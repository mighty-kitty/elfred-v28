from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.config import Settings
from adapter.analysis_worker import AnalysisWorker
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.observer_sync import ObserverAutoSync
from adapter.service import AdapterService
from adapter.storage import SQLiteStore
from adapter.task_analyzer import TaskAnalysis, TaskAnalysisError
from conftest import make_event


class StageAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.candidate_batches: list[list[dict[str, Any]]] = []

    def analyze(
        self,
        event: dict[str, Any],
        existing_tasks: list[dict[str, Any]] | None = None,
    ) -> TaskAnalysis:
        candidates = list(existing_tasks or [])
        self.calls.append(event)
        self.candidate_batches.append(candidates)
        index = len(self.calls) - 1
        stages = [
            ("not_started", 0, "new"),
            ("in_progress", 55, "update"),
            ("completed", 100, "update"),
        ]
        stage, progress, relation = stages[index]
        matched_id = candidates[0]["id"] if candidates else None
        return TaskAnalysis(
            provider="hermes",
            model="hermes-chat",
            is_task_context=True,
            context_kind="task",
            domain="work",
            summary="正在推进 Elfred 被动任务分析",
            reason="截图包含同一项工作的阶段证据",
            tasks=[
                {
                    "task": "完成 Elfred 被动任务分析",
                    "description": "实现模型分类、阶段判断和同类合并",
                    "deadline": None,
                    "assignee": "unknown",
                    "project": "Elfred",
                    "priority": "high",
                    "confidence": 0.96,
                    "stage": stage,
                    "progress_percent": progress,
                    "relation": relation,
                    "matched_task_id": matched_id,
                    "match_confidence": 0.97 if matched_id else 0,
                    "evidence": ["无敏感内容的测试画面显示工作阶段"],
                    "analysis_source": "llm",
                }
            ],
        )


class NonTaskAnalyzer:
    def analyze(
        self,
        event: dict[str, Any],
        existing_tasks: list[dict[str, Any]] | None = None,
    ) -> TaskAnalysis:
        return TaskAnalysis(
            provider="hermes",
            model="hermes-chat",
            is_task_context=False,
            context_kind="reference",
            domain="learning",
            summary="当前画面是参考资料",
            reason="没有用户承诺执行的行动项",
            tasks=[],
        )


class FailingAnalyzer:
    def analyze(
        self,
        event: dict[str, Any],
        existing_tasks: list[dict[str, Any]] | None = None,
    ) -> TaskAnalysis:
        raise TaskAnalysisError("temporary model failure")

    def analyze_batch(
        self,
        batch: list[tuple[dict[str, Any], list[dict[str, Any]]]],
    ) -> list[TaskAnalysis]:
        raise TaskAnalysisError("temporary model failure")


def passive_settings(tmp_path: Path, **values: Any) -> Settings:
    defaults = {
        "llm_provider": "hermes",
        "hermes_api_key": "local-test-key",
        "llm_provider_id": "test-provider",
        "llm_model_id": "test-model",
        "llm_cloud_consent": True,
        "analysis_worker_interval_seconds": 1.0,
        "analysis_retry_base_seconds": 0.0,
    }
    defaults.update(values)
    return Settings(
        tmp_path / "adapter.db",
        "http://fake",
        "http://observer",
        **defaults,
    )


def safe_stage_event(event_id: str, text: str) -> dict[str, Any]:
    event = make_event(event_id)
    event["content"].update(
        {
            "raw_text": text,
            "clean_text": text,
            "summary": text,
            "tasks": [{"task": "旧机械规则任务", "confidence": 0.99}],
        }
    )
    return event


def test_passive_pipeline_creates_then_updates_one_todo_across_screenshots(tmp_path: Path) -> None:
    analyzer = StageAnalyzer()
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, analyzer)

    first = service.enqueue_payload(safe_stage_event("passive-1", "准备实现被动任务分析。"))
    assert first.status == "analysis_pending"
    assert analyzer.calls == []
    first_result = service.process_next_analysis()

    assert first_result and first_result["status"] == "succeeded"
    assert len(client.todos) == 1
    todo_id = next(iter(client.todos))
    assert client.todos[todo_id]["name"] == "完成 Elfred 被动任务分析"
    assert client.todos[todo_id]["percent_complete"] == 0
    assert client.todos[todo_id]["categories"] == "工作项目"

    service.enqueue_payload(safe_stage_event("passive-2", "该功能已经进入编码阶段。"))
    second_result = service.process_next_analysis()
    assert second_result and second_result["status"] == "succeeded"
    assert len(client.todos) == 1
    assert client.todos[todo_id]["status"] == "active"
    assert client.todos[todo_id]["percent_complete"] == 55

    service.enqueue_payload(safe_stage_event("passive-3", "该功能已经完成。"))
    third_result = service.process_next_analysis()
    assert third_result and third_result["status"] == "succeeded"
    assert len(client.todos) == 1
    assert client.todos[todo_id]["status"] == "completed"
    assert client.todos[todo_id]["percent_complete"] == 100

    canonical = service.store.canonical_task_candidates()
    assert len(canonical) == 1
    assert canonical[0]["stage"] == "completed"
    assert len(service.store.task_evidence(task_id=canonical[0]["task_id"])) == 3
    assert [method for method, path in client.calls if path.startswith("/api/todos")] == [
        "POST",
        "PUT",
        "PUT",
    ]
    assert analyzer.candidate_batches[0] == []
    assert analyzer.candidate_batches[1][0]["id"] == canonical[0]["task_id"]


def test_non_task_context_is_classified_without_creating_todo(tmp_path: Path) -> None:
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, NonTaskAnalyzer())

    service.enqueue_payload(safe_stage_event("reference-1", "这里是一段学习参考资料。"))
    result = service.process_next_analysis()

    assert result and result["status"] == "succeeded_no_task"
    assert client.todos == {}
    stored = service.store.task_analysis("reference-1")
    assert stored and stored["analysis"]["context_kind"] == "reference"
    assert stored["analysis"]["domain"] == "learning"


def test_communication_uses_model_after_explicit_cloud_consent(
    tmp_path: Path,
) -> None:
    analyzer = StageAnalyzer()
    client = InMemoryFreeTodoClient()
    service = AdapterService(
        passive_settings(
            tmp_path,
            task_analysis_cloud_apps=("WeChat", "Weixin", "微信"),
        ),
        client,
        analyzer,
    )
    event = safe_stage_event(
        "private-chat-1",
        "我现在需要进行生物医学工程的一篇博\n士论文的审阅，这篇论文研究的是肺部成像。",
    )
    event["content"]["tasks"] = [
        {"task": "我现在需要进行..", "confidence": 0.72},
        {
            "task": "我现在需要进行生物医学工程的一篇博",
            "confidence": 0.72,
        },
    ]
    event["suggestions"]["task_card_suggestions"] = list(
        event["content"]["tasks"]
    )
    event["app"].update(
        {"name": "Weixin", "process_name": "Weixin.exe", "category": "im_collaboration"}
    )

    queued = service.enqueue_payload(event)
    result = service.process_next_analysis()

    assert queued.status == "analysis_pending"
    assert result and result["status"] == "succeeded"
    assert len(analyzer.calls) == 1
    assert len(client.todos) == 1
    todo = next(iter(client.todos.values()))
    assert todo["name"]
    stored = service.store.task_analysis("private-chat-1")
    assert stored and stored["provider"] == "test-provider"
    assert stored["cloud_consent"] is True


def test_cloud_app_allowlist_prevents_unapproved_edge_analysis(
    tmp_path: Path,
) -> None:
    analyzer = StageAnalyzer()
    service = AdapterService(
        passive_settings(
            tmp_path,
            task_analysis_cloud_apps=("WeChat", "Weixin", "微信"),
        ),
        InMemoryFreeTodoClient(),
        analyzer,
    )
    event = safe_stage_event(
        "edge-not-authorized",
        "Review the current browser page and create a follow-up task.",
    )
    event["app"].update(
        {"name": "Microsoft Edge", "process_name": "msedge.exe", "category": "browser"}
    )

    result = service.enqueue_payload(event)

    assert result.status == "skipped_no_cloud_consent"
    assert analyzer.calls == []
    stored = service.store.task_analysis("edge-not-authorized")
    assert stored and stored["cloud_consent"] is False


def test_offline_mode_still_queues_local_communication_tasks(
    tmp_path: Path,
) -> None:
    client = InMemoryFreeTodoClient()
    settings = passive_settings(
        tmp_path,
        llm_provider="deterministic",
        llm_cloud_consent=False,
    )
    service = AdapterService(settings, client)
    event = safe_stage_event(
        "offline-chat-1",
        "我需要完成本地任务同步。",
    )
    event["app"].update(
        {"name": "Weixin", "process_name": "Weixin.exe", "category": "im_collaboration"}
    )
    event["content"]["tasks"] = [
        {"task": "完成本地任务同步", "confidence": 0.91}
    ]

    queued = service.enqueue_payload(event)
    result = service.process_next_analysis()

    assert queued.status == "analysis_pending"
    assert result and result["status"] == "succeeded"
    assert len(client.todos) == 1
    stored = service.store.task_analysis("offline-chat-1")
    assert stored and stored["cloud_consent"] is False
    retried = service.retry_event("offline-chat-1")
    assert retried.status == "analysis_pending"
    assert service.process_next_analysis()["status"] == "succeeded"
    assert len(client.todos) == 1


def test_model_failure_retries_then_becomes_terminal(tmp_path: Path) -> None:
    service = AdapterService(
        passive_settings(tmp_path, analysis_max_attempts=2),
        InMemoryFreeTodoClient(),
        FailingAnalyzer(),
    )
    service.enqueue_payload(safe_stage_event("retry-model-1", "安全的重试测试。"))

    first = service.process_next_analysis()
    second = service.process_next_analysis()

    assert first and first["status"] == "failed_retryable"
    assert second and second["status"] == "failed_terminal"
    assert service.store.task_analysis("retry-model-1")["attempt_count"] == 2


def test_worker_keeps_model_failure_visible_while_retry_is_waiting(tmp_path: Path) -> None:
    service = AdapterService(
        passive_settings(tmp_path, analysis_retry_base_seconds=60),
        InMemoryFreeTodoClient(),
        FailingAnalyzer(),
    )
    service.enqueue_payload(safe_stage_event("retry-visible-1", "安全的失败状态测试。"))
    worker = AnalysisWorker(service)

    # 第一轮：批量分析内部捕获了 TaskAnalysisError，标记事件为 failed_retryable
    result = worker.process_once()
    assert result and result["status"] == "processed"

    # 验证事件已被标记为可重试
    analysis = service.store.task_analysis("retry-visible-1")
    assert analysis is not None
    assert analysis["status"] == "failed_retryable"
    assert "temporary model failure" in str(analysis.get("error", ""))

    # 第二轮：retry timer 未到期，无事件可处理
    idle = worker.process_once()
    assert idle is None


def test_feed_backfill_persists_cursor_and_enqueues_in_order(tmp_path: Path, monkeypatch) -> None:
    class FeedService:
        def __init__(self) -> None:
            self.settings = passive_settings(
                tmp_path,
                observer_auto_sync_interval_seconds=1.0,
                observer_auto_sync_backfill=True,
            )
            self.store = SQLiteStore(tmp_path / "feed-state.db")
            self.events: list[str] = []

        def enqueue_payload(self, event: dict[str, Any]) -> None:
            self.events.append(event["event_id"])

        def process_payload(self, event: dict[str, Any]) -> None:
            raise AssertionError("feed mode must enqueue instead of synchronous processing")

    service = FeedService()
    sync = ObserverAutoSync(service)
    monkeypatch.setattr(
        sync,
        "_fetch_feed",
        lambda: {
            "events": [{"event_id": "old-1"}, {"event_id": "old-2"}],
            "next_cursor": "cursor-2",
            "has_more": True,
            "total": 82,
        },
    )

    result = sync.poll_once()

    assert result == {"baseline": 0, "processed": 2, "has_more": True}
    assert service.events == ["old-1", "old-2"]
    assert service.store.get_setting("observer_auto_sync.feed_cursor.v1") == "cursor-2"
    assert sync.status()["state"] == "backfilling"


def test_recent_only_sync_enqueues_new_events_instead_of_using_legacy_sync(
    tmp_path: Path, monkeypatch
) -> None:
    class RecentService:
        def __init__(self) -> None:
            self.settings = passive_settings(
                tmp_path,
                observer_auto_sync_interval_seconds=1.0,
                observer_auto_sync_backfill=False,
            )
            self.enqueued: list[str] = []

        def enqueue_payload(self, event: dict[str, Any]) -> None:
            self.enqueued.append(event["event_id"])

        def process_payload(self, event: dict[str, Any]) -> None:
            raise AssertionError("recent-only mode must not use legacy synchronous processing")

    service = RecentService()
    sync = ObserverAutoSync(service)
    batches = [
        [{"event_id": "existing-event"}],
        [{"event_id": "new-event"}, {"event_id": "existing-event"}],
    ]
    monkeypatch.setattr(sync, "_fetch_events", lambda: batches.pop(0))

    assert sync.poll_once() == {"baseline": 1, "processed": 0}
    assert sync.poll_once() == {"baseline": 0, "processed": 1}
    assert service.enqueued == ["new-event"]


def test_single_json_import_uses_analysis_queue_when_real_analyzer_is_configured(
    tmp_path: Path,
) -> None:
    analyzer = StageAnalyzer()
    client = InMemoryFreeTodoClient()
    service = AdapterService(
        passive_settings(tmp_path, analysis_worker_interval_seconds=0),
        client,
        analyzer,
    )
    api = TestClient(create_app(service=service))

    response = api.post(
        "/v1/elfred/import/json",
        json=safe_stage_event("single-import-queue", "Implement passive task analysis."),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "analysis_pending"
    assert service.store.task_analysis("single-import-queue")["status"] == "pending"
    assert analyzer.calls == []
    assert client.todos == {}
    assert service.store.remote_links("single-import-queue")["todo"] == []


def test_retry_force_requeues_analysis_without_creating_legacy_event_todo(
    tmp_path: Path,
) -> None:
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, NonTaskAnalyzer())
    event = safe_stage_event("canonical-retry", "This is reference material, not a task.")
    service.enqueue_payload(event)
    assert service.process_next_analysis()["status"] == "succeeded_no_task"
    assert service.store.task_analysis("canonical-retry")["status"] == "succeeded_no_task"

    retried = service.retry_event("canonical-retry")

    assert retried.status == "analysis_pending"
    queued = service.store.task_analysis("canonical-retry")
    assert queued["status"] == "pending"
    assert queued["attempt_count"] == 0
    assert client.todos == {}
    assert service.store.remote_links("canonical-retry")["todo"] == []


def test_recovery_adopts_remote_write_that_succeeded_before_local_checkpoint(
    tmp_path: Path,
) -> None:
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, NonTaskAnalyzer())
    original = service.store.upsert_canonical_task(
        "task-recovered",
        title="完成 Elfred 被动任务分析",
        domain="work",
        project="Elfred",
        stage="not_started",
        progress_percent=0,
        confidence=0.95,
    )
    remote = client.create_todo(
        {
            "uid": original["freetodo_uid"],
            "name": original["title"],
            "description": None,
            "user_notes": "[ELFRED_TASK task_id=task-recovered]",
            "status": "active",
            "percent_complete": 0,
            "priority": "none",
            "due": None,
            "categories": "工作项目",
            "tags": ["工作项目", "Elfred"],
        }
    )
    service.store.upsert_canonical_task(
        "task-recovered",
        title=original["title"],
        domain="work",
        project="Elfred",
        stage="not_started",
        progress_percent=0,
        confidence=0.95,
        freetodo_todo_id=int(remote["id"]),
        last_remote=remote,
    )

    # Simulate: the stage update was stored, FreeTodo accepted the PUT, then the
    # Adapter process died before committing the new remote response hash.
    service.store.upsert_canonical_task(
        "task-recovered",
        title=original["title"],
        domain="work",
        project="Elfred",
        stage="in_progress",
        progress_percent=60,
        confidence=0.97,
    )
    client.todos[int(remote["id"])]["percent_complete"] = 60

    recovered = service._publish_canonical_task("task-recovered")

    assert recovered["status"] == "synced"
    assert service.store.canonical_task("task-recovered")["metadata"]["publish_state"] == "synced"


def test_stale_remote_id_never_overwrites_an_unrelated_todo(tmp_path: Path) -> None:
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, NonTaskAnalyzer())
    unrelated = client.create_todo(
        {"uid": "manual-unrelated", "name": "用户自己的任务", "description": "保留"}
    )
    task = service.store.upsert_canonical_task(
        "task-stale-link",
        title="修复 Elfred 任务看板",
        domain="work",
        project="Elfred",
        stage="in_progress",
        progress_percent=40,
        confidence=0.95,
        freetodo_todo_id=int(unrelated["id"]),
    )

    published = service._publish_canonical_task("task-stale-link")

    assert client.todos[int(unrelated["id"])]["name"] == "用户自己的任务"
    assert client.todos[int(unrelated["id"])]["description"] == "保留"
    assert published["todo_id"] != unrelated["id"]
    assert client.todos[int(published["todo_id"])]["uid"] == task["freetodo_uid"]
    assert len(client.todos) == 2


LEGACY_BRAND = "Al" + "fred"
LEGACY_PREFIX = LEGACY_BRAND.casefold()


def _legacy_branded_todo(client: InMemoryFreeTodoClient) -> dict[str, Any]:
    return client.create_todo(
        {
            "uid": f"{LEGACY_PREFIX}-old-event-old-task-key",
            "name": f"完成 {LEGACY_BRAND} 被动任务分析",
            "description": "旧版按事件生成的任务",
            "user_notes": "[ELFRED_SOURCE event_id=old-event task_key=old-task-key]",
            "status": "draft",
            "percent_complete": 0,
            "priority": "high",
            "due": None,
            "categories": "工作项目",
            "tags": ["工作项目"],
        }
    )


def test_legacy_branded_todo_is_adopted_instead_of_duplicated(tmp_path: Path) -> None:
    analyzer = StageAnalyzer()
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, analyzer)
    legacy = _legacy_branded_todo(client)
    service.store.upsert_remote_link(
        "todo",
        "old-event",
        "old-task-key",
        int(legacy["id"]),
        str(legacy["uid"]),
        "synced",
        legacy,
    )
    client.calls.clear()

    service.enqueue_payload(
        safe_stage_event("adoption-1", "正在推进完成 Elfred 被动任务分析。")
    )
    result = service.process_next_analysis()

    assert result and result["status"] == "succeeded"
    assert len(client.todos) == 1
    canonical = service.store.canonical_task_candidates()
    assert len(canonical) == 1
    assert canonical[0]["freetodo_todo_id"] == legacy["id"]
    assert canonical[0]["metadata"]["migrated_from"] == "legacy_product_todo"
    assert not any(method == "POST" for method, _ in client.calls)
    assert any(method == "PUT" for method, _ in client.calls)


def test_manually_modified_legacy_todo_is_adopted_but_not_overwritten(
    tmp_path: Path,
) -> None:
    analyzer = StageAnalyzer()
    client = InMemoryFreeTodoClient()
    service = AdapterService(passive_settings(tmp_path), client, analyzer)
    legacy = _legacy_branded_todo(client)
    service.store.upsert_remote_link(
        "todo",
        "old-event",
        "old-task-key",
        int(legacy["id"]),
        str(legacy["uid"]),
        "synced",
        legacy,
    )
    client.todos[int(legacy["id"])]["description"] = "用户手工保留的说明"
    client.calls.clear()

    service.enqueue_payload(
        safe_stage_event("adoption-manual-1", "正在推进完成 Elfred 被动任务分析。")
    )
    result = service.process_next_analysis()

    assert result and result["status"] == "succeeded"
    assert len(client.todos) == 1
    assert client.todos[int(legacy["id"])]["description"] == "用户手工保留的说明"
    assert not any(method in {"POST", "PUT"} for method, _ in client.calls)
    canonical = service.store.canonical_task_candidates()[0]
    assert canonical["metadata"]["publish_state"] == "manual_modified"
