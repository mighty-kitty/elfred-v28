from __future__ import annotations

import json

import pytest

from adapter.journal.grouper import DayGroup
from adapter.journal.models import JournalPayload
from adapter.journal.parser import JournalParseError, JournalParser


def _group(date: str = "2026-07-30", event_count: int = 10) -> DayGroup:
    return DayGroup(
        date=date, event_count=event_count,
        summaries=[f"Event {i}" for i in range(event_count)],
    )


def test_parse_valid_json():
    p = JournalParser()
    raw = json.dumps({
        "summary_line": "今天写了测试",
        "main_thread": "早上写grouper测试，下午写parser测试",
        "key_progress": ["完成grouper测试", "完成parser测试"],
        "task_changes": "从零到有",
        "ideas_and_insights": ["单测很重要"],
        "decisions": ["用pytest"],
        "risks_and_blockers": [],
        "waiting_on": [],
        "next_steps": ["写service测试"],
        "mood_and_energy": "高效",
    })
    result = p.parse(raw, _group())
    assert isinstance(result, JournalPayload)
    assert "今天写了测试" in result.content_objective
    assert "完成grouper测试" in result.content_ai
    assert "高效" in result.content_ai


def test_parse_markdown_fence():
    p = JournalParser()
    raw = "```json\n" + json.dumps({"summary_line": "test", "main_thread": "narrative"}) + "\n```"
    result = p.parse(raw, _group())
    assert "test" in result.content_objective


def test_parse_empty_raises():
    p = JournalParser()
    with pytest.raises(JournalParseError):
        p.parse("", _group())


def test_fallback_produces_valid_payload():
    p = JournalParser()
    result = p.fallback(_group("2026-07-30", 5))
    assert result.uid == "elfred-daily-2026-07-30"
    assert result.content_format == "markdown"
    assert "Event 0" in result.content_objective


def test_build_ai_with_mixed_types():
    p = JournalParser()
    raw = json.dumps({
        "summary_line": "test",
        "main_thread": "narrative",
        "key_progress": ["A", "B"],             # list
        "task_changes": "some change text",     # string
    })
    result = p.parse(raw, _group())
    assert "关键进展" in result.content_ai
    assert "任务变化" in result.content_ai
    assert "- A" in result.content_ai
    assert "some change text" in result.content_ai


def test_parse_rejects_wrong_field_types_and_oversized_content():
    p = JournalParser()
    wrong_type = json.dumps({"summary_line": ["not", "a", "string"]})
    with pytest.raises(JournalParseError):
        p.parse(wrong_type, _group())

    too_long = json.dumps({"summary_line": "x" * 501})
    with pytest.raises(JournalParseError):
        p.parse(too_long, _group())


def test_parse_caps_bullet_fields():
    p = JournalParser()
    raw = json.dumps(
        {
            "summary_line": "summary",
            "main_thread": "thread",
            "key_progress": [f"item {index}" for index in range(6)],
        }
    )

    with pytest.raises(JournalParseError):
        p.parse(raw, _group())
