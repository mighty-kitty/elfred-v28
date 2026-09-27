from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from adapter.task_analyzer import (
    HermesTaskAnalyzer,
    TaskAnalysis,
    is_task_analysis_candidate,
)
from conftest import make_event


class FakeHermesClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response
        self.created_sources: list[str] = []
        self.chat_calls: list[tuple[str, str]] = []
        self.deleted_sessions: list[str] = []

    def create_session(self, *, source: str) -> dict[str, Any]:
        self.created_sources.append(source)
        return {"id": "session-v2"}

    def chat(self, session_id: str, message: str) -> dict[str, Any]:
        self.chat_calls.append((session_id, message))
        if self.response is None:
            raise AssertionError("unexpected Hermes chat call")
        return self.response

    def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True


def analyzer(client: FakeHermesClient | None = None) -> HermesTaskAnalyzer:
    return HermesTaskAnalyzer(
        "http://127.0.0.1:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        reasoning_effort="low",
        client=client or FakeHermesClient(),
    )


def test_task_analysis_v2_fields_are_backward_compatible() -> None:
    legacy = TaskAnalysis(
        provider="hermes",
        model="test-model",
        is_task_context=False,
        summary="没有任务",
        reason="只是参考资料",
        tasks=[],
    )

    assert legacy.context_kind == "unknown"
    assert legacy.domain == "uncategorized"
    assert legacy.to_dict()["context_kind"] == "unknown"


def test_candidate_gate_admits_all_safe_text_but_blocks_private_or_empty_events() -> None:
    ordinary = make_event("ordinary")
    ordinary["app"].update(
        {"name": "Calculator", "process_name": "Calculator.exe", "category": "unknown"}
    )
    ordinary["content"]["clean_text"] = "42"

    sensitive = deepcopy(ordinary)
    sensitive["privacy"].update({"is_sensitive": True, "action": "block"})
    empty = deepcopy(ordinary)
    empty["content"]["clean_text"] = "  "
    messaging = deepcopy(ordinary)
    messaging["app"].update(
        {"name": "Weixin", "process_name": "Weixin.exe", "category": "messaging"}
    )

    assert is_task_analysis_candidate(ordinary) is True
    assert is_task_analysis_candidate(sensitive) is False
    assert is_task_analysis_candidate(empty) is False
    assert is_task_analysis_candidate(messaging) is False


def test_v2_normalization_strictly_bounds_enums_numbers_matches_and_evidence() -> None:
    result = analyzer()._normalize(
        {
            "context_kind": "ACTION-ITEM",
            "domain": "学习提升",
            "is_task_context": "true",
            "summary": "正在推进模型联调",
            "reason": "画面显示已开始执行",
            "tasks": [
                {
                    "task": "完成模型联调",
                    "priority": "urgent",
                    "confidence": "91%",
                    "stage": "doing",
                    "progress_percent": "125%",
                    "relation": "progress-update",
                    "matched_task_id": 42,
                    "match_confidence": 1.7,
                    "evidence": ["已启动联调", "已启动联调", 2, {"unsafe": "shape"}, "三", "四", "五", "六"],
                },
                {
                    "task": "另一个任务",
                    "stage": "DONE",
                    "progress_percent": -9,
                    "relation": "duplicate",
                    "matched_task_id": "../not-a-candidate",
                    "match_confidence": 0.99,
                },
            ],
        },
        existing_task_ids={"42"},
    )

    assert result.context_kind == "task"
    assert result.domain == "learning"
    first, second = result.tasks
    assert first["priority"] == "none"
    assert first["confidence"] == 0.91
    assert first["stage"] == "in_progress"
    assert first["progress_percent"] == 100
    assert first["relation"] == "update"
    assert first["matched_task_id"] == "42"
    assert first["match_confidence"] == 1.0
    assert first["evidence"] == ["已启动联调", "2", "三", "四", "五"]
    assert second["stage"] == "completed"
    assert second["progress_percent"] == 0
    assert second["relation"] == "new"
    assert second["matched_task_id"] is None
    assert second["match_confidence"] == 0.0


def test_analyze_passes_bounded_existing_candidates_and_accepts_only_their_ids() -> None:
    client = FakeHermesClient(
        {
            "message": {
                "content": json.dumps(
                    {
                        "context_kind": "task",
                        "domain": "work",
                        "is_task_context": True,
                        "summary": "已有任务取得进展",
                        "reason": "画面和候选任务语义一致",
                        "tasks": [
                            {
                                "task": "完善 Elfred 模型分析",
                                "stage": "in_progress",
                                "progress_percent": 60,
                                "relation": "update",
                                "matched_task_id": "7",
                                "match_confidence": 0.94,
                                "evidence": ["正在修改分析器"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            }
        }
    )
    model = analyzer(client)
    result = model.analyze(
        make_event("v2-existing-task"),
        existing_tasks=[
            {
                "id": 7,
                "title": "完善 Elfred 模型分析",
                "status": "doing",
                "progress_percent": 40,
                "category": "工作项目",
            },
            {"id": "bad id with spaces", "title": "无效候选"},
        ],
    )

    assert client.created_sources == ["api_server"]
    prompt = client.chat_calls[0][1]
    assert '<EXISTING_TASK_CANDIDATES>' in prompt
    assert '"id":"7"' in prompt
    assert "bad id with spaces" not in prompt
    assert result.tasks[0]["relation"] == "update"
    assert result.tasks[0]["matched_task_id"] == "7"
    assert client.deleted_sessions == ["session-v2"]
