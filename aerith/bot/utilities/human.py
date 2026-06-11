from __future__ import annotations

import datetime as dt
import humanize
from dateutil.relativedelta import relativedelta

from .text import human_join, Plural


def human_size(size: float, fmt: str = "%.2f", trim: bool = False) -> str:
    result = humanize.naturalsize(size, format=fmt)
    return result.replace(" ", "") if trim else result


def ordinal(value: int) -> str:
    return humanize.ordinal(value)


def percentage(lowest: float, highest: float = 100) -> str:
    return f"{int((lowest / highest) * 100):.0f}%"


def format_duration(value: int, ms: bool = True) -> str:
    if ms:
        value //= 1000

    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"

    return f"{minutes:02}:{seconds:02}"


def human_timedelta(
    value: dt.datetime | dt.timedelta,
    *,
    source: dt.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    if isinstance(value, dt.timedelta):
        value = dt.datetime.now(dt.timezone.utc) - value

    now = source or dt.datetime.now(dt.timezone.utc)

    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    now = now.replace(microsecond=0)
    value = value.replace(microsecond=0)

    future = value > now
    delta = relativedelta(value, now) if future else relativedelta(now, value)
    output_suffix = "" if future or not suffix else " ago"

    attrs = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]

    output: list[str] = []

    for attr, short in attrs:
        amount = getattr(delta, f"{attr}s")

        if not amount:
            continue

        if attr == "day":
            weeks = delta.weeks

            if weeks:
                amount -= weeks * 7
                output.append(f"{weeks}w" if brief else format(Plural(weeks), "week"))

        if amount <= 0:
            continue

        output.append(f"{amount}{short}" if brief else format(Plural(amount), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if not output:
        return "now"

    return (
        "".join(output) + output_suffix
        if brief
        else human_join(output, final="and") + output_suffix
    )
