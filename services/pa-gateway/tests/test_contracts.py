# -*- coding: utf-8 -*-
import time
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


# The gate the run has to reach is built from real dependencies (EMOS recall
# measured at 4-9s, plus Organizer and the knowledge proxy), so a run needs ~15s
# to reach waiting_approval even with the deterministic planner. The old 10s
# budget here is what made this file "flaky": it returned a run still in
# contextualizing and the manifest assertions then failed on empty context_refs.
def _wait_run(rid, timeout=45.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(f"/v1/runs/{rid}").json()
        if r["state"] in ("waiting_approval", "completed", "failed", "cancelled"):
            return r
        time.sleep(0.15)
    return c.get(f"/v1/runs/{rid}").json()


def test_openapi_has_core_paths():
    paths = set(c.get("/openapi.json").json()["paths"].keys())
    for p in ["/v1/pa/profiles", "/v1/pa/{pa_id}/messages", "/v1/runs/{run_id}",
              "/v1/runs/{run_id}/events", "/v1/runs/{run_id}/approvals",
              "/v1/runs/{run_id}/acceptance", "/v1/pa/profiles/{pa_id}/calibrate",
              "/v1/pa/profiles/{pa_id}/readiness", "/v1/server/health"]:
        assert p in paths, f"missing {p}"


def test_error_shape_and_trace_id():
    r = c.get("/v1/pa/profiles/nope")
    assert r.status_code == 404
    b = r.json()
    assert b["code"] == "NOT_FOUND" and "trace_id" in b
    assert "X-Trace-Id" in r.headers


def test_run_context_is_full_manifest():
    pa = c.post("/v1/pa/profiles", json={"user_id": "u_c"}).json()["pa_id"]
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "契约检查"}).json()["run_id"]
    run = _wait_run(rid)
    cr = run["context_refs"]
    for k in ["run_id", "query_summary", "profile_version", "consent_version",
              "memory_refs", "knowledge_refs", "observer_event_refs", "organizer_refs",
              "task_refs", "skill_refs", "redaction_log", "token_budget", "generated_at"]:
        assert k in cr, f"manifest missing {k}"


def test_pa_and_run_state_machines_match_execution_book():
    from app.models import PAState, RunState
    assert [s.value for s in PAState] == ["draft", "onboarding", "initializing", "calibrating",
                                          "trial_ready", "active", "suspended", "archived"]
    assert [s.value for s in RunState] == ["created", "admitted", "contextualizing", "planning",
                                           "waiting_approval", "executing", "verifying", "delivering",
                                           "completed", "failed", "cancelled", "expired"]


def test_openapi_has_pa_lifecycle_paths():
    paths = set(c.get("/openapi.json").json()["paths"].keys())
    for p in ["/v1/pa/profiles/{pa_id}/initialize", "/v1/pa/profiles/{pa_id}/activate"]:
        assert p in paths, f"missing {p}"
