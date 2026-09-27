from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.config import Settings
from adapter.contracts import normalize_event_payload
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.hardware_output.models import (
    ExecutePlanRequest,
    JournalSnapshot,
    PlanCreateRequest,
)
from adapter.hardware_output.adapters import AdapterCommand
from adapter.hardware_output.planner import HardwareActionPlanner
from adapter.hardware_output.routes import register_hardware_output_routes
from adapter.hardware_output.worker import HardwareOutputWorker
from adapter.journal.models import GenerateRequest
from adapter.service import AdapterService


def _journal() -> JournalSnapshot:
    return JournalSnapshot(
        journalId="journal-demo-2026-07-30",
        journalVersion="v1",
        date="2026-07-30",
        title="回家后的 Personal Journal",
        content="今天完成了 Elfred 联调，回到家后非常疲惫，很想有人帮我拿一下外套。",
        mood="疲惫",
        energy=2,
        tags=["Elfred", "demo"],
    )


def _service(tmp_path: Path) -> AdapterService:
    settings = Settings(
        tmp_path / "elfred_adapter.db",
        "http://fake",
        "http://observer",
        hardware_output_config_path=tmp_path / "hardware.local.json",
    )
    return AdapterService(settings, InMemoryFreeTodoClient())


def _journal_event() -> dict:
    return {
        "event_id": "journal-event-1",
        "created_at": "2026-07-30T20:00:00+08:00",
        "app": {"name": "Elfred", "category": "work"},
        "content": {
            "summary": "完成四硬件软件编排与联调准备",
            "tasks": [{"title": "验证 Journal 旁路集成"}],
        },
    }


def test_direct_route_registration_uses_elfred_prefix_by_default() -> None:
    app = FastAPI()
    register_hardware_output_routes(app, None)  # type: ignore[arg-type]

    assert "/v1/elfred/hardware-output/status" in {
        route.path for route in app.routes
    }


def _ingest_journal_event(service: AdapterService) -> None:
    _, canonical, digest = normalize_event_payload(_journal_event())
    service.store.ingest_event(canonical, digest)


def test_plan_is_traceable_and_only_contains_pc_owned_pendant(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = service.hardware_output.create_plan(
        PlanCreateRequest(journal=_journal())
    )

    assert plan["created"] is True
    assert plan["status"] == "ready"
    assert {action["adapter_id"] for action in plan["actions"]} == {"pendant"}
    assert plan["journal_hash"]
    assert plan["effective_mode"] == "deterministic"


def test_k3_owned_actions_cannot_be_queued_on_pc(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    for adapter_id in ("base", "arm", "printer"):
        adapter = service.hardware_output.registry.get(adapter_id)
        assert adapter.transport == "k3-local"
        result = adapter.execute(
            AdapterCommand(
                run_id="test",
                action_id="test",
                adapter_id=adapter_id,
                command="diagnostic",
                preset="diagnostic",
            )
        )
        assert result.status == "ownership_blocked"


def test_pendant_action_runs_without_k3_side_effects(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    plan = service.hardware_output.create_plan(
        PlanCreateRequest(journal=_journal())
    )
    service.hardware_output.queue_plan(
        plan["plan_id"],
        ExecutePlanRequest(idempotencyKey="safe-actions-only"),
    )

    worker = HardwareOutputWorker(service.hardware_output)
    result = worker.process_once()

    assert result is not None
    assert result["status"] == "completed"
    assert result["result"]["failure_count"] == 0
    assert worker.status()["state"] == "watching"
    assert worker.status()["processed_runs"] == 1
    assert worker.status()["failed_runs"] == 0


def test_model_hardware_planning_is_disabled_when_k3_owns_devices() -> None:
    result = HardwareActionPlanner().plan(_journal(), "model")
    assert result.effective_mode == "deterministic"
    assert result.warnings


def test_generated_journal_automatically_creates_plan_without_execution(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    _ingest_journal_event(service)

    response = service.journal_coordinator.sync(
        GenerateRequest(date="2026-07-30"),
    )

    assert response.status == "fallback"
    assert response.payload is not None
    plans = service.hardware_output.repository.list_plans()
    assert len(plans) == 1
    assert plans[0]["journal_id"] == "elfred-daily-2026-07-30"
    assert plans[0]["journal"]["metadata"]["source"] == (
        "journal_generator"
    )
    assert service.hardware_output.repository.list_runs() == []


def test_hardware_sidecar_failure_cannot_break_journal_output(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    def fail_plan(*args, **kwargs):
        raise RuntimeError("simulated optional sidecar failure")

    service.hardware_output.create_plan_from_generated = fail_plan
    _ingest_journal_event(service)
    response = service.journal_coordinator.sync(
        GenerateRequest(date="2026-07-30"),
    )

    assert response.status == "fallback"
    assert response.payload is not None
    assert response.used_fallback is True
    assert service.hardware_output.repository.list_plans() == []
    state = service.store.journal_sync_state("2026-07-30")
    assert state["status"] == "succeeded"
    assert state["hardware_status"] == "retry_pending"


def test_dry_run_and_disabled_hardware_preserve_software_only_journal(
    tmp_path: Path,
) -> None:
    enabled = _service(tmp_path / "enabled")
    dry_run = enabled.journal.generate(
        GenerateRequest(date="2026-07-30", dry_run=True),
        events=[_journal_event()],
    )
    assert dry_run.status == "dry_run"
    assert dry_run.payload is not None
    assert enabled.hardware_output.repository.list_plans() == []

    settings = Settings(
        tmp_path / "disabled" / "elfred_adapter.db",
        "http://fake",
        "http://observer",
        hardware_output_enabled=False,
        hardware_output_auto_plan_on_journal=True,
        hardware_output_config_path=tmp_path / "disabled" / "hardware.local.json",
    )
    disabled = AdapterService(settings, InMemoryFreeTodoClient())
    _ingest_journal_event(disabled)
    response = TestClient(create_app(service=disabled)).post(
        "/v1/elfred/journal/generate",
        json={"date": "2026-07-30"},
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "status",
        "journal_id",
        "payload",
        "warnings",
        "used_fallback",
    }
    assert response.json()["status"] == "fallback"
    assert response.json()["payload"] is not None
    assert disabled.hardware_output.repository.list_plans() == []


def test_http_flow_supports_push_pull_diagnostics_and_cors(tmp_path: Path) -> None:
    service = _service(tmp_path)
    client = TestClient(create_app(service=service))
    payload = _journal().model_dump(mode="json", by_alias=True)

    response = client.post(
        "/v1/elfred/hardware-output/journals/ready",
        json={"journal": payload, "executeSafeActions": False},
    )
    assert response.status_code == 200
    plan = response.json()["plan"]

    execute = client.post(
        f"/v1/elfred/hardware-output/plans/{plan['plan_id']}/execute",
        json={"idempotencyKey": "api-safe"},
    )
    assert execute.status_code == 202
    assert execute.json()["status"] == "queued"

    assert client.post(
        "/v1/elfred/hardware-output/adapters/arm/test",
        json={"confirm": False},
    ).status_code == 409
    assert client.post(
        "/v1/elfred/hardware-output/adapters/arm/test",
        json={"confirm": True},
    ).status_code == 200
    assert client.get("/v1/elfred/hardware-output/doctor").status_code == 200

    bundle = client.get(
        "/v1/elfred/hardware-output/support-bundle"
    ).json()
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert _journal().content not in serialized
    assert bundle["redaction"]["journal_text_included"] is False

    preflight = client.options(
        "/v1/elfred/hardware-output/plans",
        headers={
            "Origin": "http://127.0.0.1:8002",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:8002"
    )


def test_existing_database_gains_hardware_output_schema(tmp_path: Path) -> None:
    database = tmp_path / "elfred_adapter.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE ingested_events(
            event_id TEXT PRIMARY KEY,payload_json TEXT,status TEXT,created_at TEXT
            )"""
        )

    _service(tmp_path)
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "hardware_output_plans",
        "hardware_output_actions",
        "hardware_output_runs",
        "hardware_output_attempts",
        "hardware_device_events",
    }.issubset(tables)
