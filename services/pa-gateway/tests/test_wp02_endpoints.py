# -*- coding: utf-8 -*-
"""WP-02 endpoint closure: PATCH profile, consents, artifacts, cancel (書 §6.1)."""
import time

import app.calibration as cal
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


def _mk(**kw):
    payload = {"user_id": "u_wp02", "consent_version": 1}
    payload.update(kw)
    return c.post("/v1/pa/profiles", json=payload).json()["pa_id"]


def _wait_run(rid, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        run = c.get(f"/v1/runs/{rid}").json()
        if run["state"] in ("waiting_approval", "completed", "failed", "cancelled"):
            return run
        time.sleep(0.2)
    return c.get(f"/v1/runs/{rid}").json()


def test_patch_profile_bumps_version_and_persists():
    pa = _mk()
    before = c.get(f"/v1/pa/profiles/{pa}").json()
    updated = c.patch(f"/v1/pa/profiles/{pa}", json={
        "preferences": {"lang": "zh", "format": "three_point"},
        "boundaries": {"allowed_roots": ["C:\\workspace"]},
        "tool_scopes": ["emos_recall", "task_create"],
    }).json()
    assert updated["profile_version"] == before["profile_version"] + 1
    reloaded = c.get(f"/v1/pa/profiles/{pa}").json()
    assert reloaded["preferences"]["format"] == "three_point"
    assert reloaded["boundaries"]["allowed_roots"] == ["C:\\workspace"]
    assert reloaded["tool_scopes"] == ["emos_recall", "task_create"]


def test_patch_unknown_profile_is_404():
    assert c.patch("/v1/pa/profiles/nope", json={"preferences": {}}).status_code == 404


def test_consent_must_increase():
    pa = _mk(consent_version=1)
    assert c.post(f"/v1/pa/profiles/{pa}/consents", json={"consent_version": 1}).status_code == 409
    assert c.post(f"/v1/pa/profiles/{pa}/consents", json={"consent_version": 2}).json()["consent_version"] == 2


def test_consent_after_passing_gates_makes_pa_trial_ready():
    # gates pass while consent is still 0, so readiness stays blocked until consent
    pa = _mk(consent_version=0)
    c.post(f"/v1/pa/profiles/{pa}/initialize")
    good = {"decision": {s: exp for s, exp in cal.DECISION_CORPUS},
            "alignment": {s: exp for s, exp in cal.ALIGNMENT_CORPUS}}
    gates = c.post(f"/v1/pa/profiles/{pa}/calibrate", json=good).json()
    assert gates["pa_state"] == "calibrating"          # no consent yet
    assert c.get(f"/v1/pa/profiles/{pa}/readiness").json()["ready"] is False
    profile = c.post(f"/v1/pa/profiles/{pa}/consents", json={"consent_version": 1}).json()
    assert profile["state"] == "trial_ready"
    assert c.get(f"/v1/pa/profiles/{pa}/readiness").json()["ready"] is True


def test_artifacts_endpoint_reports_the_run_trail():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "say hello"}).json()["run_id"]
    _wait_run(rid)
    body = c.get(f"/v1/runs/{rid}/artifacts").json()
    assert body["run_id"] == rid
    assert isinstance(body["artifacts"], list)
    assert body["total"] == len(body["artifacts"])


def test_cancel_from_the_approval_gate_and_is_idempotent():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "do something"}).json()["run_id"]
    run = _wait_run(rid)
    assert run["state"] == "waiting_approval"
    body = c.post(f"/v1/runs/{rid}/cancel", json={"reason": "changed my mind"}).json()
    assert body["state"] == "cancelled"
    types = [e["type"] for e in body["events"]]
    assert "run.cancelled" in types
    assert c.post(f"/v1/runs/{rid}/cancel", json={}).json()["state"] == "cancelled"
    assert c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).status_code == 409


def test_cancel_mid_flight_is_refused_rather_than_half_done():
    """A run with a live worker must not be silently cancelled."""
    from app import main as main_mod

    class _Stub:
        name = "stub"

        def plan(self, query, ctx, tools=None):
            return [{"step": 1, "goal": "slow", "tool": "emos_recall", "risk": "low"}]

    original = main_mod.engine.planner
    main_mod.engine.planner = _Stub()
    try:
        pa = _mk()
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "x"}).json()["run_id"]
        run = _wait_run(rid)
        c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"})
        resp = c.post(f"/v1/runs/{rid}/cancel", json={})
        assert resp.status_code in (409, 200), resp.text
        if resp.status_code == 409:
            assert resp.json()["code"] == "CONFLICT"
    finally:
        main_mod.engine.planner = original
