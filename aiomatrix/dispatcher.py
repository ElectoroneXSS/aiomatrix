import asyncio
import inspect
import logging
from .types import Update

log = logging.getLogger('aiomatrix')

class Router:
    def __init__(self): self.message_handlers = []
    def message(self, *filters):
        def decorator(func):
            self.message_handlers.append((filters, func)); return func
        return decorator
    async def _dispatch_message(self, message):
        for filters, handler in list(self.message_handlers):
            matched = True
            for filt in filters:
                try:
                    value = filt(message) if callable(filt) else False
                    if inspect.isawaitable(value): value = await value
                    if not value: matched = False; break
                except Exception:
                    log.exception('Filter failed'); matched = False; break
            if matched:
                try:
                    result = handler(message)
                    if inspect.isawaitable(result): await result
                except Exception: log.exception('Message handler failed')
                return True
        return False

class Dispatcher(Router):
    def __init__(self): super().__init__(); self.routers = []
    def include_router(self, router): self.routers.append(router)
    async def feed_update(self, bot, update):
        if isinstance(update, dict): update = Update.from_dict(update, bot=bot)
        if update.message:
            update.message._bot = bot
            await self._dispatch_message(update.message)
            for router in self.routers: await router._dispatch_message(update.message)
    async def start_polling(self, bot, *, polling_timeout=20, retry_delay=2):
        offset = None
        while True:
            try:
                updates = await bot.get_updates(offset=offset, timeout=polling_timeout)
                for update in updates:
                    await self.feed_update(bot, update)
                    if update.update_id is not None:
                        try: offset = int(update.update_id) + 1
                        except (ValueError, TypeError): pass
            except asyncio.CancelledError: raise
            except Exception as exc:
                log.warning('Polling failed (%s); retrying in %s seconds', type(exc).__name__, retry_delay)
                await asyncio.sleep(retry_delay)
