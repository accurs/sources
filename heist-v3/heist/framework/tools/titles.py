import os
import json
import aiofiles
import logging
import asyncio

TITLES_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "shared",
        "titles.json"
    )
)

_titles_cache = None
_last_mtime = None
_lock = asyncio.Lock()
_logger = logging.getLogger("heist.titles")

async def load_titles(force_reload: bool = False):
    global _titles_cache, _last_mtime
    async with _lock:
        try:
            stat = await asyncio.to_thread(os.stat, TITLES_PATH)
            mtime = stat.st_mtime
        except FileNotFoundError:
            _titles_cache = {}
            _last_mtime = None
            return _titles_cache
        if not force_reload and _last_mtime == mtime:
            return _titles_cache
        try:
            async with aiofiles.open(TITLES_PATH, "r") as f:
                _titles_cache = json.loads(await f.read())
            _last_mtime = mtime
        except Exception as e:
            _logger.error("Failed to load titles: %s", e, exc_info=True)
            _titles_cache = {}
        return _titles_cache

async def get_title(user_id: int) -> str | None:
    titles = await load_titles()
    return titles.get(str(user_id))