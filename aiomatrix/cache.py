"""Small in-process TTL/LRU cache for lightweight response and application data."""
from collections import OrderedDict
from copy import deepcopy
import time


class TTLCache:
    """TTL cache with a maximum entry count.

    It is synchronous by design: cache operations contain no await points and are
    atomic relative to other asyncio tasks running on the same event loop. Use a
    separate instance per process; this is not a distributed cache.
    """
    def __init__(self, *, ttl: float = 30.0, max_items: int = 2048):
        if ttl < 0:
            raise ValueError("ttl must be >= 0")
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        self.ttl = float(ttl)
        self.max_items = int(max_items)
        self._items = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _purge_expired(self, now=None):
        now = time.monotonic() if now is None else now
        expired = [key for key, (deadline, _) in self._items.items() if deadline <= now]
        for key in expired:
            self._items.pop(key, None)

    def get_with_status(self, key):
        now = time.monotonic()
        item = self._items.get(key)
        if item is None:
            self.misses += 1
            return False, None
        deadline, value = item
        if deadline <= now:
            self._items.pop(key, None)
            self.misses += 1
            return False, None
        self._items.move_to_end(key)
        self.hits += 1
        return True, deepcopy(value)

    def get(self, key, default=None):
        found, value = self.get_with_status(key)
        return value if found else default

    def set(self, key, value, *, ttl=None):
        duration = self.ttl if ttl is None else float(ttl)
        if duration < 0:
            raise ValueError("ttl must be >= 0")
        if duration == 0:
            self.delete(key)
            return
        now = time.monotonic()
        self._items[key] = (now + duration, deepcopy(value))
        self._items.move_to_end(key)
        self._purge_expired(now)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)
            self.evictions += 1

    def delete(self, key):
        return self._items.pop(key, None) is not None

    def clear(self):
        self._items.clear()

    def __len__(self):
        self._purge_expired()
        return len(self._items)

    def stats(self):
        return {"items": len(self), "hits": self.hits, "misses": self.misses, "evictions": self.evictions}
