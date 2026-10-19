"""Small asyncio task scheduler; jobs run until cancelled or scheduler stops."""
import asyncio, inspect, logging
log = logging.getLogger("aiomatrix.scheduler")
class Scheduler:
    def __init__(self): self._tasks = set(); self._stopped = False
    def every(self, seconds, callback, *args, **kwargs):
        if seconds <= 0: raise ValueError("seconds must be positive")
        if self._stopped: raise RuntimeError("scheduler has been stopped")
        async def runner():
            while True:
                await asyncio.sleep(seconds)
                try:
                    result = callback(*args, **kwargs)
                    if inspect.isawaitable(result): await result
                except asyncio.CancelledError: raise
                except Exception: log.exception("Scheduled job failed")
        task = asyncio.create_task(runner()); self._tasks.add(task); task.add_done_callback(self._tasks.discard); return task
    async def stop(self):
        self._stopped = True
        for task in tuple(self._tasks): task.cancel()
        if self._tasks: await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
