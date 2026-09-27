# -*- coding: utf-8 -*-
"""WP-08 tool tests: tasks, skills, local file access and delegation.

Every tool runs against injected fakes, so the suite stays hermetic: what is under
test is the gateway's tool semantics (idempotency, honest failure, audit refs).
"""
import os
import sys
import time

import app.main as main_mod
from app.main import app
from fastapi.testclient import TestClient

c = TestClient(app)


class FakeTaskHost:
    def __init__(self):
        self.todos = {}
        self.calls = []
        self._next = 1
        self.available = True

    def health(self):
        return {"status": "healthy"}

    def list_todos(self, status=None):
        if not self.available:
            raise RuntimeError("task host down")
        return {"todos": list(self.todos.values()), "total": len(self.todos)}

    def get_todo(self, todo_id):
        return self.todos.get(int(todo_id))

    def create_todo(self, payload, idempotency_key=None):
        if not self.available:
            raise RuntimeError("task host down")
        uid = payload.get("uid")
        for todo in self.todos.values():
            if todo.get("uid") == uid:  # uid is the business key
                return todo
        item = {"id": self._next, "status": "active", "percent_complete": 0, **payload}
        self.todos[self._next] = item
        self._next += 1
        self.calls.append(("create", uid))
        return item

    def update_todo(self, todo_id, payload):
        if not self.available:
            raise RuntimeError("task host down")
        todo = self.todos[int(todo_id)]
        todo.update(payload)
        self.calls.append(("update", todo.get("uid")))
        return todo


class FakeSkills:
    def __init__(self, status="succeeded"):
        self.status = status
        self.runs = []

    def match(self, context):
        return {"total": 1, "matches": [{"skillId": "skill_test_1", "name": "doc summary"}]}

    def list_skills(self):
        return {"total": 1, "skills": [{"id": "skill_test_1", "status": "approved"}]}

    def approve(self, skill_id, allow_heuristic=True):
        return {"skill_id": skill_id, "status": "approved"}

    def run(self, skill_id, inputs=None, task_context=None):
        run_id = f"skillrun_test_{len(self.runs) + 1}"
        self.runs.append({"run_id": run_id, "skill_id": skill_id, "status": self.status,
                          "taskContext": task_context, "inputs": inputs})
        return {"run": {"run_id": run_id, "skill_id": skill_id, "status": self.status,
                        "error": None if self.status == "succeeded" else "verification failed"}}


class StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _mk_pa(boundaries=None, scopes=None):
    payload = {"user_id": "u_wp08", "consent_version": 1}
    if boundaries:
        payload["boundaries"] = boundaries
    if scopes:
        payload["tool_scopes"] = scopes
    return c.post("/v1/pa/profiles", json=payload).json()["pa_id"]


def _run_with_plan(plan, message="wp08", boundaries=None, scopes=None):
    original = main_mod.engine.planner
    main_mod.engine.planner = StubPlanner(plan)
    try:
        pa = _mk_pa(boundaries, scopes)
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": message}).json()["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline:
            run = c.get(f"/v1/runs/{rid}").json()
            if run["state"] == "waiting_approval":
                break
            time.sleep(0.1)
        body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
        return run, body
    finally:
        main_mod.engine.planner = original


def _events(body, type_):
    return [e["payload"] for e in body["events"] if e["type"] == type_]


def test_task_create_is_keyed_by_run_and_step(monkeypatch):
    host = FakeTaskHost()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    plan = [{"step": 1, "goal": "create the Monday task", "tool": "task_create", "risk": "low"}]
    run, body = _run_with_plan(plan)
    assert body["state"] == "completed", _events(body, "tool.failed")
    tasks = [a for a in body["artifacts"] if a.get("type") == "task"]
    assert len(tasks) == 1
    uid = tasks[0]["uid"]
    assert uid == f"elfred-{run['run_id']}-s1"
    assert tasks[0]["run_id"] == run["run_id"], "artifacts must be traceable to the run"
    completed = _events(body, "tool.completed")
    assert completed and completed[0]["tool"] == "task_create"


def test_repeating_a_step_does_not_create_a_second_task(monkeypatch):
    host = FakeTaskHost()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    plan = [{"step": 1, "goal": "create once", "tool": "task_create", "risk": "low"}]
    _run_with_plan(plan)
    _run_with_plan(plan)
    uids = [todo["uid"] for todo in host.todos.values()]
    assert len(uids) == len(set(uids)) == 2, uids  # one per run, never duplicated


def test_task_complete_sets_percent_complete(monkeypatch):
    host = FakeTaskHost()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    plan = [{"step": 1, "goal": "create", "tool": "task_create", "risk": "low"},
            {"step": 2, "goal": "finish it", "tool": "task_complete", "risk": "low"}]
    _, body = _run_with_plan(plan)
    todo = list(host.todos.values())[0]
    assert todo["status"] == "completed"
    assert todo["percent_complete"] == 100
    assert body["state"] == "completed"


def test_task_tools_fail_honestly_when_the_host_is_down(monkeypatch):
    host = FakeTaskHost()
    host.available = False
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    plan = [{"step": 1, "goal": "create", "tool": "task_create", "risk": "low"}]
    _, body = _run_with_plan(plan)
    errors = [e.get("error") for e in _events(body, "tool.failed")]
    assert "SERVICE_UNAVAILABLE" in errors, errors
    assert not _events(body, "tool.completed")


def test_skill_run_attaches_a_task_and_records_evidence(monkeypatch):
    host = FakeTaskHost()
    skills = FakeSkills()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    monkeypatch.setattr(main_mod.engine, "skill", skills)
    plan = [{"step": 1, "goal": "summarize the document", "tool": "skill_run", "risk": "medium"}]
    run, body = _run_with_plan(plan)
    assert body["state"] == "completed", _events(body, "tool.failed")
    assert skills.runs[0]["taskContext"]["freetodoTodoId"] == 1
    artifacts = [a for a in body["artifacts"] if a.get("type") == "skill_run"]
    assert artifacts and artifacts[0]["run_id"] == run["run_id"]
    envelope = [t for t in body["tool_calls"] if t["status"] == "completed"][0]
    assert any(ref.startswith("skillrun:") for ref in envelope["evidence_refs"])


def test_failed_skill_run_is_reported_not_hidden(monkeypatch):
    host = FakeTaskHost()
    monkeypatch.setattr(main_mod.engine, "freetodo", host)
    monkeypatch.setattr(main_mod.engine, "skill", FakeSkills(status="failed"))
    plan = [{"step": 1, "goal": "summarize", "tool": "skill_run", "risk": "medium"}]
    _, body = _run_with_plan(plan)
    # The only step failed, so the run must fail as well rather than look done.
    assert body["state"] == "failed"
    assert "INVALID_OUTPUT" in [e.get("error") for e in _events(body, "tool.failed")]


def test_local_file_read_is_limited_to_allowed_roots(monkeypatch, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "note.txt"
    inside.write_text("hello from the workspace", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("should never be read", encoding="utf-8")

    plan = [{"step": 1, "goal": f"read {inside}", "tool": "local_file_read", "risk": "low"}]
    _, ok = _run_with_plan(plan, boundaries={"allowed_roots": [str(allowed)]})
    assert "file" in [a.get("type") for a in ok["artifacts"]], _events(ok, "tool.failed")

    plan_out = [{"step": 1, "goal": f"read {outside}", "tool": "local_file_read", "risk": "low"}]
    _, denied = _run_with_plan(plan_out, boundaries={"allowed_roots": [str(allowed)]})
    assert "POLICY_DENIED" in [e.get("error") for e in _events(denied, "tool.failed")]

    _, unset = _run_with_plan(plan)
    assert "POLICY_DENIED" in [e.get("error") for e in _events(unset, "tool.failed")]


def test_delegation_requires_configuration(monkeypatch):
    monkeypatch.delenv("PA_DELEGATE_CMD", raising=False)
    monkeypatch.delenv("PA_DELEGATE_WORKSPACE", raising=False)
    plan = [{"step": 1, "goal": "review the repo", "tool": "opencode_delegate", "risk": "high"}]
    _, body = _run_with_plan(plan)
    assert "TOOL_UNAVAILABLE" in [e.get("error") for e in _events(body, "tool.failed")]


def test_configured_delegation_runs_and_records_the_artifact(monkeypatch, tmp_path):
    monkeypatch.setenv("PA_DELEGATE_CMD", f'"{sys.executable}" -c "print(\'delegated-ok\')"')
    monkeypatch.setenv("PA_DELEGATE_WORKSPACE", str(tmp_path))
    plan = [{"step": 1, "goal": "say ok", "tool": "opencode_delegate", "risk": "high"}]
    _, body = _run_with_plan(plan, boundaries={"allowed_roots": [str(tmp_path)]})
    artifacts = [a for a in body["artifacts"] if a.get("type") == "delegation"]
    assert artifacts, _events(body, "tool.failed")
    assert artifacts[0]["exit_code"] == 0
    assert "delegated-ok" in artifacts[0]["output"]
