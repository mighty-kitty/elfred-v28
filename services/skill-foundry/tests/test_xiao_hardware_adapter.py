from __future__ import annotations

from contextlib import contextmanager
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit

from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.config import Settings
from adapter.contracts import payload_hash
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.hardware_output.adapters import (
    AdapterCommand,
    HardwareAdapterRegistry,
    XIAO_COMMAND_PROTOCOL_VERSION,
    XiaoHardwareAdapter,
)
from adapter.hardware_output.models import (
    ExecutePlanRequest,
    JournalSnapshot,
    PlanCreateRequest,
)
from adapter.service import AdapterService


TOKEN = "xiao-test-token-1234"


def _semantic_digest(payload: dict[str, Any]) -> str:
    return payload_hash(
        {
            key: payload.get(key)
            for key in (
                "protocolVersion",
                "commandId",
                "idempotencyKey",
                "actionId",
                "adapterId",
                "deviceId",
                "command",
                "preset",
                "parameters",
            )
        }
    )


@contextmanager
def _xiao_server(
    *,
    command_protocol: str | None = XIAO_COMMAND_PROTOCOL_VERSION,
    fail_posts: int = 0,
) -> Iterator[tuple[str, dict[str, Any]]]:
    state: dict[str, Any] = {
        "command_protocol": command_protocol,
        "fail_posts": fail_posts,
        "post_count": 0,
        "commands": [],
        "receipts": {},
        "tokens": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-Xiao-Token", "")
            state["tokens"].append(supplied)
            if supplied == TOKEN:
                return True
            self._send(401, {"error": "unauthorized"})
            return False

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self) -> None:
            if not self._authorized():
                return
            path = urlsplit(self.path).path
            if path == "/api/status":
                payload: dict[str, Any] = {
                    "ok": True,
                    "stream_protocol_version": 2,
                    "streaming": False,
                }
                if state["command_protocol"] is not None:
                    payload["command_protocol_version"] = state[
                        "command_protocol"
                    ]
                self._send(200, payload)
                return
            prefix = "/api/hardware/commands/"
            if path.startswith(prefix):
                command_id = unquote(path[len(prefix) :])
                receipt = state["receipts"].get(command_id)
                if receipt is None:
                    self._send(404, {"error": "command not found"})
                    return
                receipt = {**receipt, "status": "completed"}
                state["receipts"][command_id] = receipt
                self._send(200, receipt)
                return
            self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            path = urlsplit(self.path).path
            if path not in {
                "/api/hardware/command",
                "/api/hardware/stop",
            }:
                self._send(404, {"error": "not found"})
                return
            payload = self._body()
            state["post_count"] += 1
            state["commands"].append(payload)
            if state["post_count"] <= state["fail_posts"]:
                self._send(503, {"error": "temporary device failure"})
                return
            if payload.get("payloadSha256") != _semantic_digest(payload):
                self._send(422, {"error": "payload digest mismatch"})
                return
            command_id = payload["commandId"]
            existing = state["receipts"].get(command_id)
            if existing is not None:
                self._send(200, existing)
                return
            receipt = {
                "protocolVersion": XIAO_COMMAND_PROTOCOL_VERSION,
                "commandId": command_id,
                "status": (
                    "stopped"
                    if path == "/api/hardware/stop"
                    else "accepted"
                ),
            }
            state["receipts"][command_id] = receipt
            self._send(202, receipt)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _device_config(base_url: str) -> dict[str, Any]:
    return {
        "transport": "xiao",
        "baseUrl": base_url,
        "deviceId": "xiao-pendant-lab",
        "boardProfile": "xiao-esp32s3",
        "tokenEnv": "XIAO_PENDANT_TOKEN",
        "pollIntervalMs": 10,
        "completionTimeoutSeconds": 2,
        "capabilities": ["notify", "stop"],
    }


def _write_config(
    path: Path,
    base_url: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "1.0",
                "devices": {
                    "pendant": _device_config(base_url),
                    "base": {"transport": "mock"},
                    "arm": {"transport": "mock"},
                    "printer": {"transport": "mock"},
                },
            }
        ),
        encoding="utf-8",
    )


def _journal() -> JournalSnapshot:
    return JournalSnapshot(
        journalId="journal-xiao-1",
        journalVersion="v1",
        date="2026-08-01",
        title="XIAO hardware output",
        content="The journal is ready for the four hardware outputs.",
        mood="calm",
        energy=5,
    )


def test_xiao_adapter_probes_executes_polls_and_stops(
    monkeypatch,
) -> None:
    monkeypatch.setenv("XIAO_PENDANT_TOKEN", TOKEN)
    with _xiao_server() as (base_url, state):
        adapter = XiaoHardwareAdapter(
            "pendant",
            _device_config(base_url),
            timeout_seconds=2,
        )
        command = AdapterCommand(
            run_id="run-1",
            action_id="action-1",
            adapter_id="pendant",
            command="notify",
            preset="journal_ready",
            parameters={"title": "Journal ready"},
        )

        probe = adapter.probe()
        result = adapter.execute(command)
        stopped = adapter.stop()

    assert probe.ok is True
    assert probe.detail["commandReady"] is True
    assert probe.detail["boardProfile"] == "xiao-esp32s3"
    assert result.ok is True
    assert result.status == "completed"
    assert result.detail["receipt"]["commandId"] == "action-1"
    assert stopped.ok is True
    assert stopped.status == "stopped"
    assert state["commands"][0]["idempotencyKey"] == "action-1"
    assert state["commands"][0]["payloadSha256"] == _semantic_digest(
        state["commands"][0]
    )
    assert all(token == TOKEN for token in state["tokens"])
    assert TOKEN not in json.dumps(probe.model_dump(mode="json"))


def test_xiao_probe_distinguishes_stream_only_firmware(
    monkeypatch,
) -> None:
    monkeypatch.setenv("XIAO_PENDANT_TOKEN", TOKEN)
    with _xiao_server(command_protocol=None) as (base_url, _):
        adapter = XiaoHardwareAdapter(
            "pendant",
            _device_config(base_url),
            timeout_seconds=2,
        )
        result = adapter.probe()

    assert result.ok is False
    assert result.status == "firmware_incompatible"
    assert result.detail["deviceStatus"]["stream_protocol_version"] == 2
    assert result.detail["commandReady"] is False


def test_xiao_registry_rejects_missing_token_and_public_host(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("XIAO_PENDANT_TOKEN", raising=False)
    config_path = tmp_path / "missing-token.json"
    _write_config(config_path, "http://127.0.0.1:12345")
    registry = HardwareAdapterRegistry(config_path)
    missing = registry.get("pendant").probe()

    public_path = tmp_path / "public-host.json"
    _write_config(public_path, "https://example.com")
    public = HardwareAdapterRegistry(public_path).get("pendant").probe()

    assert missing.status == "misconfigured"
    assert "XIAO_PENDANT_TOKEN" in str(missing.error)
    assert public.status == "misconfigured"
    assert "private IP" in str(public.error)


def test_hardware_output_retries_same_xiao_command_without_leaking_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XIAO_PENDANT_TOKEN", TOKEN)
    with _xiao_server(fail_posts=1) as (base_url, state):
        config_path = tmp_path / "hardware.local.json"
        _write_config(config_path, base_url)
        settings = Settings(
            tmp_path / "elfred_adapter.db",
            "http://fake",
            "http://observer",
            hardware_output_config_path=config_path,
            hardware_output_http_timeout_seconds=2,
            hardware_output_max_attempts=2,
        )
        service = AdapterService(settings, InMemoryFreeTodoClient())
        plan = service.hardware_output.create_plan(
            PlanCreateRequest(journal=_journal())
        )
        queued = service.hardware_output.queue_plan(
            plan["plan_id"],
            ExecutePlanRequest(idempotencyKey="xiao-safe-actions"),
        )
        completed = service.hardware_output.execute_next()
        status = service.hardware_output.status(probe=True)
        bundle = service.hardware_output.support_bundle()

    assert queued["status"] == "queued"
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"]["failure_count"] == 0
    assert completed["result"]["success_count"] == 1
    pendant_attempts = [
        attempt
        for attempt in completed["attempts"]
        if attempt["adapter_id"] == "pendant"
    ]
    assert len(pendant_attempts) == 2
    assert len(state["commands"]) == 2
    assert state["commands"][0]["commandId"] == state["commands"][1][
        "commandId"
    ]
    assert state["commands"][0]["payloadSha256"] == state["commands"][1][
        "payloadSha256"
    ]
    serialized = json.dumps({"status": status, "bundle": bundle})
    assert TOKEN not in serialized
    pendant = next(
        item for item in status["adapters"] if item["adapter_id"] == "pendant"
    )
    assert pendant["transport"] == "xiao"
    assert pendant["health"]["ok"] is True


def test_api_lifespan_worker_delivers_journal_command_to_xiao(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XIAO_PENDANT_TOKEN", TOKEN)
    with _xiao_server() as (base_url, state):
        config_path = tmp_path / "hardware.local.json"
        _write_config(config_path, base_url)
        settings = Settings(
            tmp_path / "elfred_adapter.db",
            "http://fake",
            "http://observer",
            hardware_output_config_path=config_path,
            hardware_output_worker_interval_seconds=0.1,
            hardware_output_http_timeout_seconds=2,
        )
        service = AdapterService(settings, InMemoryFreeTodoClient())
        app = create_app(service=service)

        with TestClient(app) as client:
            ready = client.post(
                "/v1/elfred/hardware-output/journals/ready",
                json={
                    "journal": _journal().model_dump(
                        mode="json",
                        by_alias=True,
                    ),
                    "executeSafeActions": True,
                    "idempotencyKey": "xiao-worker-e2e",
                },
            )
            assert ready.status_code == 200
            run_id = ready.json()["run"]["run_id"]

            deadline = time.monotonic() + 5
            run: dict[str, Any] = {}
            while time.monotonic() < deadline:
                response = client.get(
                    f"/v1/elfred/hardware-output/runs/{run_id}"
                )
                assert response.status_code == 200
                run = response.json()
                if run["status"] in {"completed", "partial", "failed"}:
                    break
                time.sleep(0.05)

            status = client.get(
                "/v1/elfred/hardware-output/status?probe=true"
            )
            assert status.status_code == 200
            assert status.json()["worker"]["state"] == "watching"

        assert app.state.hardware_output_worker.status()["state"] == "stopped"

    assert run["status"] == "completed"
    assert run["result"]["success_count"] == 1
    assert len(state["commands"]) == 1
    assert state["commands"][0]["adapterId"] == "pendant"
    assert state["commands"][0]["command"] == "notify"
