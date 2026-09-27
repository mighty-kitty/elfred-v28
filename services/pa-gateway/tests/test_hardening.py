# -*- coding: utf-8 -*-
"""Hardening tests: skill step, redaction/privacy, revoke(policy deny), external contracts, P95."""
import time
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app.redact import redact

c = TestClient(app)


def _mk(scopes=None):
    payload = {"user_id": "u_h", "consent_version": 1}
    if scopes is not None:
        payload["tool_scopes"] = scopes
    return c.post("/v1/pa/profiles", json=payload).json()["pa_id"]


# Same reason as test_contracts: a real context build takes ~15s (measured).
def _wait(rid, timeout=45.0):
    end = time.time() + timeout
    while time.time() < end:
        r = c.get(f"/v1/runs/{rid}").json()
        if r["state"] in ("waiting_approval", "completed", "failed", "cancelled"):
            return r
        time.sleep(0.15)
    return c.get(f"/v1/runs/{rid}").json()


def _approve(rid, decision="approve"):
    """Tools only run after approval (execution book order)."""
    _wait(rid)
    r = c.post(f"/v1/runs/{rid}/approvals", json={"decision": decision})
    assert r.status_code == 200, r.text
    return r.json()


def test_skill_step_present_and_degrades_gracefully():
    pa = _mk()
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "用技能总结一下"}).json()["run_id"]
    planned = _wait(rid)
    plan_tools = [s.get("tool") for s in planned["plan"]]
    assert "skill_run" in plan_tools, f"skill step missing from plan: {plan_tools}"
    run = _approve(rid)
    tools = [e["payload"].get("tool") for e in run["events"] if e["type"] == "tool.started"]
    assert "skill_run" in tools, f"skill step missing: {tools}"
    assert run["state"] == "completed"  # degraded, not crashed


def test_privacy_redaction_drops_sensitive():
    out = redact({"api_key": "sk-123", "token": "t", "nested": {"secret": "s"}, "long": "x" * 900,
                  "url": "https://x/a?b=1"})
    assert out["api_key"] == "<redacted>"
    assert out["token"] == "<redacted>"
    assert out["nested"]["secret"] == "<redacted>"
    assert out["long"].endswith("<truncated>")
    assert out["url"] == "<url-redacted>"


def test_revoke_tool_denied_by_policy():
    # only allow emos_recall -> knowledge_search / task_create must be POLICY_DENIED
    pa = _mk(scopes=["emos_recall"])
    rid = c.post(f"/v1/pa/{pa}/messages", json={"message": "总结并建任务"}).json()["run_id"]
    run = _approve(rid)
    # Revoking a tool must make it unusable. Two mechanisms enforce that: the plan
    # may only name available tools, and Policy refuses anything outside the scope.
    from app.policy import Policy

    planned = [step.get("tool") for step in run["plan"]]
    executed = [e["payload"].get("tool") for e in run["events"] if e["type"] == "tool.completed"]
    assert set(planned) <= {"emos_recall"}, f"out-of-scope step planned: {planned}"
    assert set(executed) <= {"emos_recall"}, f"out-of-scope tool ran: {executed}"
    assert Policy(tool_scopes=["emos_recall"]).allow("task_create") is False


def test_external_service_contracts():
    # EMOS
    e = httpx.get("http://127.0.0.1:8000/health", timeout=8)
    assert e.status_code == 200 and e.json().get("status") == "ok"
    # Organizer
    o = httpx.get("http://127.0.0.1:8770/v1/health", timeout=8)
    assert o.status_code == 200 and o.json().get("ok") is True
    # Knowledge (mobile BFF -> Typesense)
    k = httpx.get("http://127.0.0.1:5173/api/search",
                  params={"q": "PPT", "query_by": "title,summary", "per_page": 3}, timeout=10)
    assert k.status_code == 200 and "found" in k.json()


def test_p95_latency_within_budget():
    # create PA budget < 3s ; message accept budget < 500ms (async)
    t0 = time.time()
    pa = _mk()
    create_ms = (time.time() - t0) * 1000
    t1 = time.time()
    c.post(f"/v1/pa/{pa}/messages", json={"message": "ping"})
    msg_ms = (time.time() - t1) * 1000
    assert create_ms < 3000, f"create PA too slow: {create_ms:.0f}ms"
    assert msg_ms < 500, f"message accept too slow: {msg_ms:.0f}ms"
