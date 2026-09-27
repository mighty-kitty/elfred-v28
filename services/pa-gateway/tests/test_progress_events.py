# -*- coding: utf-8 -*-
"""plan.updated / tool.progress must carry real information (book section 11.1)."""
import sys
import time

import app.main as main_mod
import app.policy as policy_mod
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


class _FakeTaskHost:
    def __init__(self):
        self.todos = {}
        self._next = 1

    def list_todos(self, status=None):
        return {"todos": list(self.todos.values()), "total": len(self.todos)}

    def get_todo(self, todo_id):
        return self.todos.get(int(todo_id))

    def create_todo(self, payload, idempotency_key=None):
        uid = payload.get("uid")
        for todo in self.todos.values():
            if todo.get("uid") == uid:
                return todo
        item = {"id": self._next, "status": "active", "percent_complete": 0, **payload}
        self.todos[self._next] = item
        self._next += 1
        return item

    def update_todo(self, todo_id, payload):
        todo = self.todos[int(todo_id)]
        todo.update(payload)
        return todo


class _FakeSkills:
    def __init__(self):
        self.runs = []

    def match(self, context):
        return {"total": 1, "matches": [{"skillId": "skill_progress_1"}]}

    def list_skills(self):
        return {"total": 1, "skills": [{"skill_id": "skill_progress_1", "status": "approved"}]}

    def run(self, skill_id, inputs=None, task_context=None):
        time.sleep(0.2)  # a real tool takes time; progress must reflect that
        run_id = f"skillrun_progress_{len(self.runs) + 1}"
        self.runs.append({"run_id": run_id, "status": "succeeded"})
        return {"run": {"run_id": run_id, "skill_id": skill_id, "status": "succeeded"}}


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _run(plan, message="progress", scopes=None, boundaries=None):
    original = main_mod.engine.planner
    main_mod.engine.planner = _StubPlanner(plan)
    try:
        payload = {"user_id": "u_progress", "consent_version": 1}
        if scopes:
            payload["tool_scopes"] = scopes
        if boundaries:
            payload["boundaries"] = boundaries
        pa = c.post("/v1/pa/profiles", json=payload).json()["pa_id"]
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": message}).json()["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            run = c.get(f"/v1/runs/{rid}").json()
            if run["state"] == "waiting_approval":
                break
            time.sleep(0.2)
        body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
        return run, body
    finally:
        main_mod.engine.planner = original


def _payloads(run, type_):
    return [e["payload"] for e in run["events"] if e["type"] == type_]


def test_plan_updated_is_emitted_only_when_steps_are_dropped(monkeypatch):
    monkeypatch.setattr(policy_mod, "TOOL_REGISTRY",
                        policy_mod.TOOL_REGISTRY + ["not_a_real_tool"])
    plan = [{"step": 1, "goal": "recall", "tool": "emos_recall", "risk": "low"},
            {"step": 2, "goal": "phantom", "tool": "not_a_real_tool", "risk": "low"}]
    kept, _ = _run(plan, scopes=["emos_recall"])
    updates = _payloads(kept, "plan.updated")
    assert updates, "a trimmed plan must be announced"
    assert updates[-1]["dropped_tools"] == ["not_a_real_tool"]
    assert updates[-1]["steps"] == 1
    assert updates[-1]["reason"] == "unavailable tools removed"

    # nothing dropped -> no noise
    clean, _ = _run([{"step": 1, "goal": "recall", "tool": "emos_recall", "risk": "low"}])
    assert _payloads(clean, "plan.updated") == []


def test_skill_run_reports_real_progress_stages(monkeypatch):
    host = _FakeTaskHost()
    skills = _FakeSkills()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    monkeypatch.setattr(main_mod.engine, "skill", skills)
    plan = [{"step": 1, "goal": "summarize", "tool": "skill_run", "risk": "medium"}]
    _, body = _run(plan)
    stages = [p["stage"] for p in _payloads(body, "tool.progress") if p.get("tool") == "skill_run"]
    assert stages == ["skill_selected", "running", "finished"], stages
    finished = [p for p in _payloads(body, "tool.progress") if p.get("stage") == "finished"][0]
    assert finished["skill"] == "skill_progress_1"
    assert finished["skill_run"].startswith("skillrun_progress_")
    assert finished["duration_ms"] >= 150, finished  # real elapsed time, not a constant


def test_delegation_reports_spawned_and_finished(monkeypatch, tmp_path):
    monkeypatch.setenv("PA_DELEGATE_CMD", f'"{sys.executable}" -c "print(\'ok\')"')
    monkeypatch.setenv("PA_DELEGATE_WORKSPACE", str(tmp_path))
    plan = [{"step": 1, "goal": "say ok", "tool": "opencode_delegate", "risk": "high"}]
    _, body = _run(plan, boundaries={"allowed_roots": [str(tmp_path)]})
    progress = _payloads(body, "tool.progress")
    stages = [p["stage"] for p in progress]
    assert "spawned" in stages and "finished" in stages, stages
    spawned = [p for p in progress if p["stage"] == "spawned"][0]
    assert spawned["workspace"] == str(tmp_path)
    assert spawned["timeout_s"] > 0
    finished = [p for p in progress if p["stage"] == "finished"][0]
    assert finished["exit_code"] == 0
