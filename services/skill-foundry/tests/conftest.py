from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from adapter.config import Settings
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.service import AdapterService


def make_event(event_id: str = "test-event-001", **overrides: Any) -> dict[str, Any]:
    event = {
        "event_id": event_id,
        "created_at": "2026-07-13T09:30:00+08:00",
        "source": "desktop_observer",
        "app": {"name": "Codex", "process_name": "Codex.exe", "window_title": "Elfred Adapter", "category": "development"},
        "trigger": {"type": "test", "level": 3, "score": 8, "reasons": ["test"]},
        "content": {
            "content_type": "important",
            "raw_text": "决定使用 Adapter。新想法：来源链接可支持 forget。风险：FreeTodo 可能离线。",
            "clean_text": "决定使用 Adapter。新想法：来源链接可支持 forget。风险：FreeTodo 可能离线。",
            "summary": "实现 Elfred FreeTodo Adapter",
            "entities": [{"type": "project", "text": "Elfred"}],
            "tasks": [{"task": "完成 Adapter 联调", "deadline": "明天", "project": "Elfred", "assignee": "unknown", "confidence": 0.91}],
        },
        "privacy": {
            "is_sensitive": False,
            "sensitivity_types": [],
            "action": "allow",
            "allowed_to_upload": False,
            "allowed_to_write_long_term_memory": False,
            "requires_user_confirmation": False,
        },
        "artifacts": {"screenshot_id": "test-shot"},
        "suggestions": {"memory_write_suggestions": [], "task_card_suggestions": [], "skill_candidate_suggestions": []},
        "status": "temporary_context",
    }
    for key, value in overrides.items():
        if key in event and isinstance(event[key], dict) and isinstance(value, dict):
            event[key].update(value)
        else:
            event[key] = value
    return event


@pytest.fixture
def event() -> dict[str, Any]:
    return make_event()


@pytest.fixture
def fake_client() -> InMemoryFreeTodoClient:
    return InMemoryFreeTodoClient()


@pytest.fixture
def service(tmp_path: Path, fake_client: InMemoryFreeTodoClient) -> AdapterService:
    settings = Settings(tmp_path / "elfred_adapter.db", "http://fake", "http://observer")
    return AdapterService(settings, fake_client)


@pytest.fixture
def copied_event(event: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(event)

