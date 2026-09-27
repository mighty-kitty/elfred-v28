from __future__ import annotations

from dataclasses import asdict
from typing import Any

from adapter.journal.models import DayGroup
from adapter.journal.parser import JournalParser


_LEGACY_FIELDS = (
    "uid",
    "name",
    "content_format",
    "content_objective",
    "content_ai",
    "user_notes",
)

_LEGACY_RELATION_FIELDS = (
    "related_todo_ids",
    "related_activity_ids",
)
_LEGACY_EMPTY_FIELDS = ("mood", "energy", "day_bucket_start")


def is_unmodified_legacy_fallback(
    remote: dict[str, Any],
    day: str,
    events: list[dict[str, Any]],
    max_events: int,
) -> bool:
    expected = asdict(
        JournalParser().fallback(
            build_legacy_group(events, day, max_events=max_events)
        )
    )
    if not expected["user_notes"].startswith("由 Elfred fallback 生成；"):
        return False
    if str(remote.get("date") or "")[:10] != day:
        return False
    if not all(
        _normalized(remote.get(field)) == _normalized(expected.get(field))
        for field in _LEGACY_FIELDS
    ):
        return False
    if _normalized_tags(remote.get("tags")) != _normalized_tags(
        expected.get("tags")
    ):
        return False
    if any(
        _normalized_relations(remote.get(field))
        != _normalized_relations(expected.get(field))
        for field in _LEGACY_RELATION_FIELDS
    ):
        return False
    return all(remote.get(field) in (None, "") for field in _LEGACY_EMPTY_FIELDS)


def build_legacy_group(
    events: list[dict[str, Any]],
    day: str,
    *,
    max_events: int,
) -> DayGroup:
    day_events = [
        event
        for event in events
        if str(event.get("created_at") or "").startswith(day)
    ][:max_events]
    summaries: list[str] = []
    seen: set[str] = set()
    for event in day_events:
        content = event.get("content") or {}
        text = " ".join(
            str(content.get("summary") or content.get("clean_text") or "").split()
        )
        if not text or text in seen:
            continue
        seen.add(text)
        app = str((event.get("app") or {}).get("name") or "")
        timestamp = str(event.get("created_at") or "")[11:16]
        prefix = f"{timestamp} [{app}] " if app else f"{timestamp} "
        summaries.append(f"{len(summaries) + 1}. {prefix}{text}")

    return DayGroup(
        date=day,
        event_count=len(day_events),
        summaries=summaries,
    )


def _normalized(value: Any) -> Any:
    if value is None:
        return ""
    return value


def _normalized_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("tag_name")
        text = str(item or "").strip()
        if text:
            tags.append(text)
    return sorted(tags)


def _normalized_relations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)
