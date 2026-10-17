import asyncio
import json
from urllib.parse import quote
import aiohttp
from .exceptions import APIError, NetworkError, ValidationError
from .types import Update

class Bot:
    """Async generic Bot API client. Default URL: {api_base}/{token}/{method}."""
    def __init__(self, token, *, api_base='https://abarsayeh.ir/bot', timeout=30, session=None, default_parse_mode=None):
        if not isinstance(token, str) or not token.strip():
            raise ValidationError('token must be a non-empty string')
        self.token = token.strip()
        self.api_base = api_base.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session = session
        self._owns_session = session is None
        self.default_parse_mode = default_parse_mode

    async def __aenter__(self):
        await self._ensure_session(); return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)

    def _url(self, method):
        method = str(method).strip('/')
        if not method or '/' in method:
            raise ValidationError('method must be a single API method name')
        return f'{self.api_base}/{quote(self.token, safe=":")}/{quote(method, safe="")}'

    async def call(self, method, *, data=None, json_data=None, http_method='POST'):
        await self._ensure_session()
        url = self._url(method)
        try:
            async with self._session.request(http_method.upper(), url, data=data, json=json_data) as response:
                status = response.status
                text = await response.text()
                try: payload = json.loads(text)
                except json.JSONDecodeError:
                    raise APIError('non-JSON API response: ' + text[:500], method=method, status=status)
                if status >= 400:
                    desc = payload.get('description', payload.get('message', str(payload))) if isinstance(payload, dict) else str(payload)
                    raise APIError(desc, method=method, status=status, payload=payload)
                if isinstance(payload, dict) and payload.get('ok') is False:
                    raise APIError(payload.get('description', 'API returned ok=false'), method=method, status=status, payload=payload)
                return payload.get('result') if isinstance(payload, dict) and 'result' in payload else payload
        except asyncio.CancelledError:
            raise
        except APIError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # Deliberately omit URL because it contains the token.
            raise NetworkError(f'{method}: {type(exc).__name__}: {exc}') from exc

    async def get_me(self):
        return await self.call('getMe', http_method='GET')

    async def send_message(self, chat_id, text, **kwargs):
        payload = {'chat_id': chat_id, 'text': text}
        if self.default_parse_mode and 'parse_mode' not in kwargs: payload['parse_mode'] = self.default_parse_mode
        payload.update({k: (v.to_dict() if hasattr(v, 'to_dict') else v) for k, v in kwargs.items()})
        return await self.call('sendMessage', json_data=payload)

    async def get_updates(self, *, offset=None, limit=100, timeout=20, allowed_updates=None):
        payload = {'limit': limit, 'timeout': timeout}
        if offset is not None: payload['offset'] = offset
        if allowed_updates is not None: payload['allowed_updates'] = allowed_updates
        result = await self.call('getUpdates', json_data=payload)
        if result is None: return []
        if not isinstance(result, list): raise APIError('getUpdates result is not a list', method='getUpdates', payload=result)
        return [Update.from_dict(item, bot=self) for item in result if isinstance(item, dict)]

    async def set_webhook(self, url, **kwargs):
        return await self.call('setWebhook', json_data={'url': url, **kwargs})

    async def delete_webhook(self, **kwargs): return await self.call('deleteWebhook', json_data=kwargs)
    async def get_webhook_info(self): return await self.call('getWebhookInfo', http_method='GET')
    async def get_my_commands(self): return await self.call('getMyCommands', http_method='GET')
    async def set_my_commands(self, commands, **kwargs): return await self.call('setMyCommands', json_data={'commands': commands, **kwargs})
    async def delete_my_commands(self, **kwargs): return await self.call('deleteMyCommands', json_data=kwargs)
    async def get_chat_member(self, chat_id, user_id): return await self.call('getChatMember', json_data={'chat_id': chat_id, 'user_id': user_id})

    async def close(self):
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()
