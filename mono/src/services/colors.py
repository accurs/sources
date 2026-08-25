from __future__ import annotations

import asyncio
import re

import aiohttp
from PIL import ImageColor


BARE_HEX = re.compile(r"[0-9a-fA-F]{6}")
RGB = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.I)
_name_cache: dict[str, tuple[tuple[int, int, int], str | None]] = {}


async def resolve_color(value: str) -> tuple[tuple[int, int, int], str | None]:
    cleaned = value.strip()
    cache_key = " ".join(cleaned.casefold().split())
    cached = _name_cache.get(cache_key)
    if cached is not None:
        return cached

    rgb_match = RGB.fullmatch(cleaned)
    try:
        if rgb_match:
            rgb = tuple(map(int, rgb_match.groups()))
        else:
            local_value = f"#{cleaned}" if BARE_HEX.fullmatch(cleaned) else cleaned
            try:
                rgb = ImageColor.getrgb(local_value)
            except ValueError:
                rgb = ImageColor.getrgb(re.sub(r"[\s_-]+", "", local_value))
        if len(rgb) > 3:
            rgb = rgb[:3]
        if any(not 0 <= component <= 255 for component in rgb):
            raise ValueError
        result = ((int(rgb[0]), int(rgb[1]), int(rgb[2])), None)
        _name_cache[cache_key] = result
        return result
    except (TypeError, ValueError):
        pass

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.color.pizza/v1/names/",
                params={"name": cleaned, "maxResults": 1, "list": "bestOf"},
            ) as response:
                response.raise_for_status()
                payload = await response.json()
        match = payload["colors"][0]
        if float(match.get("similarity", 0)) < 0.6:
            raise ValueError
        rgb = (
            int(match["rgb"]["r"]),
            int(match["rgb"]["g"]),
            int(match["rgb"]["b"]),
        )
        result = (rgb, str(match["name"]))
        _name_cache[cache_key] = result
        return result
    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "I could not match that color. Use a color name, six-digit HEX, or RGB value."
        ) from None
