from __future__ import annotations

import asyncio
import hashlib
import io
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, Hashable, TypeVar


T = TypeVar("T")

CPU_COUNT = os.cpu_count() or 2
# Leave capacity for Discord, linked accounts, SQLite, and system services.
MEDIA_WORKERS = max(2, min(3, CPU_COUNT - 1 if CPU_COUNT > 2 else CPU_COUNT))
FFMPEG_THREADS = max(1, min(4, CPU_COUNT - 1 if CPU_COUNT > 2 else CPU_COUNT))
FRAME_WORKERS = max(2, min(3, MEDIA_WORKERS))

_EXECUTOR = ThreadPoolExecutor(
    max_workers=MEDIA_WORKERS,
    thread_name_prefix="media",
)
_FRAME_EXECUTOR = ThreadPoolExecutor(
    max_workers=FRAME_WORKERS,
    thread_name_prefix="media-frame",
)
_CACHE_LOCK = threading.Lock()
_CACHE: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
_CACHE_TTL = 5 * 60
_CACHE_ITEMS = 32
_CACHE_BYTES = 96 * 1024 * 1024


def bytes_digest(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def map_frames(function: Callable[[Any], T], frames: list[Any]) -> list[T]:
    """Process frames concurrently on one shared, bounded frame pool."""
    return list(_FRAME_EXECUTOR.map(function, frames))


def _cache_size(value: Any) -> int:
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, io.BytesIO):
        return value.getbuffer().nbytes
    if isinstance(value, tuple):
        return sum(_cache_size(item) for item in value)
    return 0


def _cache_get(key: Hashable) -> Any | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        created, value = item
        if now - created > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return value


def _cache_put(key: Hashable, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_ITEMS or sum(
            _cache_size(item[1]) for item in _CACHE.values()
        ) > _CACHE_BYTES:
            _CACHE.popitem(last=False)


async def run_media(
    function: Callable[..., T],
    /,
    *args: Any,
    cache_key: Hashable | None = None,
    **kwargs: Any,
) -> T:
    """Run CPU/blocking media work away from Discord's event loop."""
    if cache_key is not None:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        _EXECUTOR,
        partial(function, *args, **kwargs),
    )
    if cache_key is not None:
        _cache_put(cache_key, result)
    return result
