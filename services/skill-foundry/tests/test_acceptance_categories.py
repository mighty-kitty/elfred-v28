from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.config import Settings
from adapter.contracts import normalize_event_payload
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.scripts.migrate_legacy import migrate, rollback
from adapter.service import AdapterService
from conftest import make_event


def test_01_current_real_observer_context_event_imports(tmp_path: Path) -> None:
    project = Path(__file__).resolve()
    legacy_observer = ("al" + "fred") + "_desktop_observer"
    candidates = [
        project.parents[3] / "elfred-observer" / "context_event.json",
        project.parents[2] / "alfred-observer" / "context_event.json",
        project.parents[2] / legacy_observer / "samples" / "context_event.json",
    ]
    sample_path = next((path for path in candidates if path.exists()), candidates[0])
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    service = AdapterService(Settings(tmp_path / "real.db", "fake", "observer"), InMemoryFreeTodoClient())
    result = service.process_payload(payload)
    assert result.status == "synced"
    assert len(result.todo_ids) == 2


def test_02_unknown_fields_are_preserved(service: AdapterService, event: dict) -> None:
    event["future_contract"] = {"new_field": 42}
    service.process_payload(event)
    stored = service.store.get_event(event["event_id"])
    assert stored["payload"]["event"]["future_contract"]["new_field"] == 42


def test_03_same_event_is_idempotent(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    first = service.process_payload(event)
    second = service.process_payload(deepcopy(event))
    assert first.status == "synced" and second.status == "duplicate"
    assert len(fake_client.todos) == 1 and len(fake_client.journals) == 1


def test_04_same_id_different_payload_conflicts(service: AdapterService, event: dict) -> None:
    service.process_payload(event)
    changed = deepcopy(event)
    changed["content"]["summary"] = "different"
    assert service.process_payload(changed).status == "conflict"
    assert service.store.get_event(event["event_id"])["status"] == "conflict"


def test_05_low_confidence_task_becomes_draft(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    event["content"]["tasks"][0]["confidence"] = 0.2
    service.process_payload(event)
    assert next(iter(fake_client.todos.values()))["status"] == "draft"


def test_06_upload_false_never_enables_cloud(service: AdapterService, event: dict) -> None:
    service.process_payload(event)
    item = service.store.outbox("memory")[0]
    assert item["payload"]["cloud_allowed"] is False
    with service.store.connect() as conn:
        decision = conn.execute("SELECT cloud_allowed FROM privacy_decisions").fetchone()
    assert decision[0] == 0


def test_07_sensitive_content_never_reaches_freetodo(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    event["content"]["clean_text"] = "password=TOPSECRET"
    event["privacy"].update({"is_sensitive": True, "sensitivity_types": ["credential"], "action": "block"})
    assert service.process_payload(event).status == "privacy_blocked"
    assert not fake_client.todos and not fake_client.journals
    assert service.store.outbox("memory") == []


def test_08_context_event_creates_todo(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    result = service.process_payload(event)
    todo = fake_client.get_todo(result.todo_ids[0])
    assert todo["name"] == "完成 Adapter 联调"
    assert event["event_id"] in todo["user_notes"]


def test_09_context_event_creates_journal(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    result = service.process_payload(event)
    journal = fake_client.get_journal(result.journal_ids[0])
    assert journal["uid"] == "elfred-daily-2026-07-13"
    assert "来源索引" in journal["content_objective"]


def test_10_journal_relates_todo(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    result = service.process_payload(event)
    journal = fake_client.get_journal(result.journal_ids[0])
    assert journal["related_todo_ids"] == result.todo_ids


def test_11_topic_aliases_do_not_duplicate(service: AdapterService) -> None:
    first = make_event("alias-1")
    first["content"]["tasks"][0]["project"] = "阿福"
    second = make_event("alias-2")
    second["content"]["tasks"][0]["project"] = "Personal Agent项目"
    service.process_payload(first)
    service.process_payload(second)
    assert "topic_elfred" in {x["topic_id"] for x in service.store.topics_for_event("alias-1")}
    assert "topic_elfred" in {x["topic_id"] for x in service.store.topics_for_event("alias-2")}


def test_12_daily_journal_is_idea_oriented(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    service.process_payload(event)
    content = next(iter(fake_client.journals.values()))["content_ai"]
    assert all(section in content for section in ("新想法与认识", "关键决策", "风险与卡点", "等待与依赖", "下一步"))


def test_13_weekly_report_is_synthesis_not_daily_concat(service: AdapterService, event: dict) -> None:
    service.process_payload(event)
    report = service.weekly_report(2026, 29)
    assert report["week"] == "2026-W29"
    assert report["main_threads"]
    assert "content_objective" not in report


def test_14_forget_deletes_unmodified_objects(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    service.process_payload(event)
    result = service.forget_event(event["event_id"])
    assert result["status"] == "completed"
    assert not fake_client.todos and not fake_client.journals


def test_15_manual_todo_edit_is_preserved_on_forget(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    result = service.process_payload(event)
    fake_client.todos[result.todo_ids[0]]["name"] = "用户手工修改"
    forgotten = service.forget_event(event["event_id"])
    assert forgotten["preserved_todo_ids"] == result.todo_ids
    assert fake_client.todos[result.todo_ids[0]]["name"] == "用户手工修改"


def test_16_freetodo_unavailable_enters_retry(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    fake_client.available = False
    result = service.process_payload(event)
    assert result.status == "retry"
    assert service.store.get_event(event["event_id"])["status"] == "retry"


def test_17_restart_recovers_idempotent_state(tmp_path: Path, event: dict) -> None:
    client = InMemoryFreeTodoClient()
    settings = Settings(tmp_path / "restart.db", "fake", "observer")
    first = AdapterService(settings, client)
    first.process_payload(event)
    restarted = AdapterService(settings, client)
    assert restarted.process_payload(event).status == "duplicate"
    assert len(client.todos) == 1


def test_18_reconcile_detects_orphan(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    result = service.process_payload(event)
    del fake_client.todos[result.todo_ids[0]]
    report = service.reconcile()
    assert report["counts"]["missing"] == 1


def test_19_memory_outbox_is_idempotent(service: AdapterService, event: dict) -> None:
    service.process_payload(event)
    service.process_payload(event)
    assert len(service.store.outbox("memory")) == 1


def test_20_personal_agent_outbox_is_idempotent(service: AdapterService, event: dict) -> None:
    service.process_payload(event)
    service.process_payload(event)
    assert len(service.store.outbox("personal_agent")) == 1


def _legacy_db(path: Path, event: dict) -> None:
    _, canonical, _ = normalize_event_payload(event)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ingested_events(event_id TEXT,payload_json TEXT,status TEXT,created_at TEXT)")
        conn.execute(
            "INSERT INTO ingested_events VALUES(?,?,?,?)",
            (event["event_id"], json.dumps(canonical, ensure_ascii=False), "processed", event["created_at"]),
        )


def test_21_legacy_migration_dry_run_has_no_writes(tmp_path: Path, service: AdapterService, event: dict) -> None:
    source = tmp_path / "legacy.db"
    _legacy_db(source, event)
    report = migrate(source, service, dry_run=True)
    assert report["legacy_counts"]["events"] == 1
    assert service.status()["counts"]["events"] == 0


def test_22_migration_rollback(tmp_path: Path, service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    source = tmp_path / "legacy.db"
    _legacy_db(source, event)
    report = migrate(source, service, dry_run=False)
    rolled = rollback(report["batch_id"], service)
    assert rolled["status"] == "rolled_back"
    assert not fake_client.todos and not fake_client.journals


def test_23_windows_unicode_path_supported(tmp_path: Path) -> None:
    path = tmp_path / "含 空格" / "elfred_adapter.db"
    service = AdapterService(Settings(path, "fake", "observer"), InMemoryFreeTodoClient())
    assert service.process_payload(make_event("windows-path")).status == "synced"
    assert path.exists()


def test_24_api_smoke(tmp_path: Path, event: dict) -> None:
    service = AdapterService(Settings(tmp_path / "api.db", "fake", "observer"), InMemoryFreeTodoClient())
    client = TestClient(create_app(service=service))
    assert client.get("/v1/elfred/health").status_code == 200
    created = client.post("/v1/elfred/events", json=event)
    assert created.status_code == 202
    assert client.get(f"/v1/elfred/events/{event['event_id']}/links").status_code == 200
    item_id = client.get("/v1/elfred/outbox/memory").json()["items"][0]["item_id"]
    assert client.post(f"/v1/elfred/outbox/{item_id}/ack").status_code == 200


def test_25_tests_use_no_paid_api(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    service.process_payload(event)
    assert service.settings.llm_provider == "deterministic"
    assert fake_client.calls
    assert all(path.startswith("/api/todos") or path.startswith("/api/journals") for _, path in fake_client.calls)


def test_manual_journal_edit_is_not_overwritten(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    first = service.process_payload(event)
    journal_id = first.journal_ids[0]
    fake_client.journals[journal_id]["content_ai"] = "用户自己的日记"
    second = make_event("second-event")
    result = service.process_payload(second)
    assert "journal_manual_modification_preserved" in result.warnings
    assert fake_client.journals[journal_id]["content_ai"] == "用户自己的日记"


def test_pii_is_redacted_from_todo_and_journal(service: AdapterService, fake_client: InMemoryFreeTodoClient, event: dict) -> None:
    event["content"]["summary"] = "联系 13800138000 或 owner@example.com"
    event["content"]["clean_text"] = event["content"]["summary"]
    event["content"]["tasks"][0]["task"] = "发邮件给 owner@example.com"
    service.process_payload(event)
    blob = json.dumps({"todos": fake_client.todos, "journals": fake_client.journals}, ensure_ascii=False)
    assert "13800138000" not in blob and "owner@example.com" not in blob
