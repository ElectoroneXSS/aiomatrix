"""Async token-bucket style rate limiter for application-side throttling."""
import asyncio, time

class RateLimiter:
    def __init__(self, rate: float, per: float = 1.0):
        if rate <= 0 or per <= 0: raise ValueError("rate and per must be positive")
        self.interval = per / rate
        self._next = 0.0
        self._lock = asyncio.Lock()
    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if wait: await asyncio.sleep(wait)
    async def __aenter__(self): await self.acquire(); return self
    async def __aexit__(self, *exc): return False
