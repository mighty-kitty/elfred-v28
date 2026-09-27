# -*- coding: utf-8 -*-
"""Closed-loop integration test for the PA Gateway-lite.
Requires EMOS(:8000), Organizer(:8770), mobile knowledge(:5173) to be running;
FreeTodo connector degrades gracefully if its adapter is down.
"""
import time
from fastapi.testclient import TestClient
from app.main import app


# Same reason as test_contracts: a real context build takes ~15s (measured).
def _wait_run(c: TestClient, rid: str, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(f"/v1/runs/{rid}").json()
        if r["state"] in ("waiting_approval", "completed", "failed", "cancelled"):
            return r
        time.sleep(0.15)
    return c.get(f"/v1/runs/{rid}").json()


def test_closed_loop_roundtrip():
    c = TestClient(app)
    r = c.post("/v1/pa/profiles", json={
        "user_id": "u1",
        "preferences": {"lang": "zh", "format": "三点"},
        "consent_version": 1,
        "knowledge_sources": ["project_docs"],
    })
    assert r.status_code == 200, r.text
    pa_id = r.json()["pa_id"]

    r2 = c.post(f"/v1/pa/{pa_id}/messages", json={"message": "总结当前项目并建一个周一要完成的任务"})
    assert r2.status_code == 200, r2.text
    run = _wait_run(c, r2.json()["run_id"])
    rid = run["run_id"]
    # execution book order: the run must STOP at waiting_approval, tools run only after approval
    assert run["state"] == "waiting_approval"
    assert run["plan"], "no plan produced"
    assert run["context_refs"], "no context assembled"
    types = [e["type"] for e in run["events"]]
    for expected in ("run.created", "context.started", "context.completed", "plan.created",
                     "approval.required"):
        assert expected in types, f"missing event {expected}"
    assert "tool.started" not in types, "tools must not run before approval"
    states = [e["payload"].get("state") for e in run["events"] if e["type"] == "run.status_changed"]
    assert states == ["admitted", "contextualizing", "planning", "waiting_approval"], states

    r3 = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["state"] == "completed"
    after = [e["type"] for e in r3.json()["events"]]
    for expected in ("approval.resolved", "tool.requested", "tool.started", "tool.completed",
                     "artifact.created", "delivery.ready", "run.completed"):
        assert expected in after, f"missing post-approval event {expected}"
    assert after.index("approval.resolved") < after.index("tool.started")

    r4 = c.post(f"/v1/runs/{rid}/acceptance",
                json={"user_id": "u1", "decision": "accept", "comment": "ok"})
    assert r4.status_code == 200, r4.text
    assert r4.json()["state"] == "completed"
    types_after = [e["type"] for e in r4.json()["events"]]
    assert "acceptance.recorded" in types_after

    rd = c.get(f"/v1/pa/profiles/{pa_id}/readiness")
    assert rd.status_code == 200
    body = rd.json()
    assert "ready" in body and "gate1" in body and "gate2" in body


def test_idempotent_run_seq_is_monotonic():
    c = TestClient(app)
    pa = c.post("/v1/pa/profiles", json={"user_id": "u2"}).json()["pa_id"]
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "hello"}).json()["run_id"]
    run = _wait_run(c, rid)
    seqs = [e["event_seq"] for e in run["events"]]
    assert seqs == sorted(seqs), "event_seq not monotonic"
