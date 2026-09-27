# -*- coding: utf-8 -*-
"""pause / resume semantics (book section 6.1).

Phase-1 pauses a run at its current state: a paused run cannot advance (approval is
refused) until it is resumed. Mid-execution pause is refused honestly instead of
being faked, because approval still executes inline.
"""
import time

import app.main as main_mod
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _mk():
    return c.post("/v1/pa/profiles",
                  json={"user_id": "u_pause", "consent_version": 1}).json()["pa_id"]


def _parked_run():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "do something"}).json()["run_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        run = c.get(f"/v1/runs/{rid}").json()
        if run["state"] == "waiting_approval":
            return rid, run
        time.sleep(0.2)
    raise AssertionError("run never reached the approval gate")


def test_pause_freezes_the_run_and_blocks_approval():
    rid, _ = _parked_run()
    paused = c.post(f"/v1/runs/{rid}/pause").json()
    assert paused["paused"] is True
    assert paused["state"] == "waiting_approval"
    flags = [e["payload"].get("paused") for e in paused["events"]
             if e["type"] == "run.status_changed"]
    assert True in flags, "pausing must be visible in the event stream"
    blocked = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "CONFLICT"
    assert c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval"


def test_resume_unblocks_the_run():
    rid, _ = _parked_run()
    c.post(f"/v1/runs/{rid}/pause")
    resumed = c.post(f"/v1/runs/{rid}/resume").json()
    assert resumed["paused"] is False
    body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    assert body["state"] in ("completed", "failed"), body["state"]


def test_pause_is_idempotent_and_resume_on_unpaused_is_a_noop():
    rid, _ = _parked_run()
    assert c.post(f"/v1/runs/{rid}/pause").json()["paused"] is True
    assert c.post(f"/v1/runs/{rid}/pause").json()["paused"] is True
    assert c.post(f"/v1/runs/{rid}/resume").json()["paused"] is False
    assert c.post(f"/v1/runs/{rid}/resume").json()["paused"] is False


def test_finished_runs_cannot_be_paused():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "reject me"}).json()["run_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
            break
        time.sleep(0.2)
    c.post(f"/v1/runs/{rid}/approvals", json={"decision": "reject"})
    assert c.post(f"/v1/runs/{rid}/pause").status_code == 409


def test_mid_execution_pause_is_refused_not_faked():
    """Approval runs inline in Phase-1, so a run that is executing cannot be paused."""
    from app.models import RunState

    engine = main_mod.engine
    run = engine.store.create_run(_mk(), "inline execution")
    run.state = RunState.executing
    engine.store.save_run(run)
    resp = c.post(f"/v1/runs/{run.run_id}/pause")
    assert resp.status_code == 409, resp.text
    assert "async executor" in resp.json()["message"]
