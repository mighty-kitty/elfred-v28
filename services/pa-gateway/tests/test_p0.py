# -*- coding: utf-8 -*-
"""P0 end-to-end scenarios (execution book 12.1), against real EMOS/Organizer/Knowledge."""
import time
from fastapi.testclient import TestClient
import app.calibration as cal
from app.main import app

c = TestClient(app)


# Same reason as test_contracts: a real context build takes ~15s (measured).
def _wait_run(c: TestClient, rid: str, timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(f"/v1/runs/{rid}").json()
        if r["state"] in ("waiting_approval", "completed", "failed", "cancelled"):
            return r
        time.sleep(0.15)
    return c.get(f"/v1/runs/{rid}").json()


def _mk() -> str:
    r = c.post("/v1/pa/profiles", json={"user_id": "u_p0", "consent_version": 1, "preferences": {"lang": "zh"}})
    return r.json()["pa_id"]


def test_p0_create_pa_returns_versioned_profile():
    pa = _mk()
    p = c.get(f"/v1/pa/profiles/{pa}").json()
    assert p["pa_id"] == pa and p["profile_version"] == 1 and p["state"] in ("onboarding", "draft")


def test_p0_idempotent_profile_same_key_returned():
    pa = _mk()
    h = {"Idempotency-Key": "idem-pro-1"}
    r1 = c.post("/v1/pa/profiles", json={"user_id": "u_idem"}, headers=h)
    r2 = c.post("/v1/pa/profiles", json={"user_id": "u_idem"}, headers=h)
    assert r1.json()["pa_id"] == r2.json()["pa_id"]


def test_p0_approval_gate_blocks_until_approve():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "写文件并发送"}).json()["run_id"]
    run = _wait_run(c, rid)
    assert run["state"] == "waiting_approval"
    assert any(e["type"] == "approval.required" for e in run["events"])
    c.post(f"/v1/runs/{run['run_id']}/approvals", json={"decision": "approve"})
    r = c.get(f"/v1/runs/{run['run_id']}").json()
    assert r["state"] == "completed"


def test_p0_event_seq_monotonic():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "记录我的偏好"}).json()["run_id"]
    run = _wait_run(c, rid)
    seqs = [e["event_seq"] for e in run["events"]]
    assert seqs == sorted(seqs)


def test_p0_sse_stream_resume_by_last_event_id():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "总结"}).json()["run_id"]
    run = _wait_run(c, rid)
    ev = c.get(f"/v1/runs/{rid}/events", headers={"Last-Event-ID": "0"})
    assert ev.status_code == 200
    assert ev.headers["content-type"].startswith("text/event-stream")
    assert "event: run.created" in ev.text and "data:" in ev.text
    # resume from a later event should skip earlier ones
    last = max(e["event_seq"] for e in run["events"])
    ev2 = c.get(f"/v1/runs/{rid}/events", headers={"Last-Event-ID": str(last)})
    assert "event: run.created" not in ev2.text


def test_p0_calibration_readiness_twogate():
    pa = _mk()
    # fail both gates
    bad = {"decision": {s: "blocked" for s, _ in cal.DECISION_CORPUS},
           "alignment": {s: "wrong" for s, _ in cal.ALIGNMENT_CORPUS}}
    g = c.post(f"/v1/pa/profiles/{pa}/calibrate", json=bad).json()
    assert g["gate1"]["rate"] < 0.9
    assert c.get(f"/v1/pa/profiles/{pa}/readiness").json()["ready"] is False
    # pass both gates
    good = {"decision": {s: exp for s, exp in cal.DECISION_CORPUS},
            "alignment": {s: exp for s, exp in cal.ALIGNMENT_CORPUS}}
    c.post(f"/v1/pa/profiles/{pa}/calibrate", json=good)
    rd = c.get(f"/v1/pa/profiles/{pa}/readiness").json()
    assert rd["gate1"]["rate"] >= 0.9 and rd["gate2"]["score"] >= 0.8
    assert rd["ready"] is True  # consent_version=1


def _good_calibration() -> dict:
    return {"decision": {s: exp for s, exp in cal.DECISION_CORPUS},
            "alignment": {s: exp for s, exp in cal.ALIGNMENT_CORPUS}}


def test_p0_pa_state_machine_walk_to_active():
    """Execution book 7.1: onboarding -> initializing -> calibrating -> trial_ready -> active."""
    pa = _mk()
    assert c.get(f"/v1/pa/profiles/{pa}").json()["state"] == "onboarding"
    # cannot jump straight to active
    assert c.post(f"/v1/pa/profiles/{pa}/activate").status_code == 409
    init = c.post(f"/v1/pa/profiles/{pa}/initialize").json()
    assert init["pa"]["state"] == "calibrating"
    assert any(s["step"] == "emos_binding" for s in init["steps"])
    g = c.post(f"/v1/pa/profiles/{pa}/calibrate", json=_good_calibration()).json()
    assert g["pa_state"] == "trial_ready"
    assert c.get(f"/v1/pa/profiles/{pa}").json()["state"] == "trial_ready"
    act = c.post(f"/v1/pa/profiles/{pa}/activate").json()
    assert act["state"] == "active"
    assert c.post(f"/v1/pa/profiles/{pa}/activate").json()["state"] == "active"
    # initialized/activated PA state survives a reload from SQLite
    assert c.get(f"/v1/pa/profiles/{pa}").json()["consent_version"] == 1


def test_p0_failed_calibration_keeps_pa_out_of_trial_ready():
    pa = _mk()
    c.post(f"/v1/pa/profiles/{pa}/initialize")
    bad = {"decision": {s: "blocked" for s, _ in cal.DECISION_CORPUS},
           "alignment": {s: "wrong" for s, _ in cal.ALIGNMENT_CORPUS}}
    g = c.post(f"/v1/pa/profiles/{pa}/calibrate", json=bad).json()
    assert g["pa_state"] == "calibrating"
    assert c.post(f"/v1/pa/profiles/{pa}/activate").status_code == 409


def test_p0_reject_cancels_without_running_tools():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "summarize the project"}).json()["run_id"]
    run = _wait_run(c, rid)
    assert run["state"] == "waiting_approval"
    body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "reject"}).json()
    assert body["state"] == "cancelled"
    types = [e["type"] for e in body["events"]]
    assert "run.cancelled" in types
    assert "tool.started" not in types


def test_p0_double_approve_conflicts_and_does_not_duplicate_side_effects():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "summarize the project"}).json()["run_id"]
    _wait_run(c, rid)
    assert c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).status_code == 200
    assert c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).status_code == 409
    run = c.get(f"/v1/runs/{rid}").json()
    assert run["state"] == "completed"
    assert len(run["tool_calls"]) == len(run["plan"])


def test_p0_acceptance_requires_completed_run():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "summarize the project"}).json()["run_id"]
    _wait_run(c, rid)
    r = c.post(f"/v1/runs/{rid}/acceptance", json={"user_id": "u_p0", "decision": "accept"})
    assert r.status_code == 409


def test_p0_message_accept_state_is_deterministic():
    """The 202/accepted payload must not race with the worker thread."""
    pa = _mk()
    for _ in range(5):
        r = c.post(f"/v1/pa/{pa}/messages", json={"message": "ping"})
        assert r.status_code == 200, r.text
        assert r.json()["state"] == "created", r.json()


def test_p0_server_health_reports_real_dependency_state():
    """A dead dependency must be reported as down, never as a green light."""
    from app import main as main_mod
    from connectors import EmosClient

    good = main_mod.engine.emos
    broken = EmosClient()
    broken.base_url = "http://127.0.0.1:1"
    main_mod.engine.emos = broken
    try:
        body = c.get("/v1/server/health").json()
        assert body["emos"] == "down", body
    finally:
        main_mod.engine.emos = good
    assert c.get("/v1/server/health").json()["emos"] == "ok"


def test_p0_manifest_carries_memory_refs_from_the_pa_namespace():
    """initialize persists declared preferences; a later run must cite that memory."""
    r = c.post("/v1/pa/profiles", json={"user_id": "u_mem", "consent_version": 1,
                                        "preferences": {"lang": "zh", "format": "three_point"}})
    pa = r.json()["pa_id"]
    init = c.post(f"/v1/pa/profiles/{pa}/initialize").json()
    assert init["pa"]["emos_profile_ref"] == f"emos:{pa}"
    assert {s["step"]: s["status"] for s in init["steps"]}["emos_binding"] == "ok"
    rid = c.post(f"/v1/pa/{pa}/messages",
                 json={"message": "user declared preferences lang format"}).json()["run_id"]
    run = _wait_run(c, rid)
    refs = run["context_refs"]["memory_refs"]
    assert refs, "manifest must reference recalled memory / evidence / profile blocks"


def test_store_survives_concurrent_reads_and_writes():
    """The run worker thread and API threads share one SQLite connection."""
    import threading
    from app.db import DbStore

    store = DbStore(path=":memory:")
    profile = store.create_profile(user_id="u_threads")
    errors: list = []

    def worker() -> None:
        try:
            for i in range(400):
                store.get_profile(profile.pa_id)
                store.set_idempotent(f"k-{threading.get_ident()}-{i}", "run", "r")
                store.get_idempotent(f"k-{threading.get_ident()}-{i}")
                store.set_calibration(profile.pa_id, {"decision": {}}, {"gate1": {}})
                store.get_calibration(profile.pa_id)
                store.save_profile(profile)
                created = store.create_run(profile.pa_id, "concurrent")
                store.get_run(created.run_id)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors[:3]


def test_unknown_tool_is_dropped_from_the_plan():
    """A tool the gateway does not offer must never reach the plan at all."""
    from app import main as main_mod

    class _StubPlan:
        name = "stub"

        def plan(self, query, ctx, tools=None):
            # a tool name that is deliberately not in the registry
            return [{"step": 1, "goal": "do something imaginary",
                     "tool": "totally_unknown_tool", "risk": "high"}]

    original = main_mod.engine.planner
    main_mod.engine.planner = _StubPlan()
    try:
        pa = _mk()
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "delegate"}).json()["run_id"]
        run = _wait_run(c, rid)
        assert run["state"] == "waiting_approval"
        assert run["plan"] == [], run["plan"]
        created = [e["payload"] for e in run["events"] if e["type"] == "plan.created"][-1]
        assert created["dropped_tools"] == ["totally_unknown_tool"], created
        body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    finally:
        main_mod.engine.planner = original
    types = [e["type"] for e in body["events"]]
    assert "tool.completed" not in types, "a tool that is not offered must never run"


def test_registered_tool_without_implementation_is_reported(monkeypatch):
    """Defense in depth: even if a tool name slips through, it cannot look done."""
    from app import main as main_mod
    from app import policy as policy_mod

    class _StubPlan:
        name = "stub"

        def plan(self, query, ctx, tools=None):
            return [{"step": 1, "goal": "half-implemented tool", "tool": "task_archive",
                     "risk": "low"}]

    monkeypatch.setattr(policy_mod, "TOOL_REGISTRY", policy_mod.TOOL_REGISTRY + ["task_archive"])
    original = main_mod.engine.planner
    main_mod.engine.planner = _StubPlan()
    try:
        pa = _mk()
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "archive"}).json()["run_id"]
        run = _wait_run(c, rid)
        body = c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    finally:
        main_mod.engine.planner = original
    errors = [e["payload"].get("error") for e in body["events"] if e["type"] == "tool.failed"]
    assert "TOOL_UNAVAILABLE" in errors, errors
    assert "tool.completed" not in [e["type"] for e in body["events"]]


def test_initialize_binds_letta_agent_only_when_verified(monkeypatch):
    """The binding must come from the running App Server, never from config alone."""
    from app import main as main_mod

    class _Ok:
        def models(self):
            return {"data": [{"id": "Elfred PA"}]}

    class _Down:
        def models(self):
            raise RuntimeError("connection refused")

    monkeypatch.setenv("LETTA_AGENT_ID", "agent-local-test")
    monkeypatch.setenv("LETTA_MODEL", "Elfred PA")

    monkeypatch.setattr(main_mod, "LettaClient", lambda: _Ok())
    pa = c.post("/v1/pa/profiles", json={"user_id": "u_letta", "consent_version": 1}).json()["pa_id"]
    steps = {s["step"]: s["status"] for s in c.post(f"/v1/pa/profiles/{pa}/initialize").json()["steps"]}
    assert steps["letta_agent"] == "ok", steps
    assert c.get(f"/v1/pa/profiles/{pa}").json()["letta_agent_id"] == "agent-local-test"

    monkeypatch.setattr(main_mod, "LettaClient", lambda: _Down())
    pa2 = c.post("/v1/pa/profiles", json={"user_id": "u_letta2", "consent_version": 1}).json()["pa_id"]
    steps2 = {s["step"]: s["status"] for s in c.post(f"/v1/pa/profiles/{pa2}/initialize").json()["steps"]}
    assert steps2["letta_agent"] == "degraded", steps2
    assert c.get(f"/v1/pa/profiles/{pa2}").json()["letta_agent_id"] is None


def test_interrupted_runs_are_failed_on_startup():
    """A run left in flight by a crash is closed honestly, never silently resumed."""
    from app.db import DbStore
    from app.engine import RunEngine
    from app.models import RunState

    store = DbStore(path=":memory:")
    profile = store.create_profile(user_id="u_recover")
    stuck = store.create_run(profile.pa_id, "was mid-flight")
    stuck.state = RunState.executing
    store.save_run(stuck)
    parked = store.create_run(profile.pa_id, "waiting for the user")
    parked.state = RunState.waiting_approval
    store.save_run(parked)

    engine = RunEngine(store)
    assert engine.recover_interrupted_runs() == 1
    assert store.get_run(stuck.run_id).state == RunState.failed
    events = store.get_run(stuck.run_id).events
    types = [(e["type"] if isinstance(e, dict) else e.type) for e in events]
    assert "run.failed" in types
    # A run parked at the approval gate belongs to the user, not to the restart.
    assert store.get_run(parked.run_id).state == RunState.waiting_approval
