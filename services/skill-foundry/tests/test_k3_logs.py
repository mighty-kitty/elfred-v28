from __future__ import annotations

from adapter.hardware_output.k3_logs import K3ExecutionLogSink


def test_k3_log_sink_accepts_only_private_local_endpoints() -> None:
    sink = K3ExecutionLogSink("http://192.168.3.6:8780", "s" * 16, 2)
    assert sink.base_url == "http://192.168.3.6:8780"


def test_k3_log_sink_rejects_public_or_credentialed_endpoints() -> None:
    for url in (
        "https://example.com",
        "http://user:pass@192.168.3.6:8780",
        "http://192.168.3.6:8780/path",
    ):
        try:
            K3ExecutionLogSink(url, "s" * 16, 2)
        except ValueError:
            continue
        raise AssertionError(f"unsafe K3 log URL was accepted: {url}")


def test_k3_log_sink_never_sends_executable_payload() -> None:
    sink = K3ExecutionLogSink("http://127.0.0.1:8780", "s" * 16, 2)
    assert sink.send({"logId": "x", "executable": True}) == (
        False,
        "K3 log payload must explicitly be non-executable",
    )
