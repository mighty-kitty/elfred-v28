from __future__ import annotations

from queue import Queue
from typing import Any

from adapter.codex_client import CodexClient, CodexRuntime
from adapter.codex_transport import CodexAppServerTransport, CodexProcessStatus


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.status_value = CodexProcessStatus(True, 42, "codex-cli 0.146.0")

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None

    def status(self) -> CodexProcessStatus:
        return self.status_value

    def request(self, method: str, params: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.requests.append((method, params))
        if method == "thread/start":
            return {"result": {"thread": {"id": "thread-1", "createdAt": 1}}}
        if method == "thread/read":
            return {
                "result": {
                    "thread": {
                        "id": "thread-1",
                        "createdAt": 1,
                        "turns": [
                            {
                                "items": [
                                    {"type": "userMessage", "content": [{"type": "text", "text": "hi"}]},
                                    {"type": "agentMessage", "text": "hello"},
                                ]
                            }
                        ]
                    }
                }
            }
        if method == "thread/name/set":
            return {"result": {"thread": {"id": "thread-1", "name": params["name"]}}}
        if method == "thread/resume":
            return {"result": {"thread": {"id": "thread-1"}}}
        if method == "thread/delete":
            return {"result": {}}
        if method == "thread/list":
            return {"result": {"data": [], "nextCursor": None}}
        if method == "turn/start":
            return {"result": {"turn": {"id": "turn-1"}}}
        if method == "turn/interrupt":
            return {"result": {}}
        raise AssertionError(method)

    def subscribe(self, _: str):
        channel: Queue[dict[str, Any]] = Queue()
        channel.put({"method": "item/agentMessage/delta", "params": {"delta": "ok"}})
        channel.put({"method": "turn/completed", "params": {}})
        return channel, lambda: None


def make_client(fake: FakeTransport) -> CodexClient:
    return CodexClient(
        fake,  # type: ignore[arg-type]
        runtime=CodexRuntime("gpt-5.6-luna", "elfred-sub2api", "low"),
        working_directory="C:/workspace",
    )


def test_codex_thread_params_are_read_only_and_non_interactive() -> None:
    fake = FakeTransport()
    session = make_client(fake).create_session(source="test")
    assert session["id"] == "thread-1"
    method, params = fake.requests[0]
    assert method == "thread/start"
    assert params["approvalPolicy"] == "never"
    assert params["sandbox"] == "read-only"
    assert params["modelProvider"] == "elfred-sub2api"


def test_codex_messages_and_stream_are_projected_to_adapter_contract() -> None:
    fake = FakeTransport()
    client = make_client(fake)
    client.create_session(source="test")
    assert client.get_messages("thread-1") == [
        {"id": "", "role": "user", "content": "hi"},
        {"id": "", "role": "assistant", "content": "hello"},
    ]
    assert list(client.iter_chat_events("thread-1", "next")) == [
        ("message.started", {"session_id": "thread-1"}),
        ("assistant.delta", {"delta": "ok"}),
        ("assistant.completed", {}),
        ("done", {}),
    ]


def test_codex_interrupt_targets_only_the_active_turn() -> None:
    fake = FakeTransport()
    client = make_client(fake)
    events = client.iter_chat_events("thread-1", "next")

    assert next(events) == ("message.started", {"session_id": "thread-1"})
    assert client.interrupt_chat("thread-1") is True
    assert fake.requests[-1] == (
        "turn/interrupt",
        {"threadId": "thread-1", "turnId": "turn-1"},
    )

    assert list(events) == [
        ("assistant.delta", {"delta": "ok"}),
        ("assistant.completed", {}),
        ("done", {}),
    ]
    assert client.interrupt_chat("thread-1") is False


class FailingTurnTransport(FakeTransport):
    def subscribe(self, _: str):
        channel: Queue[dict[str, Any]] = Queue()
        channel.put({"method": "turn/failed", "params": {}})
        return channel, lambda: None


def test_codex_failed_turn_emits_error_without_done() -> None:
    fake = FailingTurnTransport()
    client = make_client(fake)
    assert list(client.iter_chat_events("thread-1", "next")) == [
        ("message.started", {"session_id": "thread-1"}),
        ("error", {"message": "Codex turn failed"}),
    ]


def test_codex_input_projection_keeps_image_evidence_as_data() -> None:
    value = CodexClient._input_items(
        [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}},
        ]
    )
    assert value == [
        {"type": "text", "text": "describe"},
        {"type": "image", "url": "data:image/jpeg;base64,abc", "detail": "low"},
    ]


def test_codex_app_server_command_supports_native_executable() -> None:
    assert CodexAppServerTransport._app_server_command("C:/Codex/codex.exe") == [
        "C:/Codex/codex.exe",
        "app-server",
        "--stdio",
        "--strict-config",
    ]


def test_codex_app_server_command_wraps_windows_command_shim(monkeypatch) -> None:
    monkeypatch.setenv("ComSpec", "C:/Windows/System32/cmd.exe")
    command = CodexAppServerTransport._app_server_command("C:/npm/codex.cmd")
    assert command[:4] == ["C:/Windows/System32/cmd.exe", "/d", "/s", "/c"]
    assert command[4].startswith("call C:/npm/codex.cmd app-server")
    assert command[4].endswith("--stdio --strict-config")
