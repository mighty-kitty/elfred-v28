from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.config import Settings
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.service import AdapterService


class MustNotRunAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(
        self,
        event: dict[str, Any],
        existing_tasks: list[dict[str, Any]] | None = None,
    ) -> Any:
        self.calls += 1
        raise AssertionError("reading a stored analysis must not call the model")


def make_client(tmp_path: Path) -> tuple[TestClient, AdapterService, MustNotRunAnalyzer]:
    settings = Settings(
        db_path=tmp_path / "adapter.db",
        freetodo_base_url="http://unused",
        observer_base_url="http://unused",
        analysis_worker_interval_seconds=0,
        observer_auto_sync_interval_seconds=0,
    )
    analyzer = MustNotRunAnalyzer()
    service = AdapterService(settings, InMemoryFreeTodoClient(), analyzer)
    return TestClient(create_app(service=service)), service, analyzer


def test_existing_event_analysis_endpoint_reads_stored_summary_without_model_call(
    tmp_path: Path,
) -> None:
    client, service, analyzer = make_client(tmp_path)
    service.store.upsert_task_analysis(
        "capture-1",
        "succeeded",
        "hermes",
        "hermes-chat",
        "synthetic-source",
        True,
        {
            "summary": "Synthetic semantic summary",
            "context_kind": "reference",
            "tasks": [],
        },
    )

    response = client.get("/v1/elfred/events/capture-1/task-analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == "capture-1"
    assert body["status"] == "succeeded"
    assert body["provider"] == "hermes"
    assert body["model"] == "hermes-chat"
    assert body["analysis"]["summary"] == "Synthetic semantic summary"
    assert analyzer.calls == 0


def test_existing_event_analysis_endpoint_returns_not_found_without_model_call(
    tmp_path: Path,
) -> None:
    client, _, analyzer = make_client(tmp_path)

    response = client.get("/v1/elfred/events/unknown/task-analysis")

    assert response.status_code == 404
    assert response.json() == {"detail": "task analysis not found"}
    assert analyzer.calls == 0


def test_task_analysis_cors_allows_only_elfred_web_get(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path)
    endpoint = "/v1/elfred/events/capture-1/task-analysis"

    preflight = client.options(
        endpoint,
        headers={
            "Origin": "http://127.0.0.1:8002",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:8002"
    assert "GET" in preflight.headers["access-control-allow-methods"]
    assert "content-type" in preflight.headers["access-control-allow-headers"].casefold()

    localhost = client.get(
        endpoint,
        headers={"Origin": "http://localhost:8002"},
    )
    assert localhost.status_code == 404
    assert localhost.headers["access-control-allow-origin"] == "http://localhost:8002"

    disallowed = client.get(
        endpoint,
        headers={"Origin": "http://example.invalid"},
    )
    assert disallowed.status_code == 404
    assert "access-control-allow-origin" not in disallowed.headers

    write_preflight = client.options(
        "/v1/elfred/events",
        headers={
            "Origin": "http://127.0.0.1:8002",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert write_preflight.status_code == 400
