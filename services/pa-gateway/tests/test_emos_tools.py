# -*- coding: utf-8 -*-
"""EMOS tools beyond recall/write: plan_write, reflect, supersede (preference change)."""
import time

import app.main as main_mod
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


class _FakeEmos:
    """Records calls so the tests can assert the exact memory lifecycle."""

    def __init__(self, write_ok=True, old_memory="mem_old"):
        self.write_ok = write_ok
        self.old_memory = old_memory
        self.calls = []

    def recall(self, user_id, query_text, **kw):
        self.calls.append(("recall", user_id, query_text))
        recalled = {"memory_id": self.old_memory} if self.old_memory else None
        return {"payload": {"recalled_memory": recalled, "evidence": []}}

    def write(self, user_id, session_id, text, **kw):
        self.calls.append(("write", user_id, text))
        if not self.write_ok:
            return {"payload": {"memory_written": False, "memory_id": None,
                                "write_policy": {"reasons": ["low_signal"]}}}
        return {"payload": {"memory_written": True, "memory_id": "mem_new"}}

    def write_plan(self, user_id, session_id, text, **kw):
        self.calls.append(("write_plan", user_id, text))
        return {"payload": {"suggested_action": "write_new_memory"}}

    def reflect(self, user_id, session_id=None, persist=False):
        self.calls.append(("reflect", user_id, persist))
        return {"payload": {"reflection_id": "refl_1"}}

    def supersede(self, user_id, session_id, source_memory_id, replacement_memory_id,
                  reason=""):
        self.calls.append(("supersede", source_memory_id, replacement_memory_id))
        return {"payload": {"status": "superseded"}}


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _run(tool, goal, emos):
    engine = main_mod.engine
    original_planner, original_emos = engine.planner, engine.emos
    engine.planner = _StubPlanner(
        [{"step": 1, "goal": goal, "tool": tool, "risk": "low"}])
    engine.emos = emos
    try:
        pa = c.post("/v1/pa/profiles",
                    json={"user_id": "u_emos", "consent_version": 1}).json()["pa_id"]
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": goal}).json()["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
                break
            time.sleep(0.2)
        return c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    finally:
        engine.planner, engine.emos = original_planner, original_emos


def _completed(body):
    return [e["payload"].get("tool") for e in body["events"] if e["type"] == "tool.completed"]


def _failed(body):
    return [e["payload"] for e in body["events"] if e["type"] == "tool.failed"]


def test_plan_write_records_the_emos_decision():
    emos = _FakeEmos()
    body = _run("emos_plan_write", "summarize the project", emos)
    assert _completed(body) == ["emos_plan_write"], _failed(body)
    assert any(call[0] == "write_plan" for call in emos.calls)
    envelope = [t for t in body["tool_calls"] if t["status"] == "completed"][0]
    assert any(ref.startswith("emos-plan:") for ref in envelope["evidence_refs"])


def test_reflect_defaults_to_not_persisting():
    emos = _FakeEmos()
    body = _run("emos_reflect", "reflect on this week", emos)
    assert _completed(body) == ["emos_reflect"], _failed(body)
    reflect_calls = [call for call in emos.calls if call[0] == "reflect"]
    assert reflect_calls and reflect_calls[0][2] is False, reflect_calls


def test_supersede_writes_new_value_and_invalidates_the_old_one():
    emos = _FakeEmos()
    body = _run("emos_supersede", "I now want summaries in Chinese", emos)
    assert _completed(body) == ["emos_supersede"], _failed(body)
    assert ("supersede", "mem_old", "mem_new") in emos.calls, emos.calls
    memory = [a for a in body["artifacts"] if a.get("type") == "memory"][0]
    assert memory["new_memory_id"] == "mem_new"
    assert memory["superseded_memory_id"] == "mem_old"
    assert memory["run_id"] == body["run_id"]


def test_supersede_without_a_previous_value_still_stores_the_new_one():
    emos = _FakeEmos(old_memory=None)
    body = _run("emos_supersede", "my new preference: five bullet points", emos)
    assert _completed(body) == ["emos_supersede"], _failed(body)
    assert not any(call[0] == "supersede" for call in emos.calls)
    memory = [a for a in body["artifacts"] if a.get("type") == "memory"][0]
    assert memory["superseded_memory_id"] is None


def test_a_refused_write_is_reported_not_hidden():
    emos = _FakeEmos(write_ok=False)
    body = _run("emos_supersede", "x", emos)
    failed = _failed(body)
    assert failed and failed[0]["tool"] == "emos_supersede", failed
    assert failed[0]["error"] == "INVALID_OUTPUT"
    assert "low_signal" in failed[0]["detail"]
    assert not [a for a in body["artifacts"] if a.get("type") == "memory"]
