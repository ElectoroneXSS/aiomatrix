"""Polling dispatcher with bounded concurrent update handling and router support."""
from __future__ import annotations

import asyncio
import inspect
import logging

from .types import Update

log = logging.getLogger("aiomatrix")


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


class Router:
    def __init__(self):
        self.message_handlers = []
        self.edited_message_handlers = []
        self.channel_post_handlers = []
        self.callback_handlers = []
        self.inline_query_handlers = []
        self.update_handlers = []
        self.middlewares = []
        self.routers = []

    def message(self, *filters): return self._register(self.message_handlers, filters)
    def edited_message(self, *filters): return self._register(self.edited_message_handlers, filters)
    def channel_post(self, *filters): return self._register(self.channel_post_handlers, filters)
    def callback_query(self, *filters): return self._register(self.callback_handlers, filters)
    def inline_query(self, *filters): return self._register(self.inline_query_handlers, filters)
    def update(self, *filters): return self._register(self.update_handlers, filters)

    def include_router(self, router):
        if not isinstance(router, Router):
            raise TypeError("router must be a Router instance")
        self.routers.append(router)
        return router

    def middleware(self, middleware):
        self.middlewares.append(middleware)
        return middleware

    @staticmethod
    def _register(collection, filters):
        def decorator(func):
            collection.append((tuple(filters), func))
            return func
        return decorator

    async def _run(self, collection, event):
        # Snapshot handlers so runtime registration doesn't mutate this iteration.
        for handler_filters, handler in tuple(collection):
            try:
                matched = True
                for predicate in handler_filters:
                    result = predicate(event) if callable(predicate) else False
                    if inspect.isawaitable(result):
                        result = await result
                    if not result:
                        matched = False
                        break
                if not matched:
                    continue

                async def invoke(ev, data=None):
                    return await _maybe_await(handler(ev))

                call = invoke
                for middleware in reversed(tuple(self.middlewares)):
                    previous = call
                    async def wrapped(ev, data=None, _middleware=middleware, _next=previous):
                        return await _maybe_await(_middleware(_next, ev, data or {}))
                    call = wrapped
                await call(event, {})
                return True
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Handler/filter failed (handler=%s)", getattr(handler, "__name__", type(handler).__name__))
        return False

    async def _dispatch_chain(self, collection_name, event):
        """Dispatch to this router and every nested router in registration order."""
        handled = await self._run(getattr(self, collection_name), event)
        for router in tuple(self.routers):
            child_handled = await router._dispatch_chain(collection_name, event)
            handled = handled or child_handled
        return handled


class Dispatcher(Router):
    def __init__(self):
        super().__init__()
        self._stop = asyncio.Event()
        self._polling = False

    async def feed_update(self, bot, update):
        if isinstance(update, dict):
            update = Update.from_dict(update, bot)
        event_kinds = (
            (update.message, self.message_handlers, "message_handlers"),
            (update.edited_message, self.edited_message_handlers, "edited_message_handlers"),
            (getattr(update, "channel_post", None), self.channel_post_handlers, "channel_post_handlers"),
            (getattr(update, "edited_channel_post", None), self.channel_post_handlers, "channel_post_handlers"),
        )
        for event, collection, _name in event_kinds:
            if event is not None:
                event._bot = bot
                collection_name = _name
                # Root and nested routers are all visited. _run() catches handler errors.
                await self._dispatch_chain(collection_name, event)

        if update.callback_query is not None:
            callback = update.callback_query
            if isinstance(callback, dict):
                callback.setdefault("_bot", bot)
            await self._dispatch_chain("callback_handlers", callback)
        if update.inline_query is not None:
            query = update.inline_query
            if isinstance(query, dict):
                query.setdefault("_bot", bot)
            await self._dispatch_chain("inline_query_handlers", query)
        # Generic update handler always receives the typed Update instance.
        await self._dispatch_chain("update_handlers", update)

    def stop_polling(self):
        self._stop.set()

    async def start_polling(
        self, bot, *, polling_timeout=20, retry_delay=1.0, offset=None,
        allowed_updates=None, limit=100, concurrency=20,
    ):
        """Long-poll a single bot and handle each returned batch concurrently.

        A batch is acknowledged through the next offset only after its handlers
        finish, avoiding premature acknowledgement if the process stops mid-batch.
        Concurrency is bounded; updates from one batch are not allowed to create an
        unbounded number of background tasks.
        """
        if self._polling or getattr(bot, "_polling_active", False):
            raise RuntimeError("Only one polling loop is allowed per Dispatcher/Bot instance")
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        if not 0 <= int(polling_timeout) <= 50:
            raise ValueError("polling_timeout must be between 0 and 50")
        if not 1 <= int(limit) <= 100:
            raise ValueError("limit must be between 1 and 100")
        self._polling = True
        bot._polling_active = True
        self._stop.clear()
        semaphore = asyncio.Semaphore(int(concurrency))

        async def process(update):
            async with semaphore:
                try:
                    await self.feed_update(bot, update)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Update dispatch failed")

        try:
            while not self._stop.is_set():
                try:
                    updates = await bot.get_updates(
                        offset=offset, limit=limit, timeout=polling_timeout,
                        allowed_updates=allowed_updates,
                    )
                    if not updates:
                        # Protect against providers that ignore long-poll timeout and return immediately.
                        try:
                            await asyncio.wait_for(self._stop.wait(), timeout=0.03)
                        except asyncio.TimeoutError:
                            pass
                        continue
                    await asyncio.gather(*(process(update) for update in updates))
                    valid_ids = []
                    for update in updates:
                        try:
                            if update.update_id is not None:
                                valid_ids.append(int(update.update_id))
                        except (TypeError, ValueError):
                            continue
                    if valid_ids:
                        offset = max(valid_ids) + 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("Polling failed (%s); retrying after %.2fs", type(exc).__name__, retry_delay)
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=max(0.1, retry_delay))
                    except asyncio.TimeoutError:
                        pass
        finally:
            self._polling = False
            bot._polling_active = False
