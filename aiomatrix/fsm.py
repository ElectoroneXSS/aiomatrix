"""Simple async in-memory FSM storage (use a persistent backend for production)."""
import asyncio
class MemoryStorage:
    def __init__(self): self._data={}; self._lock=asyncio.Lock()
    async def set_state(self,key,state):
        async with self._lock:self._data.setdefault(str(key),{})['state']=state
    async def get_state(self,key):
        async with self._lock:return self._data.get(str(key),{}).get('state')
    async def update_data(self,key,**kwargs):
        async with self._lock:self._data.setdefault(str(key),{}).setdefault('data',{}).update(kwargs);return dict(self._data[str(key)]['data'])
    async def get_data(self,key):
        async with self._lock:return dict(self._data.get(str(key),{}).get('data',{}))
    async def clear(self,key):
        async with self._lock:self._data.pop(str(key),None)
