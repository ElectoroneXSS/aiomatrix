"""Optional SQLite-backed FSM storage. Blocking sqlite calls run in worker threads."""
import asyncio
import json
import sqlite3


class SQLiteStorage:
    def __init__(self, path="aiomatrix.sqlite3"):
        self.path = path
        self._lock = asyncio.Lock()
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS fsm (key TEXT PRIMARY KEY, state TEXT, data TEXT NOT NULL DEFAULT '{}')")

    def _run(self, sql, args=(), fetch=False):
        with sqlite3.connect(self.path, timeout=10) as db:
            cur = db.execute(sql, args)
            row = cur.fetchone() if fetch else None
            db.commit()
            return row

    async def set_state(self, key, state):
        async with self._lock:
            await asyncio.to_thread(self._run, "INSERT INTO fsm(key,state,data) VALUES(?,?, '{}') ON CONFLICT(key) DO UPDATE SET state=excluded.state", (str(key), state))

    async def get_state(self, key):
        async with self._lock:
            row = await asyncio.to_thread(self._run, "SELECT state FROM fsm WHERE key=?", (str(key),), True)
            return row[0] if row else None

    async def update_data(self, key, **kwargs):
        async with self._lock:
            row = await asyncio.to_thread(self._run, "SELECT data FROM fsm WHERE key=?", (str(key),), True)
            data = json.loads(row[0]) if row else {}
            data.update(kwargs)
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            await asyncio.to_thread(self._run, "INSERT INTO fsm(key,state,data) VALUES(?,NULL,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data", (str(key), encoded))
            return dict(data)

    async def get_data(self, key):
        async with self._lock:
            row = await asyncio.to_thread(self._run, "SELECT data FROM fsm WHERE key=?", (str(key),), True)
            return json.loads(row[0]) if row else {}

    async def clear(self, key):
        async with self._lock:
            await asyncio.to_thread(self._run, "DELETE FROM fsm WHERE key=?", (str(key),))
