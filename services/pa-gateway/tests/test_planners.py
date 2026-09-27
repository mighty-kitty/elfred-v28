# -*- coding: utf-8 -*-
import json
import httpx
import app.planners as planners


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def json(self):
        return self._d


def _fake(data):
    def fake(*a, **k):
        return _FakeResp(data)
    return fake


def test_llm_plan_parses_json(monkeypatch):
    plan = [{"step": 1, "goal": "分析", "tool": "search", "risk": "low"}]
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    p = planners.LLMPlan()
    assert p.enabled
    monkeypatch.setattr(httpx, "post", _fake({"choices": [{"message": {"content": json.dumps(plan)}}]}))
    assert p.plan("q", {}) == plan


def test_letta_plan_disabled_without_agent(monkeypatch):
    monkeypatch.delenv("LETTA_AGENT_ID", raising=False)
    p = planners.LettaPlan()
    assert p.enabled is False
    steps = p.plan("q", {})
    assert any(s["tool"] == "task_create" for s in steps)  # deterministic fallback


def test_letta_plan_parses_json(monkeypatch):
    monkeypatch.setenv("LETTA_URL", "http://y")
    monkeypatch.setenv("LETTA_AGENT_ID", "agent-1")
    plan = [{"step": 1, "goal": "阅读", "tool": "knowledge_search", "risk": "low"}]
    p = planners.LettaPlan()
    assert p.enabled
    monkeypatch.setattr(httpx, "post",
                        _fake({"choices": [{"message": {"content": json.dumps(plan)}}]}))
    assert p.plan("q", {}) == plan


def test_select_planner_defaults_to_deterministic(monkeypatch):
    monkeypatch.delenv("PA_PLAN_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert planners.select_planner().name == "deterministic"


def test_sanitize_steps_drops_unavailable_tools_and_bad_rows():
    steps = [
        {"goal": "recall", "tool": "emos_recall", "risk": "low"},
        {"goal": "delegate", "tool": "opencode_delegate", "risk": "high"},
        {"goal": "", "tool": "emos_recall"},
        "not-a-dict",
        {"goal": "search", "tool": "knowledge_search", "risk": "weird"},
    ]
    out = planners.sanitize_steps(steps, tools=["emos_recall", "knowledge_search"])
    assert [s["tool"] for s in out] == ["emos_recall", "knowledge_search"]
    assert [s["step"] for s in out] == [1, 2]
    assert out[1]["risk"] == "low"  # unknown risk is normalised, not trusted


def test_llm_plan_falls_back_when_model_returns_prose(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    p = planners.LLMPlan()
    monkeypatch.setattr(httpx, "post", _fake({"choices": [{"message": {"content": "sure thing!"}}]}))
    plan = p.plan("q", {}, tools=["emos_recall"])
    assert plan and any(s["tool"] == "task_create" for s in plan)


def test_letta_plan_targets_the_openai_compatible_app_server(monkeypatch):
    """The self-hosted Letta App Server exposes each agent as an OpenAI model."""
    monkeypatch.setenv("LETTA_URL", "http://y:4500")
    monkeypatch.setenv("LETTA_AGENT_ID", "Elfred PA")
    monkeypatch.setenv("LETTA_API_KEY", "cap-token")
    captured = {}

    def fake(url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        captured["headers"] = kw.get("headers")
        return _FakeResp({"choices": [{"message": {"content": "[]"}}]})

    monkeypatch.setattr(httpx, "post", fake)
    plan = planners.LettaPlan().plan("q", {}, tools=["emos_recall"])
    assert captured["url"] == "http://y:4500/v1/chat/completions"
    assert captured["json"]["model"] == "Elfred PA"
    assert captured["headers"]["Authorization"] == "Bearer cap-token"
    # The model answered "[]" (no tool needed). That is a model answer, not a
    # backend failure, so it must NOT be relabelled as a deterministic fallback.
    steps, source = planners.LettaPlan().plan2("q", {}, tools=["emos_recall"])
    assert steps == [] and source == "letta", (steps, source)


def test_plan2_reports_model_source_on_success(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    plan = [{"goal": "recall", "tool": "emos_recall", "risk": "low"}]
    monkeypatch.setattr(httpx, "post", _fake({"choices": [{"message": {"content": json.dumps(plan)}}]}))
    steps, source = planners.LLMPlan().plan2("q", {}, tools=["emos_recall"])
    assert source == "llm"
    assert [s["tool"] for s in steps] == ["emos_recall"]


def test_plan2_reports_the_fallback_when_the_model_is_unreachable(monkeypatch):
    """Telemetry must never claim model output when the backend actually failed."""
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    steps, source = planners.LLMPlan().plan2("q", {}, tools=["emos_recall"])
    assert source == "deterministic-fallback", source
    assert steps, "a usable fallback plan is still returned"


def test_letta_plan2_reports_the_fallback_when_the_server_is_down(monkeypatch):
    monkeypatch.setenv("LETTA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("LETTA_AGENT_ID", "Elfred PA")
    steps, source = planners.LettaPlan().plan2("q", {}, tools=["emos_recall"])
    assert source == "deterministic-fallback", source
    assert steps
