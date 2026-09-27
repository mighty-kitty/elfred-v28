# -*- coding: utf-8 -*-
"""Bug 6: outbound calls really carry the request's trace id."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.tracing import current_trace_id, set_trace_id, trace_headers
from connectors.base import EmosClient


class _Recorder(BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):  # noqa: N802
        type(self).seen.append(dict(self.headers))
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D102
        return


@pytest.fixture()
def upstream():
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Recorder.seen = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_no_trace_id_means_no_header(upstream, monkeypatch):
    monkeypatch.setattr(EmosClient, "__init__", lambda self: setattr(
        self, "base_url", upstream))
    set_trace_id("")
    EmosClient().health()
    assert "X-Trace-Id" not in _Recorder.seen[0]


def test_the_active_trace_id_is_sent_downstream(upstream, monkeypatch):
    monkeypatch.setattr(EmosClient, "__init__", lambda self: setattr(
        self, "base_url", upstream))
    set_trace_id("trace-abc-123")
    EmosClient().health()
    assert _Recorder.seen[0].get("X-Trace-Id") == "trace-abc-123"
    set_trace_id("")


def test_each_request_can_carry_its_own_id(upstream, monkeypatch):
    monkeypatch.setattr(EmosClient, "__init__", lambda self: setattr(
        self, "base_url", upstream))
    for trace_id in ("one", "two"):
        set_trace_id(trace_id)
        EmosClient().health()
    assert [row.get("X-Trace-Id") for row in _Recorder.seen] == ["one", "two"]
    set_trace_id("")


def test_headers_helper_is_empty_without_a_trace():
    set_trace_id("")
    assert trace_headers() == {} and current_trace_id() == ""
    set_trace_id("x")
    assert trace_headers() == {"X-Trace-Id": "x"}
    set_trace_id("")
