from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_OFFSET_PATTERN = re.compile(r"^([+-])(\d{2}):(\d{2})$")


def resolve_timezone(value: str) -> tzinfo:
    name = value.strip()
    if name.casefold() == "local":
        return datetime.now().astimezone().tzinfo or timezone.utc

    match = _OFFSET_PATTERN.fullmatch(name)
    if match:
        hours = int(match.group(2))
        minutes = int(match.group(3))
        if hours > 23 or minutes > 59:
            raise ValueError(f"invalid UTC offset {value!r}")
        delta = timedelta(hours=hours, minutes=minutes)
        if match.group(1) == "-":
            delta = -delta
        return timezone(delta, name)

    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"unknown timezone {value!r}; install tzdata or use an offset like +08:00"
        ) from exc


def next_boundary(now: datetime, generation_hour: int) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("journal scheduler requires a timezone-aware clock")
    if not 0 <= generation_hour <= 23:
        raise ValueError("journal generation hour must be between 0 and 23")

    boundary = datetime.combine(
        now.date(),
        time(hour=generation_hour),
        tzinfo=now.tzinfo,
    )
    if boundary <= now:
        boundary += timedelta(days=1)
    return boundary


def journal_day_for_boundary(boundary: datetime) -> str:
    if boundary.tzinfo is None or boundary.utcoffset() is None:
        raise ValueError("journal boundary must be timezone-aware")
    return (boundary.date() - timedelta(days=1)).isoformat()


def previous_day(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("journal scheduler requires a timezone-aware clock")
    return (now.date() - timedelta(days=1)).isoformat()


async def wait_until_boundary(
    boundary: datetime,
    *,
    now: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[Any]],
    max_sleep_seconds: float = 60.0,
) -> None:
    if max_sleep_seconds <= 0:
        raise ValueError("max sleep must be positive")
    while True:
        current = now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("journal scheduler requires a timezone-aware clock")
        remaining = (boundary - current).total_seconds()
        if remaining <= 0:
            return
        await sleep(min(remaining, max_sleep_seconds))
