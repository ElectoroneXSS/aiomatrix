"""Polling dispatcher with ordered handlers and router support."""
import asyncio, inspect, logging
from .types import Update
log=logging.getLogger('aiomatrix')
class Router:
    def __init__(self): self.message_handlers=[]; self.edited_message_handlers=[]; self.callback_handlers=[]
    def message(self,*filters): return self._register(self.message_handlers,filters)
    def edited_message(self,*filters): return self._register(self.edited_message_handlers,filters)
    def callback_query(self,*filters): return self._register(self.callback_handlers,filters)
    def _register(self,collection,filters):
        def deco(func): collection.append((filters,func)); return func
        return deco
    async def _run(self,collection,event):
        for filters,handler in list(collection):
            try:
                matched=True
                for f in filters:
                    v=f(event) if callable(f) else False
                    if inspect.isawaitable(v):v=await v
                    if not v:matched=False;break
                if not matched:continue
                result=handler(event)
                if inspect.isawaitable(result):await result
                return True
            except Exception: log.exception('Handler/filter failed')
        return False
    async def _dispatch_message(self,m): return await self._run(self.message_handlers,m)
class Dispatcher(Router):
    def __init__(self): super().__init__(); self.routers=[]; self._stop=asyncio.Event()
    def include_router(self,router): self.routers.append(router); return router
    async def feed_update(self,bot,update):
        if isinstance(update,dict):update=Update.from_dict(update,bot)
        for m in (update.message,update.edited_message,update.channel_post):
            if m:
                m._bot=bot; coll=self.edited_message_handlers if m is update.edited_message else self.message_handlers
                await self._run(coll,m)
                for r in self.routers: await r._run(r.edited_message_handlers if m is update.edited_message else r.message_handlers,m)
        if update.callback_query:
            cb=update.callback_query
            # Keep callback payload as dict, but provide a convenient bound answer method.
            if isinstance(cb,dict): cb.setdefault('_bot',bot)
            await self._run(self.callback_handlers,cb)
            for r in self.routers: await r._run(r.callback_handlers,cb)
    def stop_polling(self): self._stop.set()
    async def start_polling(self,bot,*,polling_timeout=20,retry_delay=2,offset=None,allowed_updates=None):
        self._stop.clear()
        while not self._stop.is_set():
            try:
                updates=await bot.get_updates(offset=offset,timeout=polling_timeout,allowed_updates=allowed_updates)
                for u in updates:
                    if self._stop.is_set():break
                    await self.feed_update(bot,u)
                    if u.update_id is not None:
                        try:offset=int(u.update_id)+1
                        except (ValueError,TypeError):pass
            except asyncio.CancelledError: raise
            except Exception as e:
                log.warning('Polling error (%s); retrying in %.1fs',type(e).__name__,retry_delay)
                try: await asyncio.wait_for(self._stop.wait(),timeout=retry_delay)
                except asyncio.TimeoutError: pass
