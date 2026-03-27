import asyncio
import json
import time
from typing import Any, Optional, Dict
from collections import OrderedDict

class FastCache:
    def __init__(self, max_size: int = 10000, ttl: int = 3600):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: OrderedDict = OrderedDict()
        self.timestamps: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self.cache:
                return None
                
            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                return None
                
            self.cache.move_to_end(key)
            return self.cache[key]
            
    async def set(self, key: str, value: Any):
        async with self._lock:
            if len(self.cache) >= self.max_size and key not in self.cache:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]
                
            self.cache[key] = value
            self.timestamps[key] = time.time()
            self.cache.move_to_end(key)
            
    async def delete(self, key: str):
        async with self._lock:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
            
    async def clear(self):
        async with self._lock:
            self.cache.clear()
            self.timestamps.clear()
            
    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None