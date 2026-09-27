# -*- coding: utf-8 -*-
"""WP-09: acceptance feedback is written back, and a change request derives a revision."""
import time

import app.main as main_mod
import pytest
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


class _FakeEmos:
    def __init__(self, ok=True):
        self.ok = ok
        self.feedback_calls = []
        self.writes = []

    def recall(self, user_id, query_text, **kw):
        return {"payload": {"recalled_memory": {"memory_id": "mem_cited_1"},
                            "evidence": [{"memory_id": "mem_cited_1"}]}}

    def write(self, user_id, session_id, text, **kw):
        self.writes.append(text)
        return {"payload": {"memory_written": True, "memory_id": "mem_accept"}}

    def feedback(self, user_id, session_id, memory_id, feedback_type, **kw):
        if not self.ok:
            raise RuntimeError("emos feedback down")
        self.feedback_calls.append((memory_id, feedback_type))
        return {"payload": {"status": "recorded"}}


class _FakeSkills:
    def __init__(self, ok=True):
        self.ok = ok
        self.feedback_calls = []

    def match(self, context):
        return {"total": 1, "matches": [{"skillId": "skill_fb_1"}]}

    def list_skills(self):
        return {"total": 1, "skills": [{"skill_id": "skill_fb_1", "status": "approved"}]}

    def run(self, skill_id, inputs=None, task_context=None):
        return {"run": {"run_id": "skillrun_fb_1", "skill_id": skill_id, "status": "succeeded"}}

    def feedback(self, skill_run_id, rating=None, outcome=None, comment=None):
        if not self.ok:
            raise RuntimeError("skill feedback down")
        self.feedback_calls.append((skill_run_id, rating, outcome))
        return {"status": "recorded"}


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


@pytest.fixture
def wire(monkeypatch):
    """Install fakes for the WHOLE test: the acceptance call uses them too."""
    def _wire(emos_ok=True, skill_ok=True):
        emos, skills = _FakeEmos(ok=emos_ok), _FakeSkills(ok=skill_ok)
        monkeypatch.setattr(main_mod.engine, "planner", _StubPlanner(
            [{"step": 1, "goal": "summarize", "tool": "skill_run", "risk": "medium"}]))
        monkeypatch.setattr(main_mod.engine, "emos", emos)
        monkeypatch.setattr(main_mod.engine, "skill", skills)
        monkeypatch.setattr(main_mod.engine, "freetodo", _FakeTaskHost())
        return emos, skills
    return _wire


def _completed_run():
    pa = c.post("/v1/pa/profiles",
                json={"user_id": "u_feedback", "consent_version": 1}).json()["pa_id"]
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "summarize please"}).json()["run_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
            break
        time.sleep(0.2)
    c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
    deadline = time.time() + 30
    run = c.get(f"/v1/runs/{rid}").json()
    while time.time() < deadline:
        run = c.get(f"/v1/runs/{rid}").json()
        if run["state"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    return rid, run


def test_accept_writes_feedback_to_emos_and_skill(wire):
    emos, skills = wire()
    rid, run = _completed_run()
    assert run["state"] == "completed", run["state"]
    body = c.post(f"/v1/runs/{rid}/acceptance",
                  json={"user_id": "u_feedback", "decision": "accept",
                        "comment": "looks good"}).json()
    assert "acceptance.recorded" in [e["type"] for e in body["events"]]
    assert ("mem_cited_1", "correct") in emos.feedback_calls, emos.feedback_calls
    assert skills.feedback_calls and skills.feedback_calls[0][0] == "skillrun_fb_1"
    audit = c.get(f"/v1/runs/{rid}/feedback").json()
    assert audit["total"] == 1
    record = audit["feedback"][0]
    assert record["decision"] == "accept"
    assert record["emos"] and record["skill"]
    assert record["revision_run_id"] is None


def test_request_changes_derives_a_revision_and_keeps_the_original(wire):
    emos, skills = wire()
    rid, run = _completed_run()
    original_artifacts = list(run["artifacts"])
    c.post(f"/v1/runs/{rid}/acceptance",
           json={"user_id": "u_feedback", "decision": "request_changes",
                 "comment": "use three bullet points"})
    revisions = c.get(f"/v1/runs/{rid}/revisions").json()
    assert revisions["total"] == 1, revisions
    revision = revisions["revisions"][0]
    full = c.get(f"/v1/runs/{revision['run_id']}").json()
    assert full["parent_run_id"] == rid
    assert "[修改要求] use three bullet points" in full["query_summary"]
    again = c.get(f"/v1/runs/{rid}").json()
    assert again["artifacts"] == original_artifacts
    assert again["state"] == "completed"
    assert ("mem_cited_1", "incorrect") in emos.feedback_calls
    audit = c.get(f"/v1/runs/{rid}/feedback").json()
    assert audit["feedback"][0]["revision_run_id"] == revision["run_id"]


def test_feedback_degradation_is_visible_not_silent(wire):
    wire(emos_ok=False, skill_ok=False)
    rid, _ = _completed_run()
    body = c.post(f"/v1/runs/{rid}/acceptance",
                  json={"user_id": "u_feedback", "decision": "reject",
                        "comment": "not what I asked"}).json()
    recorded = [e["payload"] for e in body["events"] if e["type"] == "acceptance.recorded"][0]
    assert recorded["feedback_writtenback"]["degraded"], recorded
    audit = c.get(f"/v1/runs/{rid}/feedback").json()
    assert audit["feedback"][0]["degraded"]
    assert audit["feedback"][0]["decision"] == "reject"
