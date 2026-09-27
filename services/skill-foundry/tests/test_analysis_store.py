from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from adapter.storage import SQLiteStore


def test_existing_analysis_table_is_upgraded_in_place(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            """CREATE TABLE event_task_analyses (
            event_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            cloud_consent INTEGER NOT NULL,
            analysis_json TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO event_task_analyses VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-event",
                "succeeded",
                "hermes",
                "big-pickle",
                "source-1",
                1,
                "{}",
                None,
                "2026-07-14T10:00:00+08:00",
                "2026-07-14T10:00:00+08:00",
            ),
        )

    store = SQLiteStore(database)

    with store.connect() as conn:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(event_task_analyses)")
        }
    assert {
        "attempt_count",
        "next_attempt_at",
        "lease_until",
        "prompt_version",
        "schema_version",
    } <= columns
    item = store.task_analysis("legacy-event")
    assert item is not None
    assert item["attempt_count"] == 0
    assert item["prompt_version"] == "task-analysis-v1"
    assert item["schema_version"] == "1.0"


def test_analysis_queue_is_idempotent_leased_and_retryable(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")

    assert store.enqueue_task_analysis(
        "event-1", "hermes", "big-pickle", "source-1", True
    ) is True
    assert store.enqueue_task_analysis(
        "event-1", "hermes", "big-pickle", "source-1", True
    ) is False

    claimed = store.claim_task_analysis(
        lease_seconds=60, now="2026-07-14T10:00:00+08:00"
    )
    assert claimed is not None
    assert claimed["event_id"] == "event-1"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert store.claim_task_analysis(now="2026-07-14T10:00:30+08:00") is None

    assert store.fail_task_analysis(
        "event-1",
        "temporary model outage",
        retryable=True,
        next_attempt_at="2026-07-14T10:05:00+08:00",
    ) is True
    assert store.claim_task_analysis(now="2026-07-14T10:04:59+08:00") is None
    retried = store.claim_task_analysis(now="2026-07-14T10:05:00+08:00")
    assert retried is not None
    assert retried["attempt_count"] == 2

    assert store.complete_task_analysis(
        "event-1", {"context_kind": "task", "tasks": []}, status="succeeded_no_task"
    ) is True
    finished = store.task_analysis("event-1")
    assert finished is not None
    assert finished["status"] == "succeeded_no_task"
    assert finished["analysis"]["context_kind"] == "task"
    assert finished["lease_until"] is None
    assert store.claim_task_analysis(now="2026-07-14T10:10:00+08:00") is None

    assert store.enqueue_task_analysis(
        "event-1",
        "hermes",
        "big-pickle",
        "source-1",
        True,
        prompt_version="context-analysis-v2",
        schema_version="2.0",
    ) is True
    requeued = store.task_analysis("event-1")
    assert requeued is not None
    assert requeued["status"] == "pending"
    assert requeued["attempt_count"] == 0
    assert requeued["prompt_version"] == "context-analysis-v2"


def test_expired_running_analysis_is_reclaimed(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    store.enqueue_task_analysis(
        "event-stale", "hermes", "big-pickle", "source-stale", True
    )
    first = store.claim_task_analysis(
        lease_seconds=60, now="2026-07-14T11:00:00+08:00"
    )
    assert first is not None and first["attempt_count"] == 1

    reclaimed = store.claim_task_analysis(now="2026-07-14T11:01:00+08:00")
    assert reclaimed is not None
    assert reclaimed["event_id"] == "event-stale"
    assert reclaimed["attempt_count"] == 2


def test_publish_pending_analysis_is_reclaimed_after_process_restart(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    store.enqueue_task_analysis(
        "event-publish", "hermes", "hermes-chat", "source-publish", True
    )
    claimed = store.claim_task_analysis(now="2026-07-14T11:10:00+08:00")
    assert claimed is not None
    store.complete_task_analysis(
        "event-publish",
        {"publish_pending": True, "pending_task_ids": ["task-1"]},
        status="publish_pending",
    )

    reclaimed = store.claim_task_analysis(now="2026-07-14T11:10:01+08:00")

    assert reclaimed is not None
    assert reclaimed["event_id"] == "event-publish"
    assert reclaimed["attempt_count"] == 2
    assert reclaimed["analysis"]["pending_task_ids"] == ["task-1"]


def test_canonical_task_candidates_and_evidence_are_idempotent(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    created = store.upsert_canonical_task(
        "elfred-demo",
        title="Complete Elfred passive analysis",
        description="Initial observation",
        domain="work",
        project="Elfred",
        stage="todo",
        progress_percent=0,
        priority="high",
        confidence=0.91,
        freetodo_todo_id=12,
        freetodo_uid="elfred-task-demo",
        last_remote={"id": 12, "name": "Complete Elfred passive analysis"},
        metadata={"analysis_schema": "2.0"},
        observed_at="2026-07-14T12:00:00+08:00",
    )
    assert created["freetodo_uid"] == "elfred-task-demo"
    assert created["metadata"] == {"analysis_schema": "2.0"}

    updated = store.upsert_canonical_task(
        "elfred-demo",
        title="Complete Elfred passive analysis",
        domain="work",
        project="Elfred",
        stage="in_progress",
        progress_percent=50,
        priority="high",
        confidence=0.96,
        observed_at="2026-07-14T12:05:00+08:00",
    )
    assert updated["stage"] == "in_progress"
    assert updated["progress_percent"] == 50
    assert updated["freetodo_todo_id"] == 12
    assert updated["freetodo_uid"] == "elfred-task-demo"
    assert updated["metadata"] == {"analysis_schema": "2.0"}
    assert updated["last_remote"]["id"] == 12

    store.upsert_canonical_task(
        "archived-task",
        title="Archived task",
        record_status="archived",
        observed_at="2026-07-14T12:10:00+08:00",
    )
    assert [item["task_id"] for item in store.canonical_task_candidates()] == [
        "elfred-demo"
    ]
    assert {
        item["task_id"]
        for item in store.canonical_task_candidates(include_archived=True)
    } == {"elfred-demo", "archived-task"}

    evidence_id = store.upsert_task_evidence(
        "elfred-demo",
        "event-1",
        "observation-1",
        relation="same_task",
        confidence=0.88,
        evidence={"summary": "Started implementation"},
    )
    repeated_id = store.upsert_task_evidence(
        "elfred-demo",
        "event-1",
        "observation-1",
        relation="progress_update",
        confidence=0.95,
        evidence={"summary": "Implementation is in progress"},
    )
    assert repeated_id == evidence_id
    evidence = store.task_evidence(task_id="elfred-demo")
    assert len(evidence) == 1
    assert evidence[0]["relation"] == "progress_update"
    assert evidence[0]["evidence"] == {
        "summary": "Implementation is in progress"
    }


def test_canonical_task_json_is_stored_as_structured_data(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    store.upsert_canonical_task(
        "structured",
        title="Structured task",
        metadata={"domain_reason": "work document", "labels": ["Elfred", "demo"]},
    )
    with store.connect() as conn:
        raw = conn.execute(
            "SELECT metadata_json FROM canonical_tasks WHERE task_id='structured'"
        ).fetchone()[0]
    assert json.loads(raw)["labels"] == ["Elfred", "demo"]


def test_legacy_todo_link_can_be_found_for_safe_canonical_adoption(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    legacy_brand = "Al" + "fred"
    legacy_prefix = legacy_brand.casefold()
    remote = {
        "id": 17,
        "uid": f"{legacy_prefix}-old-event-task",
        "name": f"旧 {legacy_brand} 任务",
        "status": "active",
    }
    store.upsert_remote_link(
        "todo",
        "old-event",
        "old-task-key",
        17,
        remote["uid"],
        "synced",
        remote,
    )

    link = store.todo_link_by_remote_id(17)

    assert link is not None
    assert link["event_id"] == "old-event"
    assert link["last_remote"] == remote
