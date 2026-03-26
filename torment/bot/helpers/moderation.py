from __future__ import annotations

import re
from datetime import timedelta


CLEAR_TOKENS = {"none", "off", "reset", "clear", "remove", "disable"}


def is_clear_token(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in CLEAR_TOKENS


def parse_duration(value: str | None) -> timedelta | None:
    if not value:
        return None
    text = value.strip().lower()
    if not text:
        return None

    matches = re.findall(r"(\d+)([smhdw])", text)
    if not matches:
        return None

    seconds = 0
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }
    for amount, unit in matches:
        seconds += int(amount) * units[unit]
    if seconds <= 0:
        return None
    return timedelta(seconds=seconds)


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0 seconds"

    parts: list[str] = []
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        parts.append(f"{days} day" + ("s" if days != 1 else ""))
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if seconds:
        parts.append(f"{seconds} second" + ("s" if seconds != 1 else ""))

    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"
