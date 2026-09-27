from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from adapter.journal.schedule import (
    journal_day_for_boundary,
    next_boundary,
    resolve_timezone,
    wait_until_boundary,
)


def test_boundary_owns_the_journal_day_across_midnight() -> None:
    china = resolve_timezone("+08:00")
    before_midnight = datetime(2026, 8, 2, 23, 59, 59, 900000, tzinfo=china)

    boundary = next_boundary(before_midnight, 0)

    assert boundary == datetime(2026, 8, 3, 0, 0, tzinfo=china)
    assert journal_day_for_boundary(boundary) == "2026-08-02"


def test_early_wakeup_waits_again_before_releasing_boundary() -> None:
    china = resolve_timezone("+08:00")
    current = datetime(2026, 8, 2, 23, 59, 59, tzinfo=china)
    boundary = datetime(2026, 8, 3, 0, 0, tzinfo=china)
    sleeps: list[float] = []

    def now() -> datetime:
        return current

    async def early_sleep(seconds: float) -> None:
        nonlocal current
        sleeps.append(seconds)
        if len(sleeps) == 1:
            current += timedelta(seconds=seconds / 2)
        else:
            current += timedelta(seconds=seconds)

    asyncio.run(
        wait_until_boundary(
            boundary,
            now=now,
            sleep=early_sleep,
            max_sleep_seconds=60,
        )
    )

    assert len(sleeps) == 2
    assert current >= boundary


@pytest.mark.parametrize(
    ("value", "offset_hours"),
    [("+08:00", 8), ("-05:30", -5.5)],
)
def test_fixed_offset_timezone_needs_no_external_tz_database(
    value: str,
    offset_hours: float,
) -> None:
    zone = resolve_timezone(value)
    offset = datetime(2026, 1, 1, tzinfo=zone).utcoffset()
    assert offset == timedelta(hours=offset_hours)


@pytest.mark.parametrize("hour", [-1, 24])
def test_generation_hour_is_validated(hour: int) -> None:
    with pytest.raises(ValueError, match="between 0 and 23"):
        next_boundary(datetime.now(timezone.utc), hour)
