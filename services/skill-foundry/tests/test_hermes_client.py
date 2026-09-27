from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from adapter.hermes_client import HermesClient, HermesError, HermesRuntime


class Response(io.BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_client_authenticates_and_uses_hermes_session_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[urllib.request.Request] = []
    responses = [
        {"object": "hermes.session", "session": {"id": "session-1"}},
        {
            "object": "hermes.session.chat.completion",
            "message": {"role": "assistant", "content": "done"},
        },
        {"object": "hermes.session.deleted", "deleted": True},
    ]

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        assert timeout == 42
        calls.append(request)
        return Response(json.dumps(responses.pop(0)).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HermesClient(
        "http://127.0.0.1:8642/",
        "local-gateway-key-value",
        runtime=HermesRuntime(
            model="model-alias",
            provider="custom-provider",
            reasoning_effort="low",
        ),
        timeout_seconds=42,
    )

    assert client.complete("hello", instructions="Return plain text") == "done"
    assert [request.method for request in calls] == ["POST", "POST", "DELETE"]
    assert all(
        request.headers["Authorization"] == "Bearer local-gateway-key-value"
        for request in calls
    )

    create_body = json.loads(calls[0].data or b"{}")
    assert create_body == {
        "source": "api_server",
        "model": "model-alias",
        "provider": "custom-provider",
        "require_model_lock": True,
        "model_options": {"reasoning_effort": "low"},
    }
    chat_body = json.loads(calls[1].data or b"{}")
    assert chat_body["message"] == "hello"
    assert chat_body["instructions"] == "Return plain text"
    assert chat_body["require_model_lock"] is True
    assert calls[1].full_url.endswith("/api/sessions/session-1/chat")


def test_cleanup_failure_does_not_hide_a_successful_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = 0

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        nonlocal count
        count += 1
        if count == 1:
            payload: dict[str, Any] = {"session": {"id": "session-1"}}
            return Response(json.dumps(payload).encode())
        if count == 2:
            return Response(
                json.dumps({"message": {"content": "success"}}).encode()
            )
        raise urllib.error.URLError("cleanup unavailable")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HermesClient("http://127.0.0.1:8642", "x" * 16)

    assert client.complete("hello") == "success"


def test_session_model_lock_and_inherited_chat_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[urllib.request.Request] = []
    responses = [
        {"object": "hermes.session.model.updated", "model": "deepseek-v4-flash"},
        {
            "object": "hermes.session.chat.completion",
            "message": {"role": "assistant", "content": "ok"},
        },
    ]

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        calls.append(request)
        return Response(json.dumps(responses.pop(0)).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HermesClient(
        "http://127.0.0.1:8642",
        "gateway-key",
        runtime=HermesRuntime(model="gpt-5.6-luna", provider="custom"),
    )

    client.set_session_model(
        "session-1", HermesRuntime(model="deepseek-v4-flash", provider="deepseek")
    )
    assert client.chat("session-1", "hello", inherit_session_runtime=True)

    assert calls[0].full_url.endswith("/api/sessions/session-1/model")
    assert json.loads(calls[0].data or b"{}") == {
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
        "require_model_lock": True,
    }
    assert calls[1].full_url.endswith("/api/sessions/session-1/chat")
    assert json.loads(calls[1].data or b"{}") == {"message": "hello"}


def test_errors_do_not_include_gateway_response_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sensitive-local-key"

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            f"invalid key {secret}",
            hdrs=None,
            fp=io.BytesIO(f"upstream leaked {secret}".encode()),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HermesClient("http://127.0.0.1:8642", secret)

    with pytest.raises(HermesError) as caught:
        client.list_sessions()
    assert str(caught.value) == "Hermes request failed with HTTP 401"
    assert secret not in str(caught.value)


def test_public_health_does_not_require_or_send_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> Response:
        captured.append(request)
        return Response(b'{"status":"ok"}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = HermesClient("http://127.0.0.1:8642", "")

    assert client.health() == {"status": "ok"}
    assert "Authorization" not in captured[0].headers
    with pytest.raises(HermesError, match="API key is not configured"):
        client.health(detailed=True)


def test_sse_parser_preserves_named_events_and_multiline_data() -> None:
    stream = io.BytesIO(
        b": keepalive\n\n"
        b"event: assistant.delta\n"
        b"data: {\"delta\":\"hello\"}\n\n"
        b"event: done\n"
        b"data: {\"ok\":\n"
        b"data: true}\n\n"
    )

    assert list(HermesClient.iter_sse(stream)) == [
        ("assistant.delta", '{"delta":"hello"}'),
        ("done", '{"ok":\ntrue}'),
    ]


def test_runtime_rejects_unsupported_reasoning_effort() -> None:
    with pytest.raises(ValueError, match="REASONING_EFFORT"):
        HermesRuntime(model="configured-model", reasoning_effort="light")


def test_runtime_only_locks_an_explicit_model_and_provider() -> None:
    assert HermesRuntime(model="model", provider="custom").request_fields()[
        "require_model_lock"
    ] is True
    assert "require_model_lock" not in HermesRuntime(model="model").request_fields()
    assert "require_model_lock" not in HermesRuntime(provider="custom").request_fields()
