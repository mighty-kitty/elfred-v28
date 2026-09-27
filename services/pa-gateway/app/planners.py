# -*- coding: utf-8 -*-
"""Plan providers. v0 deterministic; v1 uses an OpenAI-compatible model if configured."""
from __future__ import annotations
import json
import logging
import os
import time

logger = logging.getLogger("elfred.pa-gateway.planner")


def _extract_json_array(text: str):
    """Models sometimes wrap JSON in prose or code fences."""
    if not isinstance(text, str):
        return None
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:  # noqa: BLE001
        return None


RISKS = ("low", "medium", "high", "critical")


def plan_prompt(query: str, tools=None) -> str:
    """Shared planning instruction for every model-backed planner."""
    return (
        "Plan a personal agent. Reply with ONLY a compact JSON array, no prose, no "
        'explanation. Elements: {"goal":"<short>","tool":"<allowed>","risk":"low|medium|high"}. '
        f"Allowed tools: {', '.join(tools or []) or 'none'}. "
        "Use at most 3 steps; skip steps you do not need. "
        f"Request: {query}"
    )


def sanitize_steps(steps, tools=None) -> list[dict]:
    """Keep only well-formed steps whose tool is actually available.

    Execution book WP-06: a tool that is not available must never reach the plan,
    otherwise the run would report an action it cannot really perform.
    """
    if not isinstance(steps, list):
        return []
    allowed = set(tools or [])
    out: list[dict] = []
    for raw in steps:
        if not isinstance(raw, dict):
            continue
        tool = raw.get("tool")
        if allowed and tool not in allowed:
            continue
        goal = str(raw.get("goal") or "").strip()
        if not goal:
            continue
        risk = raw.get("risk") if raw.get("risk") in RISKS else "low"
        out.append({"step": len(out) + 1, "goal": goal[:200], "tool": tool, "risk": risk})
    return out


class DeterministicPlan:
    name = "deterministic"
    def plan(self, query: str, ctx: dict, tools=None) -> list[dict]:
        steps = []
        if ctx.get("knowledge"):
            steps.append({"step": 1, "goal": "读取并引用相关知识", "tool": "knowledge_search", "risk": "low"})
        if ctx.get("memory") or ctx.get("organizer"):
            steps.append({"step": 2, "goal": "结合记忆/上下文理解", "tool": "emos_recall", "risk": "low"})
        if ("技能" in query or "skill" in query.lower()) and steps:
            steps.append({"step": len(steps) + 1, "goal": "匹配并运行已批准技能", "tool": "skill_run", "risk": "medium"})
        steps.append({"step": 3, "goal": "产出可交付结果/任务", "tool": "task_create", "risk": "medium"})
        return steps

    def plan2(self, query: str, ctx: dict, tools=None):
        return self.plan(query, ctx, tools), "deterministic"


class LLMPlan:
    """Calls an OpenAI-compatible /chat/completions endpoint for a JSON plan when configured."""
    name = "llm"
    def __init__(self):
        self.base_url = os.environ.get("LLM_BASE_URL", "")
        self.api_key = os.environ.get("LLM_API_KEY", "")
        self.model = os.environ.get("LLM_MODEL", "")
        self.timeout = float(os.environ.get("PA_LLM_TIMEOUT", "25"))
        self.max_tokens = int(os.environ.get("PA_LLM_MAX_TOKENS", "500"))
        # Thinking mode costs ~2.5x the latency for a JSON plan and showed no gain
        # in plan quality, so it is off unless explicitly enabled.
        self.thinking = os.environ.get("PA_LLM_THINKING", "disabled")
        self.enabled = bool(self.base_url and self.api_key and self.model)

    def _invoke(self, prompt: str):
        """Model text, or None when the provider is unavailable or errors."""
        if not self.enabled:
            return None
        import httpx
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                "thinking": {"type": self.thinking}}
        # One bounded retry: a single transient failure must not silently downgrade
        # the plan to the deterministic fallback.
        for attempt in (1, 2):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions",
                               headers={"Authorization": f"Bearer {self.api_key}"},
                               json=body, timeout=self.timeout)
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                logger.warning("LLM plan attempt %d failed: %s", attempt, e)
                time.sleep(1.0)
        return None

    def plan2(self, query: str, ctx: dict, tools=None):
        fallback = DeterministicPlan().plan(query, ctx, tools)
        text = self._invoke(plan_prompt(query, tools))
        if text is None:
            return fallback, "deterministic-fallback"
        parsed = _extract_json_array(text)
        if parsed is None:
            # prose instead of JSON: the model did not answer the question we asked
            return fallback, "deterministic-fallback"
        plan = sanitize_steps(parsed, tools)
        # An empty plan from the model is an answer ("no tool needed"), not a failure.
        return plan, "llm"

    def plan(self, query: str, ctx: dict, tools=None) -> list[dict]:
        return self.plan2(query, ctx, tools)[0]


class LettaPlan:
    """Plans through a self-hosted Letta App Server (WP-01).

    `letta server --listen ... --openai-api` exposes every agent as a model on an
    OpenAI-compatible route, so the Letta agent — with its own identity, memory and
    system policy — is the planner. Letta exposes the agent *name* as the model id,
    which is what LETTA_MODEL holds; LETTA_AGENT_ID is the agent's real id.
    """
    name = "letta"
    def __init__(self):
        self.url = os.environ.get("LETTA_URL", "http://127.0.0.1:4500").rstrip("/")
        self.agent = os.environ.get("LETTA_MODEL", "") or os.environ.get("LETTA_AGENT_ID", "")
        self.api_key = os.environ.get("LETTA_API_KEY", "")
        self.timeout = float(os.environ.get("PA_LLM_TIMEOUT", "25"))
        self.enabled = bool(self.url and self.agent)

    def plan(self, query: str, ctx: dict, tools=None) -> list[dict]:
        return self.plan2(query, ctx, tools)[0]

    def plan2(self, query: str, ctx: dict, tools=None):
        fallback = DeterministicPlan().plan(query, ctx, tools)
        if not self.enabled:
            return fallback, "deterministic"
        import httpx
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        # One bounded retry, and the failure reason is logged: a transient App Server
        # hiccup must be diagnosable instead of silently downgrading the plan.
        for attempt in (1, 2):
            try:
                r = httpx.post(f"{self.url}/v1/chat/completions",
                               headers=headers,
                               json={"model": self.agent,
                                     "messages": [{"role": "user",
                                                   "content": plan_prompt(query, tools)}]},
                               timeout=self.timeout)
                content = r.json()["choices"][0]["message"]["content"]
                parsed = _extract_json_array(content)
                if parsed is None:
                    return fallback, "deterministic-fallback"
                return sanitize_steps(parsed, tools), "letta"
            except Exception as e:  # noqa: BLE001
                logger.warning("Letta plan attempt %d failed: %s", attempt, e)
                time.sleep(1.0)
        return fallback, "deterministic-fallback"


def select_planner():
    """Env-driven: PA_PLAN_PROVIDER = letta | llm | deterministic (default)."""
    choice = os.environ.get("PA_PLAN_PROVIDER", "").lower()
    if choice == "letta":
        p = LettaPlan()
        return p if p.enabled else DeterministicPlan()
    if choice == "llm":
        p = LLMPlan()
        return p if p.enabled else DeterministicPlan()
    p = LLMPlan()
    return p if p.enabled else DeterministicPlan()
