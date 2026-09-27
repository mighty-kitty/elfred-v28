# -*- coding: utf-8 -*-
"""One trace id per request, carried into every downstream call (bug 6).

The gateway already answered with `X-Trace-Id`, but nothing propagated it, so a
run could not be followed across EMOS / Observer / FreeTodo. A ContextVar is the
right carrier here: the run worker is a plain thread and each request sets its
own value.
"""
from __future__ import annotations
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("elfred_trace_id", default="")


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id or "")


def current_trace_id() -> str:
    return _trace_id.get()


def trace_headers() -> dict:
    """Headers to add to an outbound call. Empty when nothing is in flight."""
    trace_id = current_trace_id()
    return {"X-Trace-Id": trace_id} if trace_id else {}
