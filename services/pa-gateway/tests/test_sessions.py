# -*- coding: utf-8 -*-
"""Cross-device pairing: PC starts a run, mobile joins and both watch one run."""
import time

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _mk_pa():
    return c.post("/v1/pa/profiles",
                  json={"user_id": "u_session", "consent_version": 1}).json()["pa_id"]


def _parked_run(pa_id):
    rid = c.post(f"/v1/pa/{pa_id}/messages",
                 json={"message": "cross device task"}).json()["run_id"]
    deadline = time.time() + 20
    while time.time() < deadline:
        run = c.get(f"/v1/runs/{rid}").json()
        if run["state"] in ("waiting_approval", "completed", "failed"):
            return run
        time.sleep(0.2)
    return c.get(f"/v1/runs/{rid}").json()


def test_pc_creates_the_session_then_mobile_joins_it():
    pa = _mk_pa()
    created = c.post(f"/v1/pa/{pa}/sessions",
                     json={"device_id": "pc-1", "role": "pc"}).json()
    assert created["session_id"].startswith("sess_")
    assert [d["device_id"] for d in created["devices"]] == ["pc-1"]
    assert created["run"] is None

    joined = c.post(f"/v1/pa/{pa}/sessions",
                    json={"session_id": created["session_id"],
                          "device_id": "phone-1", "role": "mobile"}).json()
    assert joined["session_id"] == created["session_id"]
    assert sorted(d["device_id"] for d in joined["devices"]) == ["pc-1", "phone-1"]


def test_both_devices_see_the_same_run_state():
    pa = _mk_pa()
    session = c.post(f"/v1/pa/{pa}/sessions",
                     json={"device_id": "pc-1", "role": "pc"}).json()["session_id"]
    run = _parked_run(pa)
    c.post(f"/v1/sessions/{session}/focus", json={"run_id": run["run_id"]})

    phone = c.post(f"/v1/pa/{pa}/sessions",
                   json={"session_id": session, "device_id": "phone-1",
                         "role": "mobile"}).json()
    assert phone["run"]["run_id"] == run["run_id"]
    assert phone["run"]["state"] == run["state"]
    assert phone["run"]["awaiting_approval"] is True

    # mobile approves; the PC sees the very same run move forward
    c.post(f"/v1/runs/{run['run_id']}/approvals", json={"decision": "approve"})
    deadline = time.time() + 40
    while time.time() < deadline:
        pc_view = c.get(f"/v1/sessions/{session}").json()
        if pc_view["run"]["state"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.3)
    assert pc_view["run"]["run_id"] == run["run_id"]
    assert pc_view["run"]["state"] in ("completed", "failed")


def test_session_cannot_be_hijacked_by_another_pa():
    pa_one, pa_two = _mk_pa(), _mk_pa()
    session = c.post(f"/v1/pa/{pa_one}/sessions",
                     json={"device_id": "pc-1", "role": "pc"}).json()["session_id"]
    hijack = c.post(f"/v1/pa/{pa_two}/sessions",
                    json={"session_id": session, "device_id": "attacker"})
    assert hijack.status_code == 409
    other_run = c.post(f"/v1/pa/{pa_two}/messages",
                       json={"message": "other"}).json()["run_id"]
    assert c.post(f"/v1/sessions/{session}/focus",
                  json={"run_id": other_run}).status_code == 409


def test_closed_session_refuses_new_devices():
    pa = _mk_pa()
    session = c.post(f"/v1/pa/{pa}/sessions",
                     json={"device_id": "pc-1", "role": "pc"}).json()["session_id"]
    assert c.post(f"/v1/sessions/{session}/close").json()["status"] == "closed"
    assert c.post(f"/v1/sessions/{session}/close").json()["status"] == "closed"
    refused = c.post(f"/v1/pa/{pa}/sessions",
                     json={"session_id": session, "device_id": "late"})
    assert refused.status_code == 409


def test_unknown_session_and_missing_device_are_rejected():
    pa = _mk_pa()
    assert c.get("/v1/sessions/sess_missing").status_code == 404
    assert c.post(f"/v1/pa/{pa}/sessions", json={"role": "pc"}).status_code == 422
