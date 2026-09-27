from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adapter.config import Settings
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.observer_sync import ObserverAutoSync
from adapter.privacy import decide, safe_event_view
from adapter.service import AdapterService
from adapter.task_analyzer import HermesTaskAnalyzer, TaskAnalysis, TaskAnalysisError
from adapter.task_analyzer import is_task_analysis_candidate
from conftest import make_event


class FakeHermesClient:
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self.responses = list(responses or [])
        self.created_sources: list[str] = []
        self.chat_calls: list[tuple[str, str]] = []
        self.deleted_sessions: list[str] = []

    def create_session(self, *, source: str) -> dict[str, Any]:
        self.created_sources.append(source)
        return {"id": "session-123"}

    def chat(self, session_id: str, message: str) -> dict[str, Any]:
        self.chat_calls.append((session_id, message))
        if not self.responses:
            raise AssertionError("unexpected Hermes chat call")
        return self.responses.pop(0)

    def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True


class FakeAnalyzer:
    def __init__(self, tasks: list[dict[str, Any]]) -> None:
        self.tasks = tasks
        self.calls: list[dict[str, Any]] = []

    def _make_analysis(self) -> TaskAnalysis:
        return TaskAnalysis(
            provider="hermes",
            model="test-model",
            is_task_context=bool(self.tasks),
            summary="模型识别到真实任务" if self.tasks else "当前画面没有用户任务",
            reason="依据对话中的用户明确请求判断",
            tasks=self.tasks,
        )

    def analyze(self, event: dict[str, Any]) -> TaskAnalysis:
        self.calls.append(event)
        return self._make_analysis()

    def analyze_batch(
        self, batch: list[tuple[dict[str, Any], list[dict[str, Any]]]]
    ) -> list[TaskAnalysis]:
        return [self._make_analysis() for _ in batch]


class FailingAnalyzer:
    def analyze(self, event: dict[str, Any]) -> TaskAnalysis:
        raise TaskAnalysisError("model unavailable")


def llm_settings(
    tmp_path: Path,
    *,
    consent: bool = True,
    auto_sync: float = 0.0,
    allowed_apps: tuple[str, ...] = (),
) -> Settings:
    return Settings(
        tmp_path / "adapter.db",
        "http://fake",
        "http://observer",
        llm_provider="hermes",
        llm_cloud_consent=consent,
        task_analysis_cloud_apps=allowed_apps,
        observer_auto_sync_interval_seconds=auto_sync,
    )


def test_llm_tasks_replace_mechanical_tasks_and_are_audited(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer(
        [
            {
                "task": "完成 Elfred 截图任务分析联调",
                "description": "验证真实截图、OCR、模型与看板闭环",
                "deadline": None,
                "assignee": "unknown",
                "project": "Elfred",
                "priority": "high",
                "confidence": 0.96,
                "analysis_source": "llm",
            }
        ]
    )
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, analyzer)
    event = make_event("llm-task-1")
    event["content"]["tasks"] = [{"task": "机械规则误判", "confidence": 0.72}]

    result = service.process_payload(event)

    assert result.status == "synced"
    assert len(analyzer.calls) == 1
    assert [todo["name"] for todo in client.todos.values()] == ["完成 Elfred 截图任务分析联调"]
    stored = service.store.task_analysis(event["event_id"])
    assert stored is not None
    assert stored["status"] == "succeeded"
    assert stored["provider"] == "hermes"
    assert stored["model"] == "test-model"
    assert stored["analysis"]["task_count"] == 1


def test_synchronous_analysis_respects_cloud_app_allowlist(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([])
    service = AdapterService(
        llm_settings(tmp_path, allowed_apps=("WeChat", "Weixin", "微信")),
        InMemoryFreeTodoClient(),
        analyzer,
    )
    event = make_event("sync-edge-not-authorized")
    event["app"].update(
        {"name": "Microsoft Edge", "process_name": "msedge.exe", "category": "browser"}
    )

    result = service.process_payload(event)

    assert result.status == "synced"
    assert analyzer.calls == []
    stored = service.store.task_analysis(event["event_id"])
    assert stored and stored["status"] == "skipped_no_cloud_consent"
    assert stored["cloud_consent"] is False
    assert stored["analysis"]["task_count"] == 0


def test_model_can_reject_false_positive_task(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([])
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, analyzer)
    event = make_event("llm-no-task")
    event["content"]["tasks"] = [{"task": "网页中的示例待办", "confidence": 0.72}]

    result = service.process_payload(event)

    assert result.status == "synced"
    assert result.todo_ids == []
    assert client.todos == {}
    assert service.store.task_analysis(event["event_id"])["analysis"]["task_count"] == 0


def test_model_never_receives_sensitive_event(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([])
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, analyzer)
    event = make_event("llm-sensitive")
    event["privacy"].update(
        {"is_sensitive": True, "sensitivity_types": ["credential"], "action": "block"}
    )

    result = service.process_payload(event)

    assert result.status == "privacy_blocked"
    assert analyzer.calls == []
    assert service.store.task_analysis(event["event_id"]) is None


def test_unlabelled_provider_token_is_blocked_before_model_and_audit_is_safe(
    tmp_path: Path,
) -> None:
    synthetic_token = "sk-" + "Ab3" * 10
    analyzer = FakeAnalyzer([])
    service = AdapterService(
        llm_settings(tmp_path), InMemoryFreeTodoClient(), analyzer
    )
    event = make_event("llm-standalone-token")
    event["content"]["clean_text"] = f"temporary credential {synthetic_token}"
    event["content"]["raw_text"] = event["content"]["clean_text"]

    privacy = decide(event)
    safe_event, redactions = safe_event_view(event)
    result = service.enqueue_payload(event)

    assert privacy.local_allowed is False
    assert privacy.reason == "credential_pattern"
    assert synthetic_token not in json.dumps(safe_event, ensure_ascii=False)
    assert "provider_token" in redactions
    assert result.status == "privacy_blocked"
    assert analyzer.calls == []
    with service.store.connect() as conn:
        audit_safe = " ".join(
            str(row[0])
            for row in conn.execute(
                "SELECT redactions_json FROM privacy_decisions WHERE event_id=?",
                (event["event_id"],),
            ).fetchall()
        )
        analysis_safe = " ".join(
            str(row[0])
            for row in conn.execute(
                "SELECT analysis_json FROM event_task_analyses WHERE event_id=?",
                (event["event_id"],),
            ).fetchall()
        )
    assert synthetic_token not in audit_safe
    assert synthetic_token not in analysis_safe


def test_private_messaging_and_desktop_shell_are_never_model_candidates() -> None:
    message = make_event("weixin-event")
    message["app"].update(
        {"name": "Weixin", "process_name": "Weixin.exe", "category": "im_collaboration"}
    )
    desktop = make_event("explorer-event")
    desktop["app"].update(
        {"name": "explorer", "process_name": "explorer.exe", "category": "unknown"}
    )
    notepad = make_event("safe-notepad-event")
    notepad["app"].update(
        {"name": "Notepad", "process_name": "Notepad.exe", "category": "unknown"}
    )

    assert is_task_analysis_candidate(message) is False
    assert is_task_analysis_candidate(desktop) is False
    assert is_task_analysis_candidate(notepad) is True


def test_llm_requires_explicit_cloud_consent(tmp_path: Path) -> None:
    analyzer = FakeAnalyzer([])
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path, consent=False), client, analyzer)
    event = make_event("llm-no-consent")

    result = service.process_payload(event)

    assert analyzer.calls == []
    assert "llm_analysis_skipped_no_cloud_consent" in result.warnings
    assert service.store.task_analysis(event["event_id"])["status"] == "skipped_no_cloud_consent"
    assert client.todos == {}


def test_llm_failure_does_not_publish_mechanical_tasks(tmp_path: Path) -> None:
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, FailingAnalyzer())
    event = make_event("llm-failed")
    event["content"]["tasks"] = [{"task": "机械规则误判", "confidence": 0.99}]

    result = service.process_payload(event)

    assert any(item.startswith("llm_analysis_failed:") for item in result.warnings)
    assert client.todos == {}
    assert service.store.task_analysis(event["event_id"])["status"] == "failed"


def test_hermes_contract_uses_api_session_and_fresh_session() -> None:
    client = FakeHermesClient(
        [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "is_task_context": True,
                            "summary": "发现一个任务",
                            "reason": "用户明确要求完成联调",
                            "tasks": [
                                {
                                    "task": "完成真实模型联调",
                                    "description": "来自 OCR",
                                    "deadline": None,
                                    "project": "Elfred",
                                    "assignee": None,
                                    "priority": "high",
                                    "confidence": 0.93,
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    )
    analyzer = HermesTaskAnalyzer(
        "http://127.0.0.1:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        reasoning_effort="low",
        client=client,
    )
    event = make_event("hermes-contract")

    result = analyzer.analyze(event)

    assert result.tasks[0]["task"] == "完成真实模型联调"
    assert result.provider == "sub2api"
    assert result.model == "test-model"
    assert client.created_sources == ["api_server"]
    assert client.chat_calls[0][0] == "session-123"
    assert "<OCR_DATA>" in client.chat_calls[0][1]
    assert client.deleted_sessions == ["session-123"]


def test_cleanup_failure_does_not_turn_success_into_analysis_failure(monkeypatch) -> None:
    client = FakeHermesClient(
        [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "is_task_context": False,
                            "summary": "no task",
                            "reason": "reference only",
                            "tasks": [],
                        }
                    )
                }
            }
        ]
    )
    analyzer = HermesTaskAnalyzer(
        "http://127.0.0.1:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        client=client,
    )
    cleanup_calls: list[str] = []

    def failing_cleanup(session_id: str) -> None:
        cleanup_calls.append(session_id)
        raise OSError("cleanup unavailable")

    monkeypatch.setattr(analyzer, "_delete_session", failing_cleanup)

    result = analyzer.analyze(make_event("cleanup-success"))

    assert result.is_task_context is False
    assert cleanup_calls == ["session-123"]


def test_model_failure_is_preserved_when_session_cleanup_also_fails(monkeypatch) -> None:
    client = FakeHermesClient(
        [{"message": {"content": "not valid json"}}]
    )
    analyzer = HermesTaskAnalyzer(
        "http://127.0.0.1:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        client=client,
    )
    cleanup_calls: list[str] = []

    def failing_cleanup(session_id: str) -> None:
        cleanup_calls.append(session_id)
        raise OSError("cleanup unavailable")

    monkeypatch.setattr(analyzer, "_delete_session", failing_cleanup)

    with pytest.raises(TaskAnalysisError, match="Model response is not valid JSON"):
        analyzer.analyze(make_event("cleanup-original-error"))

    assert cleanup_calls == ["session-123"]


def test_reconcile_failure_schedules_automatic_retry(tmp_path: Path, monkeypatch) -> None:
    """A projection failure remains retryable and keeps the model result."""
    analyzer = FakeAnalyzer([
        {"task": "修复 Elfred 捕获库分析展示问题", "confidence": 0.85}
    ])
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, analyzer)
    event = make_event("reconcile-fails")
    event["content"]["clean_text"] = "在 VS Code 中修复 Elfred 捕获库问题"

    # 先持久化事件到 store
    from adapter.contracts import normalize_event_payload
    from adapter.privacy import safe_event_view
    _, canonical, digest = normalize_event_payload(event)
    service.store.ingest_event(canonical, digest)
    safe, _ = safe_event_view(canonical["event"])

    # 手动入队分析
    service.store.upsert_task_analysis(
        event["event_id"], "pending", "hermes", "test-model",
        digest, cloud_consent=True, analysis={"task_count": 0},
        prompt_version="v1", schema_version="1.0"
    )

    # Mock reconcile 抛异常
    def failing_reconcile(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("FreeTodo temporarily unavailable")
    monkeypatch.setattr(service, "_reconcile_model_tasks", failing_reconcile)

    # Mock claim 返回预置数据
    claimed = {"event_id": event["event_id"], "cloud_consent": True}
    monkeypatch.setattr(service.store, "claim_task_analysis", lambda **_kw: claimed)
    monkeypatch.setattr(service.store, "get_event", lambda _eid: {
        "payload": {"event": safe},
        "event_id": event["event_id"]
    })

    # 手动触发批量分析
    service.process_analysis_batch([claimed])

    stored = service.store.task_analysis(event["event_id"])
    assert stored is not None
    assert stored["status"] == "failed_retryable"
    assert stored["analysis"]["task_count"] == 1
    assert stored["next_attempt_at"] is not None


def test_batch_reconcile_creates_freetodo_tasks(tmp_path: Path) -> None:
    """reconcile 成功后 FreeTodo 中出现模型分析出的任务"""
    analyzer = FakeAnalyzer([
        {"task": "给 Elfred 加批量分析测试", "confidence": 0.93}
    ])
    client = InMemoryFreeTodoClient()
    service = AdapterService(llm_settings(tmp_path), client, analyzer)
    event = make_event("batch-reconcile-ok")
    event["content"]["clean_text"] = "正在给 Elfred 的批量分析加测试"

    from adapter.contracts import normalize_event_payload
    from adapter.privacy import safe_event_view
    _, canonical, digest = normalize_event_payload(event)
    service.store.ingest_event(canonical, digest)
    safe, _ = safe_event_view(canonical["event"])

    service.store.upsert_task_analysis(
        event["event_id"], "pending", "hermes", "test-model",
        digest, cloud_consent=True, analysis={"task_count": 0},
        prompt_version="v1", schema_version="1.0"
    )

    claimed = {"event_id": event["event_id"], "cloud_consent": True}
    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(service.store, "claim_task_analysis", lambda **_kw: claimed)
    monkeypatch.setattr(service.store, "get_event", lambda _eid: {
        "payload": {"event": safe},
        "event_id": event["event_id"]
    })

    # 跑批量分析 → reconcile 应成功
    service.process_analysis_batch([claimed])

    # 验证：分析状态 succeeded，不崩（之前传 analysis.tasks 会 AttributeError）
    stored = service.store.task_analysis(event["event_id"])
    assert stored["status"] == "succeeded", (
        f"分析应为 succeeded（reconcile 不覆盖），实际: {stored['status']}"
    )
    assert len(client.todos) == 1
    published = next(iter(client.todos.values()))
    assert published["name"] == "给 Elfred 加批量分析测试"
    assert published["source_type"] == "elfred_analysis"
    assert published["workflow_stage"] == "not_started"


def test_observer_auto_sync_baselines_old_events_then_processes_new(tmp_path: Path, monkeypatch) -> None:
    class Service:
        def __init__(self) -> None:
            self.settings = llm_settings(tmp_path, auto_sync=1.0)
            self.processed: list[str] = []

        def process_payload(self, event: dict[str, Any]) -> None:
            self.processed.append(event["event_id"])

    service = Service()
    sync = ObserverAutoSync(service)
    batches = [
        [{"event_id": "old-event"}],
        [{"event_id": "new-event"}, {"event_id": "old-event"}],
    ]
    monkeypatch.setattr(sync, "_fetch_events", lambda: batches.pop(0))

    assert sync.poll_once() == {"baseline": 1, "processed": 0}
    assert sync.poll_once() == {"baseline": 0, "processed": 1}
    assert service.processed == ["new-event"]
