# -*- coding: utf-8 -*-
"""Policy engine: tool allow/deny, risk tiers, approval gating, step caps, timeouts."""
from __future__ import annotations
import os


# Tools the gateway can really execute today. A tool is added here only when it
# has an implementation in RunEngine._execute (execution book WP-06: unavailable
# tools must not be offered to the planner or the model).
TOOL_REGISTRY = [
    "emos_recall",
    "emos_write",
    "emos_forget",
    "emos_block_set",
    "emos_plan_write",
    "emos_reflect",
    "emos_supersede",
    "knowledge_search",
    "task_create",
    "task_search",
    "task_update",
    "task_complete",
    "skill_run",
    "skill_match",
    "local_file_read",
    "local_file_write",
    "opencode_delegate",
]


class Policy:
    MAX_STEPS = int(os.environ.get("PA_MAX_STEPS", "10"))
    HIGH_RISK_REQUIRES_APPROVAL = True

    # Tools that change something outside the run: a second, tool-scoped approval
    # can be required for these (opt-in per profile, see needs_second_approval).
    HIGH_RISK_TOOLS = {"local_file_write", "emos_write", "emos_forget",
                       "emos_block_set", "task_complete", "skill_run",
                       "opencode_delegate"}

    def __init__(self, tool_scopes=None, boundaries=None):
        self.tool_scopes = set(tool_scopes or [])
        self.boundaries = boundaries or {}

    def second_approval_tools(self) -> set:
        """Which tools need their own approval, from the profile's boundaries.

        `true` means every high-risk tool, a list means exactly those tools, and
        anything else means the run-level approval is the only gate.
        """
        configured = self.boundaries.get("tool_approval_required")
        if configured is True:
            return set(self.HIGH_RISK_TOOLS)
        if isinstance(configured, list):
            return {str(name) for name in configured}
        return set()

    def needs_second_approval(self, tool: str) -> bool:
        return tool in self.second_approval_tools()

    def allow(self, tool: str) -> bool:
        """Tool only allowed if in the profile's scope (empty scope = allow all)."""
        if self.tool_scopes and tool not in self.tool_scopes:
            return False
        return True

    def risk_of(self, step: dict) -> str:
        return step.get("risk", "low")

    def requires_approval(self, step: dict) -> bool:
        return self.HIGH_RISK_REQUIRES_APPROVAL and self.risk_of(step) in ("high", "critical")

    def cap_steps(self, steps: list[dict]) -> list[dict]:
        return steps[: self.MAX_STEPS]

    def available_tools(self) -> list[str]:
        """Registered tools this profile is allowed to use."""
        return [tool for tool in TOOL_REGISTRY if self.allow(tool)]

    def tool_timeout(self, tool: str) -> float:
        return float(os.environ.get("PA_TOOL_TIMEOUT", "15"))
