# -*- coding: utf-8 -*-
"""Async approval: execution on a worker thread, with real mid-run pause / cancel."""
import time

import app.main as main_mod
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


class _SlowTaskHost:
    """Each create/update takes ~0.6s: long enough for pause/cancel to land."""

    def __init__(self):
        self.todos = {}
        self._next = 1

    def list_todos(self, status=None):
        return {"todos": list(self.todos.values()), "total": len(self.todos)}

    def get_todo(self, todo_id):
        return self.todos.get(int(todo_id))

    def create_todo(self, payload, idempotency_key=None):
        time.sleep(0.6)
        uid = payload.get("uid")
        for todo in self.todos.values():
            if todo.get("uid") == uid:
                return todo
        item = {"id": self._next, "status": "active", "percent_complete": 0, **payload}
        self.todos[self._next] = item
        self._next += 1
        return item

    def update_todo(self, todo_id, payload):
        time.sleep(0.6)
        todo = self.todos[int(todo_id)]
        todo.update(payload)
        return todo


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _steps(n):
    return [{"step": i + 1, "goal": f"task {i + 1}", "tool": "task_create", "risk": "low"}
            for i in range(n)]


def _start_run(monkeypatch, plan, host):
    monkeypatch.setenv("PA_APPROVAL_MODE", "async")
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    original = main_mod.engine.planner
    main_mod.engine.planner = _StubPlanner(plan)
    pa = c.post("/v1/pa/profiles",
                json={"user_id": "u_async", "consent_version": 1}).json()["pa_id"]
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "slow work"}).json()["run_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
            break
        time.sleep(0.2)
    return rid, original


def _wait_state(rid, states, timeout=30.0):
    deadline = time.time() + timeout
    run = c.get(f"/v1/runs/{rid}").json()
    while time.time() < deadline:
        run = c.get(f"/v1/runs/{rid}").json()
        if run["state"] in states:
            return run
        time.sleep(0.2)
    return run


def _completed_tools(run):
    return [e["payload"].get("tool") for e in run["events"]
            if e["type"] == "tool.completed"]


def test_async_approval_returns_immediately_and_finishes_in_background(monkeypatch):
    host = _SlowTaskHost()
    rid, original = _start_run(monkeypatch, _steps(2), host)
    try:
        accepted = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
        # the endpoint reports the accepted decision, not a finished run
        assert accepted["state"] == "executing", accepted["state"]
        assert _completed_tools(accepted) == []
        final = _wait_state(rid, ("completed", "failed"), timeout=40)
        assert final["state"] == "completed", final["state"]
        assert len(_completed_tools(final)) == 2
    finally:
        main_mod.engine.planner = original


def test_pause_mid_execution_freezes_the_worker_and_resume_finishes_it(monkeypatch):
    host = _SlowTaskHost()
    rid, original = _start_run(monkeypatch, _steps(3), host)
    try:
        c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
        # pause immediately: the worker only checks for the flag between steps, so
        # at most the step that is already in flight may finish
        paused = c.post(f"/v1/runs/{rid}/pause")
        assert paused.status_code == 200, paused.text
        assert paused.json()["paused"] is True

        time.sleep(2.0)  # three tool durations would pass here if the worker ignored pause
        during = c.get(f"/v1/runs/{rid}").json()
        assert during["state"] == "executing"
        assert len(_completed_tools(during)) <= 1, _completed_tools(during)
        assert during["paused"] is True

        c.post(f"/v1/runs/{rid}/resume")
        final = _wait_state(rid, ("completed", "failed"), timeout=40)
        assert final["state"] == "completed", final["state"]
        assert len(_completed_tools(final)) == 3
    finally:
        main_mod.engine.planner = original


def test_cancel_mid_execution_stops_the_remaining_steps(monkeypatch):
    host = _SlowTaskHost()
    rid, original = _start_run(monkeypatch, _steps(3), host)
    try:
        c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
        # cancel immediately: the worker must not walk the rest of the plan
        cancelled = c.post(f"/v1/runs/{rid}/cancel", json={"reason": "user changed mind"})
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"

        time.sleep(2.0)  # the worker must stop, not keep executing the plan
        final = c.get(f"/v1/runs/{rid}").json()
        assert final["state"] == "cancelled"
        assert len(_completed_tools(final)) <= 1, _completed_tools(final)
    finally:
        main_mod.engine.planner = original
