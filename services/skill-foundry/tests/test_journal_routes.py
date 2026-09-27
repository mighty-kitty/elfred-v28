from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter.journal.models import GenerateRequest, GenerateResponse
from adapter.journal.routes import register_journal_routes


class StubCoordinator:
    def __init__(self) -> None:
        self.requests: list[tuple[GenerateRequest, str]] = []

    def sync(self, request: GenerateRequest, *, trigger: str) -> GenerateResponse:
        self.requests.append((request, trigger))
        return GenerateResponse(
            status="dry_run" if request.dry_run else "fallback",
            payload={
                "uid": f"elfred-daily-{request.date}",
                "name": f"test-{request.date}",
            },
        )

    def status(self) -> dict:
        return {"enabled": False, "states": {}, "latest": None}


def _make_app() -> tuple[FastAPI, StubCoordinator]:
    """创建带 journal 路由的测试 FastAPI 应用"""
    app = FastAPI()
    coordinator = StubCoordinator()
    register_journal_routes(app, coordinator)
    return app, coordinator


def test_status_returns_enabled():
    app, _ = _make_app()
    client = TestClient(app)
    resp = client.get("/v1/elfred/journal/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "states": {}, "latest": None}


def test_generate_dry_run():
    app, coordinator = _make_app()
    client = TestClient(app)
    resp = client.post("/v1/elfred/journal/generate", json={"date": "2026-07-30", "dry_run": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dry_run"
    assert data["payload"] is not None
    assert coordinator.requests[0][1] == "manual"
    assert coordinator.requests[0][0].dry_run is True


def test_generate_non_dry_run():
    app, coordinator = _make_app()
    client = TestClient(app)
    resp = client.post("/v1/elfred/journal/generate", json={"date": "2026-07-30", "dry_run": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "fallback"
    assert data["payload"]["uid"].startswith("elfred-daily")
    assert coordinator.requests[0][1] == "manual"


def test_generate_validates_date_and_prompt_limit():
    app, _ = _make_app()
    client = TestClient(app)

    assert client.post(
        "/v1/elfred/journal/generate",
        json={"date": "not-a-date"},
    ).status_code == 422
    assert client.post(
        "/v1/elfred/journal/generate",
        json={"date": "2026-07-30", "max_events": 0},
    ).status_code == 422
    assert client.post(
        "/v1/elfred/journal/generate",
        json={"date": "2026-07-30", "max_events": 501},
    ).status_code == 422


def test_app_startup_queues_the_correct_timezone_day(tmp_path):
    from datetime import datetime, timedelta, timezone

    from adapter.api import create_app
    from adapter.config import Settings
    from adapter.freetodo_client import InMemoryFreeTodoClient
    from adapter.service import AdapterService

    settings = Settings(
        tmp_path / "adapter.db",
        "http://fake",
        "http://observer",
        llm_provider="deterministic",
        journal_enabled=True,
        journal_timezone="+08:00",
        journal_worker_interval_seconds=0,
        hardware_output_enabled=False,
    )
    service = AdapterService(settings, InMemoryFreeTodoClient())
    app = create_app(settings=settings, service=service)
    china = timezone(timedelta(hours=8))
    expected_day = (
        datetime.now(china).date() - timedelta(days=1)
    ).isoformat()

    assert app.router.on_startup == []

    with TestClient(app) as client:
        journal_task = app.state.journal_task
        assert journal_task is not None and not journal_task.done()
        state = service.store.journal_sync_state(expected_day)
        assert state is not None
        assert state["trigger_name"] in {"startup", "startup_reconcile"}
        resp = client.get("/v1/elfred/journal/status")
        assert resp.status_code == 200
        assert isinstance(resp.json()["enabled"], bool)
    assert journal_task.done()


def test_app_startup_runs_retry_worker_when_llm_journal_is_disabled(tmp_path):
    from adapter.api import create_app
    from adapter.config import Settings
    from adapter.freetodo_client import InMemoryFreeTodoClient
    from adapter.service import AdapterService

    settings = Settings(
        tmp_path / "adapter.db",
        "http://fake",
        "http://observer",
        journal_enabled=False,
        journal_worker_interval_seconds=0.1,
    )
    service = AdapterService(settings, InMemoryFreeTodoClient())
    app = create_app(settings=settings, service=service)

    with TestClient(app):
        assert app.state.journal_worker is not None
        assert app.state.journal_task is None
        worker_thread = app.state.journal_worker._thread
        assert worker_thread is not None and worker_thread.is_alive()

    assert app.state.journal_worker.status()["state"] == "stopped"


def test_generate_route_never_calls_legacy_direct_publish_path():
    app, coordinator = _make_app()
    client = TestClient(app)

    response = client.post(
        "/v1/elfred/journal/generate",
        json={"date": "2026-07-31"},
    )

    assert response.status_code == 200
    assert len(coordinator.requests) == 1
    assert coordinator.requests[0][0].date == "2026-07-31"
