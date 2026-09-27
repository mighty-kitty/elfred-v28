from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SKILL_STATES = {"draft", "pending_review", "approved", "active", "deprecated"}
BUILD_STATES = {
    "idle",
    "candidate",
    "selected",
    "fusing",
    "extracting",
    "validating",
    "draft_ready",
    "approved",
    "failed",
}


@dataclass
class TrajectoryStep:
    sequence: int
    action_type: str
    tool: str
    target: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    observation_before: dict[str, Any] = field(default_factory=dict)
    observation_after: dict[str, Any] = field(default_factory=dict)
    result: str = "success"
    optional: bool = False
    condition: str | None = None


@dataclass
class TaskTrajectory:
    task_id: str
    freetodo_todo_id: int
    intent: str
    inputs: dict[str, Any]
    context_apps: list[str]
    steps: list[TrajectoryStep]
    outputs: list[dict[str, Any]]
    success_signals: list[str]
    corrections: list[dict[str, Any]]
    summary: str = ""
    started_at: str | None = None
    ended_at: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    source_quality: str = "inferred"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["steps"] = [
            {
                "sequence": step.sequence,
                "actionType": step.action_type,
                "tool": step.tool,
                "target": step.target,
                "arguments": step.arguments,
                "observationBefore": step.observation_before,
                "observationAfter": step.observation_after,
                "result": step.result,
                "optional": step.optional,
                "condition": step.condition,
            }
            for step in self.steps
        ]
        result.update(
            {
                "taskId": result.pop("task_id"),
                "freetodoTodoId": result.pop("freetodo_todo_id"),
                "contextApps": result.pop("context_apps"),
                "successSignals": result.pop("success_signals"),
                "startedAt": result.pop("started_at"),
                "endedAt": result.pop("ended_at"),
                "evidenceRefs": result.pop("evidence_refs"),
                "sourceQuality": result.pop("source_quality"),
            }
        )
        return result


@dataclass
class ValidationResult:
    valid: bool
    score: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
