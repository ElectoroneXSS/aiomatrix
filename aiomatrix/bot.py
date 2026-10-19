"""Fast asynchronous client for Telegram-like Bot APIs, with safe retry defaults."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import quote
from typing import Any

import aiohttp

from .exceptions import APIError, NetworkError, ValidationError, RetryAfter
from .types import Update
from .cache import TTLCache

log = logging.getLogger("aiomatrix")


def _plain(value: Any) -> Any:
    """Convert aiomatrix models to JSON-ready built-in types."""
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _plain(value.to_dict())
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _camel_case(name: str) -> str:
    parts = str(name).split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


class Bot:
    """Asynchronous Bot API client.

    Default endpoint format: ``{api_base}/{token}/{method}``.
    The default ``api_base`` is ``https://abarsayeh.ir/bot``. A shared aiohttp
    session and connection pool are used for all requests made by this client.

    Network retries are deliberately restricted to read-like methods by default
    so a timed-out ``sendMessage`` request does not silently create duplicates.
    HTTP 429 responses may be retried because the API explicitly rejected the
    request due to rate limiting.
    """

    _SAFE_RETRY_METHODS = {
        "getme", "getupdates", "getchat", "getchatmember", "getchatadministrators",
        "getchatmembercount", "getfile", "getuserprofilephotos", "getstickerset",
        "getwebhookinfo", "getmycommands", "getchatmenubutton",
    }

    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://abarsayeh.ir/bot",
        timeout: float = 35,
        connect_timeout: float = 10,
        session: aiohttp.ClientSession | None = None,
        default_parse_mode: str | None = None,
        max_concurrency: int = 50,
        connection_limit: int = 100,
        connection_limit_per_host: int = 50,
        retries: int = 2,
        retry_backoff: float = 0.35,
        max_retry_after: float = 15,
        retry_non_idempotent: bool = False,
        headers: dict | None = None,
        rate_limit=None,
        trust_env: bool = False,
        file_url_template: str | None = None,
        cache_ttl: float = 300,
        cache_methods=("getMe",),
        cache_max_items: int = 1024,
    ):
        if not isinstance(token, str) or not token.strip():
            raise ValidationError("token must be a non-empty string")
        if not isinstance(api_base, str) or not api_base.startswith(("https://", "http://")):
            raise ValidationError("api_base must be an absolute HTTP(S) URL")
        if timeout <= 0 or connect_timeout <= 0:
            raise ValidationError("timeouts must be positive")
        if max_concurrency < 1 or connection_limit < 1 or connection_limit_per_host < 1:
            raise ValidationError("connection and concurrency limits must be >= 1")
        if retries < 0 or retry_backoff < 0 or max_retry_after < 0:
            raise ValidationError("retry settings must be non-negative")
        if cache_ttl < 0 or cache_max_items < 1:
            raise ValidationError("cache_ttl must be >= 0 and cache_max_items must be >= 1")

        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = float(timeout)
        self.connect_timeout = float(connect_timeout)
        self.timeout = aiohttp.ClientTimeout(total=self.timeout_seconds, connect=self.connect_timeout)
        self._session = session
        self._owns_session = session is None
        self.default_parse_mode = default_parse_mode
        self._semaphore = asyncio.Semaphore(int(max_concurrency))
        self.connection_limit = int(connection_limit)
        self.connection_limit_per_host = int(connection_limit_per_host)
        self.retries = int(retries)
        self.retry_backoff = float(retry_backoff)
        self.max_retry_after = float(max_retry_after)
        self.retry_non_idempotent = bool(retry_non_idempotent)
        self.headers = dict(headers or {})
        self.rate_limit = rate_limit
        self.trust_env = bool(trust_env)
        self.file_url_template = file_url_template
        self.cache_ttl = float(cache_ttl)
        self.cache_methods = {str(item).replace("_", "").lower() for item in (cache_methods or ())}
        self.cache = TTLCache(ttl=self.cache_ttl, max_items=int(cache_max_items))
        self.logger = log
        self._polling_active = False
        self._local_dispatcher = None
        self._stats = {
            "requests": 0, "successes": 0, "failures": 0, "retries": 0,
            "rate_limits": 0, "cache_hits": 0, "total_latency_ms": 0.0, "last_latency_ms": 0.0,
        }

    async def __aenter__(self):
        await self._ensure_session()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            connector_options = {
                "limit": self.connection_limit,
                "limit_per_host": self.connection_limit_per_host,
                "ttl_dns_cache": 300,
            }
            # aiohttp ignores this flag on newer CPython; keep compatibility with older versions.
            if sys.version_info < (3, 13, 5):
                connector_options["enable_cleanup_closed"] = True
            connector = aiohttp.TCPConnector(**connector_options)
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
                headers=self.headers,
                trust_env=self.trust_env,
                raise_for_status=False,
            )
            self._owns_session = True

    def _url(self, method: str) -> str:
        method = str(method).strip("/")
        if not method or "/" in method or "?" in method or "#" in method:
            raise ValidationError("method must be a single API method name")
        return f"{self.api_base}/{quote(self.token, safe=':')}/{quote(method, safe='')}"

    def stats(self, *, reset: bool = False) -> dict:
        """Return request counters and latency totals without exposing credentials."""
        snapshot = dict(self._stats)
        snapshot["average_latency_ms"] = (
            snapshot["total_latency_ms"] / snapshot["requests"] if snapshot["requests"] else 0.0
        )
        if reset:
            for key in self._stats:
                self._stats[key] = 0 if key != "last_latency_ms" else 0.0
        return snapshot

    def _can_retry(self, method: str, http_method: str) -> bool:
        if self.retry_non_idempotent or http_method.upper() == "GET":
            return True
        normalized = method.replace("_", "").lower()
        return normalized in self._SAFE_RETRY_METHODS or normalized.startswith("get")

    async def call(
        self,
        method: str,
        *,
        data=None,
        json_data=None,
        http_method: str = "POST",
        params: dict | None = None,
        request_timeout: float | None = None,
    ):
        """Call a provider method directly. Unknown methods are not mocked."""
        method = str(method).strip("/")
        url = self._url(method)  # validate method before starting any network work
        if json_data is not None and data is not None:
            raise ValidationError("use either json_data or data, not both")
        json_data = _plain(json_data) if json_data is not None else None
        if isinstance(data, (dict, list, tuple)):
            data = _plain(data)

        cache_key = None
        if (self.cache_ttl > 0 and data is None
                and (json_data is not None or params is not None or http_method.upper() == "GET")
                and method.replace("_", "").lower() in self.cache_methods):
            try:
                encoded_key = json.dumps(
                    {"method": method.lower(), "http_method": http_method.upper(),
                     "json": json_data, "params": params},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
                )
            except (TypeError, ValueError):
                encoded_key = None
            if encoded_key is not None:
                cache_key = encoded_key
                found, cached_result = self.cache.get_with_status(cache_key)
                if found:
                    self._stats["cache_hits"] += 1
                    self.logger.debug("API cache hit method=%s", method)
                    return cached_result

        await self._ensure_session()
        if self.rate_limit is not None:
            await self.rate_limit.acquire()

        attempts = self.retries + 1
        retryable = self._can_retry(method, http_method)
        req_timeout = self.timeout if request_timeout is None else aiohttp.ClientTimeout(
            total=float(request_timeout), connect=min(self.connect_timeout, float(request_timeout))
        )
        async with self._semaphore:
            self._stats["requests"] += 1
            for attempt in range(attempts):
                started = time.perf_counter()
                try:
                    async with self._session.request(
                        http_method.upper(), url, data=data, json=json_data, params=params,
                        timeout=req_timeout,
                    ) as response:
                        status = response.status
                        raw = await response.text()
                        elapsed = (time.perf_counter() - started) * 1000
                        self._stats["last_latency_ms"] = elapsed
                        self._stats["total_latency_ms"] += elapsed
                        try:
                            payload = json.loads(raw) if raw else {}
                        except json.JSONDecodeError as exc:
                            if status >= 500 and retryable and attempt + 1 < attempts:
                                self._stats["retries"] += 1
                                await asyncio.sleep(self.retry_backoff * (2 ** attempt) + random.random() * 0.05)
                                continue
                            raise APIError(
                                f"non-JSON response: {raw[:200]}", method=method, status=status
                            ) from exc

                        is_dict = isinstance(payload, dict)
                        error_code = payload.get("error_code") if is_dict else None
                        if status == 429 or error_code == 429:
                            self._stats["rate_limits"] += 1
                            parameters = payload.get("parameters") or {} if is_dict else {}
                            header_retry = response.headers.get("Retry-After")
                            try:
                                retry_after = float(parameters.get("retry_after", header_retry or 1))
                            except (TypeError, ValueError):
                                retry_after = 1.0
                            retry_after = min(max(0.0, retry_after), self.max_retry_after)
                            # FormData may contain one-shot file streams; callers can retry those
                            # explicitly with a freshly opened file to avoid sending an empty body.
                            can_replay_body = not isinstance(data, aiohttp.FormData)
                            if attempt + 1 < attempts and can_replay_body:
                                self._stats["retries"] += 1
                                await asyncio.sleep(retry_after)
                                continue
                            self._stats["failures"] += 1
                            raise RetryAfter(
                                "rate limited", retry_after=retry_after, method=method,
                                status=status, payload=payload, error_code=429,
                            )

                        if status >= 500 and retryable and attempt + 1 < attempts:
                            self._stats["retries"] += 1
                            await asyncio.sleep(self.retry_backoff * (2 ** attempt) + random.random() * 0.05)
                            continue

                        api_failed = is_dict and (
                            payload.get("ok") is False
                            or payload.get("success") is False
                            or (payload.get("error_code") not in (None, 0, "0") and "result" not in payload)
                            or bool(payload.get("error"))
                        )
                        if status >= 400 or api_failed:
                            self._stats["failures"] += 1
                            desc = (payload.get("description") or payload.get("message") or payload.get("error") or str(payload)) if is_dict else str(payload)
                            raise APIError(
                                desc, method=method, status=status, payload=payload,
                                error_code=error_code,
                            )

                        self._stats["successes"] += 1
                        self.logger.debug("API call succeeded method=%s status=%s latency_ms=%.1f", method, status, elapsed)
                        result = payload.get("result") if is_dict and "result" in payload else payload
                        if cache_key is not None:
                            self.cache.set(cache_key, result, ttl=self.cache_ttl)
                        return result

                except asyncio.CancelledError:
                    raise
                except (APIError, RetryAfter):
                    raise
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                    elapsed = (time.perf_counter() - started) * 1000
                    self._stats["last_latency_ms"] = elapsed
                    self._stats["total_latency_ms"] += elapsed
                    if retryable and attempt + 1 < attempts:
                        self._stats["retries"] += 1
                        await asyncio.sleep(self.retry_backoff * (2 ** attempt) + random.random() * 0.05)
                        continue
                    self._stats["failures"] += 1
                    # Never include the request URL: the token is embedded in it.
                    raise NetworkError(f"{method}: {type(exc).__name__}: request failed") from exc
        raise NetworkError(f"{method}: request failed")

    async def close(self):
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()

    def _ensure_dispatcher(self):
        if self._local_dispatcher is None:
            from .dispatcher import Dispatcher
            self._local_dispatcher = Dispatcher()
        return self._local_dispatcher

    def command(self, *commands, prefix="/"):
        """Register a command handler directly on the Bot (convenience API)."""
        from .filters import Command
        return self._ensure_dispatcher().message(Command(*commands, prefix=prefix))

    def on_message(self, *message_filters):
        return self._ensure_dispatcher().message(*message_filters)

    def on_edited_message(self, *message_filters):
        return self._ensure_dispatcher().edited_message(*message_filters)

    def on_callback_query(self, *query_filters):
        return self._ensure_dispatcher().callback_query(*query_filters)

    def on_inline_query(self, *query_filters):
        return self._ensure_dispatcher().inline_query(*query_filters)

    def on_photo(self):
        from .filters import HasPhoto
        return self._ensure_dispatcher().message(HasPhoto())

    def on_document(self):
        from .filters import HasDocument
        return self._ensure_dispatcher().message(HasDocument())

    def on_video(self):
        from .filters import HasVideo
        return self._ensure_dispatcher().message(HasVideo())

    def on_audio(self):
        from .filters import HasAudio
        return self._ensure_dispatcher().message(HasAudio())

    async def run_polling(self, **kwargs):
        """Start the Bot's convenience dispatcher; use ``await bot.run_polling()``."""
        return await self._ensure_dispatcher().start_polling(self, **kwargs)

    def stop_polling(self):
        if self._local_dispatcher is not None:
            self._local_dispatcher.stop_polling()

    async def get_me(self):
        return await self.call("getMe", http_method="GET")

    async def send_message(self, chat_id, text, **kwargs):
        if text is None:
            raise ValidationError("text must not be None")
        payload = {"chat_id": chat_id, "text": str(text)}
        if self.default_parse_mode and "parse_mode" not in kwargs:
            payload["parse_mode"] = self.default_parse_mode
        payload.update(kwargs)
        for key in ("inline_keypad", "chat_keypad", "reply_markup"):
            if key in payload:
                payload[key] = _plain(payload[key])
        return await self.call("sendMessage", json_data=payload)

    async def get_updates(self, *, offset=None, limit=100, timeout=20, allowed_updates=None):
        if not 1 <= int(limit) <= 100:
            raise ValidationError("limit must be between 1 and 100")
        if int(timeout) < 0:
            raise ValidationError("timeout must be >= 0")
        payload = {"limit": int(limit), "timeout": int(timeout)}
        if offset is not None:
            payload["offset"] = offset
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        # Allow the server's long-poll to exceed normal request timeout slightly.
        result = await self.call("getUpdates", json_data=payload,
                                 request_timeout=max(self.timeout_seconds, int(timeout) + 10))
        if result is None:
            return []
        if isinstance(result, dict) and isinstance(result.get("updates"), list):
            result = result["updates"]
        if not isinstance(result, list):
            raise APIError("getUpdates result is not a list", method="getUpdates", payload=result)
        return [Update.from_dict(item, bot=self) for item in result if isinstance(item, dict)]

    async def get_updates_raw(self, **kwargs):
        result = await self.call("getUpdates", json_data=kwargs,
                                 request_timeout=max(self.timeout_seconds, int(kwargs.get("timeout", 0)) + 10))
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return result.get("updates", []) if isinstance(result, dict) else []

    async def get_chat(self, chat_id): return await self.call("getChat", json_data={"chat_id": chat_id})
    async def get_chat_member(self, chat_id, user_id): return await self.call("getChatMember", json_data={"chat_id": chat_id, "user_id": user_id})
    async def get_chat_administrators(self, chat_id): return await self.call("getChatAdministrators", json_data={"chat_id": chat_id})
    async def get_chat_member_count(self, chat_id): return await self.call("getChatMemberCount", json_data={"chat_id": chat_id})
    async def get_chat_members_count(self, chat_id): return await self.get_chat_member_count(chat_id)
    async def edit_message_text(self, chat_id, message_id, text, **kwargs): return await self.call("editMessageText", json_data={"chat_id": chat_id, "message_id": message_id, "text": text, **kwargs})
    async def edit_message_caption(self, chat_id, message_id, caption, **kwargs): return await self.call("editMessageCaption", json_data={"chat_id": chat_id, "message_id": message_id, "caption": caption, **kwargs})
    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None, **kwargs): return await self.call("editMessageReplyMarkup", json_data={"chat_id": chat_id, "message_id": message_id, "reply_markup": _plain(reply_markup), **kwargs})
    async def edit_message_media(self, chat_id, message_id, media, **kwargs): return await self.call("editMessageMedia", json_data={"chat_id": chat_id, "message_id": message_id, "media": _plain(media), **kwargs})
    async def delete_message(self, chat_id, message_id): return await self.call("deleteMessage", json_data={"chat_id": chat_id, "message_id": message_id})
    async def delete_messages(self, chat_id, message_ids): return await self.call("deleteMessages", json_data={"chat_id": chat_id, "message_ids": list(message_ids)})
    async def forward_message(self, chat_id, from_chat_id, message_id, **kwargs): return await self.call("forwardMessage", json_data={"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id, **kwargs})
    async def copy_message(self, chat_id, from_chat_id, message_id, **kwargs): return await self.call("copyMessage", json_data={"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id, **kwargs})

    @staticmethod
    def _is_local_upload(value):
        return isinstance(value, (bytes, bytearray, memoryview, os.PathLike)) or hasattr(value, "read") or (isinstance(value, str) and os.path.isfile(value)
        )

    @staticmethod
    def _multipart_value(value):
        value = _plain(value)
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return None
        return str(value)

    async def _send_media(self, method, required, media_field, media_value, kwargs):
        kwargs = dict(kwargs)
        filename_hint = kwargs.pop("filename", None)
        payload = dict(required)
        payload.update(kwargs)
        payload[media_field] = media_value
        for key, value in list(payload.items()):
            payload[key] = _plain(value)
        if not self._is_local_upload(media_value):
            return await self.call(method, json_data=payload)

        media_name = media_field
        if isinstance(media_value, os.PathLike):
            media_value = os.fspath(media_value)
        if isinstance(media_value, (str, bytes, bytearray, memoryview)) and isinstance(media_value, str):
            handle = open(media_value, "rb")
            try:
                filename = os.path.basename(media_value) or media_name
                form = aiohttp.FormData()
                for key, value in payload.items():
                    if key == media_field or value is None:
                        continue
                    value = self._multipart_value(value)
                    if value is not None:
                        form.add_field(key, value)
                form.add_field(media_field, handle, filename=filename)
                return await self.call(method, data=form)
            finally:
                handle.close()

        if isinstance(media_value, (bytes, bytearray, memoryview)):
            stream = io.BytesIO(bytes(media_value))
            filename = filename_hint or media_name
            form = aiohttp.FormData()
            for key, value in payload.items():
                if key == media_field or value is None:
                    continue
                value = self._multipart_value(value)
                if value is not None:
                    form.add_field(key, value)
            form.add_field(media_field, stream, filename=filename)
            try:
                return await self.call(method, data=form)
            finally:
                stream.close()

        # A caller-provided file object remains owned by the caller.
        filename = getattr(media_value, "name", media_name)
        form = aiohttp.FormData()
        for key, value in payload.items():
            if key == media_field or value is None:
                continue
            value = self._multipart_value(value)
            if value is not None:
                form.add_field(key, value)
        form.add_field(media_field, media_value, filename=os.path.basename(str(filename)))
        return await self.call(method, data=form)

    async def send_photo(self, chat_id, photo, **kwargs): return await self._send_media("sendPhoto", {"chat_id": chat_id}, "photo", photo, kwargs)
    async def send_audio(self, chat_id, audio, **kwargs): return await self._send_media("sendAudio", {"chat_id": chat_id}, "audio", audio, kwargs)
    async def send_document(self, chat_id, document, **kwargs): return await self._send_media("sendDocument", {"chat_id": chat_id}, "document", document, kwargs)
    async def send_video(self, chat_id, video, **kwargs): return await self._send_media("sendVideo", {"chat_id": chat_id}, "video", video, kwargs)
    async def send_animation(self, chat_id, animation, **kwargs): return await self._send_media("sendAnimation", {"chat_id": chat_id}, "animation", animation, kwargs)
    async def send_voice(self, chat_id, voice, **kwargs): return await self._send_media("sendVoice", {"chat_id": chat_id}, "voice", voice, kwargs)
    async def send_video_note(self, chat_id, video_note, **kwargs): return await self._send_media("sendVideoNote", {"chat_id": chat_id}, "video_note", video_note, kwargs)
    async def send_sticker(self, chat_id, sticker, **kwargs): return await self._send_media("sendSticker", {"chat_id": chat_id}, "sticker", sticker, kwargs)
    async def send_media_group(self, chat_id, media, **kwargs): return await self.call("sendMediaGroup", json_data={"chat_id": chat_id, "media": _plain(media), **kwargs})
    async def send_location(self, chat_id, latitude, longitude, **kwargs): return await self.call("sendLocation", json_data={"chat_id": chat_id, "latitude": latitude, "longitude": longitude, **kwargs})
    async def send_venue(self, chat_id, latitude, longitude, title, address, **kwargs): return await self.call("sendVenue", json_data={"chat_id": chat_id, "latitude": latitude, "longitude": longitude, "title": title, "address": address, **kwargs})
    async def send_contact(self, chat_id, phone_number, first_name, **kwargs): return await self.call("sendContact", json_data={"chat_id": chat_id, "phone_number": phone_number, "first_name": first_name, **kwargs})
    async def send_poll(self, chat_id, question, options, **kwargs): return await self.call("sendPoll", json_data={"chat_id": chat_id, "question": question, "options": options, **kwargs})
    async def stop_poll(self, chat_id, message_id, **kwargs): return await self.call("stopPoll", json_data={"chat_id": chat_id, "message_id": message_id, **kwargs})
    async def send_dice(self, chat_id, **kwargs): return await self.call("sendDice", json_data={"chat_id": chat_id, **kwargs})
    async def send_chat_action(self, chat_id, action, **kwargs): return await self.call("sendChatAction", json_data={"chat_id": chat_id, "action": action, **kwargs})
    async def answer_callback_query(self, callback_query_id, **kwargs): return await self.call("answerCallbackQuery", json_data={"callback_query_id": callback_query_id, **kwargs})
    async def get_file(self, file_id): return await self.call("getFile", json_data={"file_id": file_id})
    async def ban_chat_member(self, chat_id, user_id, **kwargs): return await self.call("banChatMember", json_data={"chat_id": chat_id, "user_id": user_id, **kwargs})
    async def unban_chat_member(self, chat_id, user_id, **kwargs): return await self.call("unbanChatMember", json_data={"chat_id": chat_id, "user_id": user_id, **kwargs})
    async def restrict_chat_member(self, chat_id, user_id, permissions, **kwargs): return await self.call("restrictChatMember", json_data={"chat_id": chat_id, "user_id": user_id, "permissions": _plain(permissions), **kwargs})
    async def promote_chat_member(self, chat_id, user_id, **kwargs): return await self.call("promoteChatMember", json_data={"chat_id": chat_id, "user_id": user_id, **kwargs})
    async def set_chat_permissions(self, chat_id, permissions, **kwargs): return await self.call("setChatPermissions", json_data={"chat_id": chat_id, "permissions": _plain(permissions), **kwargs})
    async def set_chat_title(self, chat_id, title): return await self.call("setChatTitle", json_data={"chat_id": chat_id, "title": title})
    async def set_chat_description(self, chat_id, description): return await self.call("setChatDescription", json_data={"chat_id": chat_id, "description": description})
    async def set_chat_photo(self, chat_id, photo, **kwargs): return await self._send_media("setChatPhoto", {"chat_id": chat_id}, "photo", photo, kwargs)
    async def delete_chat_photo(self, chat_id): return await self.call("deleteChatPhoto", json_data={"chat_id": chat_id})
    async def pin_chat_message(self, chat_id, message_id, **kwargs): return await self.call("pinChatMessage", json_data={"chat_id": chat_id, "message_id": message_id, **kwargs})
    async def unpin_chat_message(self, chat_id, message_id=None):
        payload = {"chat_id": chat_id}
        if message_id is not None: payload["message_id"] = message_id
        return await self.call("unpinChatMessage", json_data=payload)
    async def unpin_all_chat_messages(self, chat_id): return await self.call("unpinAllChatMessages", json_data={"chat_id": chat_id})
    async def leave_chat(self, chat_id): return await self.call("leaveChat", json_data={"chat_id": chat_id})
    async def get_chat_administrators_count(self, chat_id): return len(await self.get_chat_administrators(chat_id))
    async def set_my_commands(self, commands, **kwargs): return await self.call("setMyCommands", json_data={"commands": [_plain(c) for c in commands], **kwargs})
    async def get_my_commands(self, **kwargs): return await self.call("getMyCommands", params=kwargs, http_method="GET")
    async def delete_my_commands(self, **kwargs): return await self.call("deleteMyCommands", json_data=kwargs)
    async def set_webhook(self, url, **kwargs): return await self.call("setWebhook", json_data={"url": url, **kwargs})
    async def delete_webhook(self, **kwargs): return await self.call("deleteWebhook", json_data=kwargs)
    async def get_webhook_info(self): return await self.call("getWebhookInfo", http_method="GET")
    async def get_user_profile_photos(self, user_id, **kwargs): return await self.call("getUserProfilePhotos", json_data={"user_id": user_id, **kwargs})
    async def create_chat_invite_link(self, chat_id, **kwargs): return await self.call("createChatInviteLink", json_data={"chat_id": chat_id, **kwargs})
    async def export_chat_invite_link(self, chat_id): return await self.call("exportChatInviteLink", json_data={"chat_id": chat_id})
    async def revoke_chat_invite_link(self, chat_id, invite_link): return await self.call("revokeChatInviteLink", json_data={"chat_id": chat_id, "invite_link": invite_link})
    async def get_sticker_set(self, name): return await self.call("getStickerSet", json_data={"name": name})
    async def get_chat_member_status(self, chat_id, user_id):
        result = await self.get_chat_member(chat_id, user_id)
        return result.get("status") if isinstance(result, dict) else None

    async def download_file(self, file_path, *, max_bytes: int = 50 * 1024 * 1024) -> bytes:
        """Download a file URL/path. Providers may require a custom file URL template.

        ``file_path`` may be a URL, a path string, or the dictionary returned by
        ``get_file``. ``max_bytes`` protects against unexpectedly large downloads.
        """
        await self._ensure_session()
        direct_url = None
        if isinstance(file_path, dict):
            direct_url = file_path.get("file_url") or file_path.get("url")
            file_path = file_path.get("file_path") or file_path.get("path") or ""
        if direct_url:
            url = direct_url
        elif isinstance(file_path, str) and file_path.startswith(("http://", "https://")):
            url = file_path
        elif self.file_url_template:
            url = self.file_url_template.format(
                api_base=self.api_base, token=quote(self.token, safe=":"),
                file_path=quote(str(file_path).lstrip("/"), safe="/"),
            )
        else:
            url = f"{self.api_base}/file/{quote(self.token, safe=':')}/{quote(str(file_path).lstrip('/'), safe='/')}"
        try:
            async with self._session.get(url, timeout=self.timeout) as response:
                if response.status >= 400:
                    raise APIError("file download failed", status=response.status, method="downloadFile")
                length = response.content_length
                if length is not None and length > max_bytes:
                    raise ValidationError(f"file exceeds max_bytes ({max_bytes})")
                chunks, total = [], 0
                async for chunk in response.content.iter_chunked(64 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValidationError(f"file exceeds max_bytes ({max_bytes})")
                    chunks.append(chunk)
                return b"".join(chunks)
        except asyncio.CancelledError:
            raise
        except (APIError, ValidationError):
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            raise NetworkError(f"downloadFile: {type(exc).__name__}: request failed") from exc

    def __getattr__(self, name):
        """Fallback wrapper for future/provider-specific methods.

        Example: ``await bot.get_business_connection(business_connection_id=...)``.
        Unknown method names are sent to the configured API; this does *not*
        imply that the remote provider actually implements them.
        """
        if name.startswith("_") or name in {"token", "api_base"}:
            raise AttributeError(name)
        method = _camel_case(name)
        async def dynamic_method(*args, **kwargs):
            if args:
                raise TypeError(f"{name} fallback accepts keyword arguments only; use bot.call({method!r}, json_data=...) for positional payloads")
            return await self.call(method, json_data=kwargs)
        dynamic_method.__name__ = name
        return dynamic_method
