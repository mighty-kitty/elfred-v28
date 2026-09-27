from __future__ import annotations

from adapter.journal.grouper import EventGrouper


def _make_evt(eid: str, created: str, app_name: str, summary: str, tasks: list[str] | None = None) -> dict:
    return {
        "event_id": eid,
        "created_at": created,
        "app": {"name": app_name, "category": "development" if app_name == "Code" else "communication"},
        "content": {
            "summary": summary,
            "tasks": [{"task": t} for t in (tasks or [])],
        },
    }


def test_filter_by_day_excludes_other_dates():
    g = EventGrouper()
    events = [
        _make_evt("1", "2026-07-30T09:00:00+08:00", "Code", "wrote tests"),
        _make_evt("2", "2026-07-29T10:00:00+08:00", "WXWork", "meeting"),
    ]
    group = g.build(events, "2026-07-30")
    assert group.event_count == 1
    assert "wrote tests" in group.summaries[0]


def test_extract_summaries_deduplicates():
    g = EventGrouper()
    events = [
        _make_evt("1", "2026-07-30T09:00:00+08:00", "Code", "fix a bug"),
        _make_evt("2", "2026-07-30T09:01:00+08:00", "Code", "fix a bug"),  # 重复
    ]
    summaries = g._extract_summaries(events)
    assert len(summaries) == 1


def test_extract_tasks_collects_all():
    g = EventGrouper()
    events = [
        _make_evt("1", "2026-07-30T09:00:00+08:00", "Code", "done", ["task A"]),
        _make_evt("2", "2026-07-30T10:00:00+08:00", "Code", "done", ["task B"]),
    ]
    tasks = g._extract_tasks(events)
    assert len(tasks) == 2
    assert "task A" in tasks
    assert "task B" in tasks


def test_extract_apps_counts_correctly():
    g = EventGrouper()
    events = [
        _make_evt("1", "2026-07-30T09:00:00+08:00", "Code", "done"),
        _make_evt("2", "2026-07-30T10:00:00+08:00", "Code", "done"),
        _make_evt("3", "2026-07-30T11:00:00+08:00", "WXWork", "done"),
    ]
    apps = g._extract_apps(events)
    assert apps == {"development": 2, "communication": 1}


def test_build_keeps_full_day_metrics_while_bounding_prompt_events():
    g = EventGrouper()
    events = [
        _make_evt(
            str(i),
            f"2026-07-30T{(i // 60):02d}:{(i % 60):02d}:00+08:00",
            "Code" if i % 3 else "WXWork",
            f"event {i}",
        )
        for i in range(120)
    ]
    group = g.build(events, "2026-07-30", max_events=10)
    assert group.event_count == 120
    assert group.included_event_count == 10
    assert group.truncated is True
    assert len(group.summaries) == 10
    assert sum(group.app_breakdown.values()) == 120
    assert any("event 0" in item for item in group.summaries)
    assert any("event 119" in item for item in group.summaries)


def test_representative_selection_is_stable_and_chronological():
    g = EventGrouper()
    events = [
        _make_evt(
            str(i),
            f"2026-07-30T{(i // 60):02d}:{(i % 60):02d}:00+08:00",
            "Code",
            f"event {i}",
            ["important task"] if i == 77 else None,
        )
        for i in range(100)
    ]

    forward = g.build(events, "2026-07-30", max_events=12)
    reverse = g.build(list(reversed(events)), "2026-07-30", max_events=12)

    assert forward.source_event_ids == reverse.source_event_ids
    assert forward.summaries == reverse.summaries
    assert "77" in forward.source_event_ids
    assert forward.source_event_ids == sorted(
        forward.source_event_ids,
        key=lambda event_id: int(event_id),
    )


def test_structured_tasks_are_aggregated_from_all_safe_day_events():
    g = EventGrouper()
    events = [
        _make_evt(
            str(index),
            f"2026-07-30T09:{index:02d}:00+08:00",
            "Code",
            f"event {index}",
            [f"task {index}"],
        )
        for index in range(20)
    ]

    group = g.build(events, "2026-07-30", max_events=3)

    assert group.included_event_count == 3
    assert group.task_titles == [f"task {index}" for index in range(20)]


def test_build_empty_when_no_matching_date():
    g = EventGrouper()
    events = [_make_evt("1", "2026-07-29T09:00:00+08:00", "Code", "old")]
    group = g.build(events, "2026-07-30")
    assert group.event_count == 0
    assert group.summaries == []
