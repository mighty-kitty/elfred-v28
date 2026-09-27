from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Protocol


class ConfirmationRequired(RuntimeError):
    pass


class ExecutionAdapter(Protocol):
    def can_execute(
        self, skill: dict[str, Any], context: dict[str, Any]
    ) -> bool: ...

    def dry_run(
        self, skill: dict[str, Any], inputs: dict[str, Any]
    ) -> dict[str, Any]: ...

    def execute(
        self,
        skill: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class ElfredTaskExecutionAdapter:
    """MVP adapter using Elfred's existing FreeTodo task capability."""

    SUPPORTED_ACTIONS = {
        "read_text_input",
        "extract_key_points",
        "compose_summary",
        "update_freetodo_task",
        "verify_task_completion",
    }

    def __init__(self, freetodo_client: Any) -> None:
        self.client = freetodo_client

    def can_execute(
        self, skill: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        workflow = (skill.get("current_version") or {}).get("workflow") or {}
        actions = {
            str(step.get("action") or "")
            for step in workflow.get("steps") or []
        }
        return bool(actions) and actions.issubset(self.SUPPORTED_ACTIONS)

    def dry_run(
        self, skill: dict[str, Any], inputs: dict[str, Any]
    ) -> dict[str, Any]:
        workflow = (skill.get("current_version") or {}).get("workflow") or {}
        steps = workflow.get("steps") or []
        requires_confirmation = workflow.get("riskLevel") == "high" or any(
            step.get("requiresConfirmation") for step in steps
        )
        return {
            "adapter": "ElfredTaskExecutionAdapter",
            "steps": [
                {
                    "id": step.get("id"),
                    "action": step.get("action"),
                    "sourceAction": step.get("sourceAction"),
                    "tool": step.get("tool"),
                    "arguments": step.get("arguments") or {},
                }
                for step in steps
            ],
            "requiresConfirmation": requires_confirmation,
            "inputKeys": sorted(inputs),
        }

    def execute(
        self,
        skill: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        plan = self.dry_run(skill, inputs)
        if plan["requiresConfirmation"] and not context.get("userConfirmed"):
            raise ConfirmationRequired(
                "This Skill contains a dangerous or irreversible action"
            )
        todo_id = context.get("freetodoTodoId")
        if todo_id is None:
            raise ValueError("freetodoTodoId is required")
        todo = self.client.get_todo(int(todo_id))
        version = str(
            (skill.get("current_version") or {}).get("version") or "unknown"
        )
        state: dict[str, Any] = {
            "todo": todo,
            "todoId": int(todo_id),
            "version": version,
            "sourceText": str(
                inputs.get("sourceText")
                or todo.get("description")
                or todo.get("user_notes")
                or ""
            ).strip(),
            "bulletCount": int(inputs.get("bulletCount") or 3),
            "outputLanguage": str(inputs.get("outputLanguage") or "zh-CN"),
            "stepResults": [],
        }
        for step in (
            (skill.get("current_version") or {}).get("workflow") or {}
        ).get("steps") or []:
            if step.get("condition") and not self._condition_met(
                str(step["condition"]), inputs
            ):
                state["stepResults"].append(
                    {
                        "id": step.get("id"),
                        "action": step.get("action"),
                        "status": "skipped",
                        "reason": "condition_not_met",
                    }
                )
                continue
            action = str(step.get("action") or "")
            handler = getattr(self, f"_action_{action}", None)
            if handler is None:
                raise ValueError(f"unsupported_workflow_action: {action}")
            handler(state, step)
            state["stepResults"].append(
                {
                    "id": step.get("id"),
                    "action": action,
                    "tool": step.get("tool"),
                    "status": "succeeded",
                }
            )
        if not state.get("updated"):
            raise RuntimeError("workflow_did_not_update_target_task")
        return {
            "status": "completed",
            "summary": state["summary"],
            "keyPoints": state["points"],
            "freetodoTodoId": int(todo_id),
            "completedAt": state["completedAt"],
            "completedBySkill": version,
            "task": state["updated"],
            "stepResults": state["stepResults"],
        }

    def validate_historical_case(
        self,
        workflow: dict[str, Any],
        trajectory: dict[str, Any],
    ) -> dict[str, Any]:
        """Safely replay one historical sample without touching FreeTodo."""

        steps = workflow.get("steps") or []
        actions = {str(step.get("action") or "") for step in steps}
        supported = bool(actions) and actions.issubset(self.SUPPORTED_ACTIONS)
        if not supported:
            return {
                "taskId": trajectory.get("taskId"),
                "mode": "safe_simulation",
                "passed": False,
                "mutatedHistoricalTask": False,
                "checks": {"workflowSupported": False},
                "error": "unsupported_workflow_action",
            }
        if workflow.get("riskLevel") == "high" or any(
            step.get("requiresConfirmation") for step in steps
        ):
            return {
                "taskId": trajectory.get("taskId"),
                "mode": "safe_simulation",
                "passed": False,
                "mutatedHistoricalTask": False,
                "checks": {
                    "workflowSupported": True,
                    "dangerousActionAbsent": False,
                },
                "error": "unsafe_workflow_not_simulated",
            }

        inputs = dict(trajectory.get("inputs") or {})
        state: dict[str, Any] = {
            "version": "safe-replay",
            "sourceText": str(inputs.get("sourceText") or "").strip(),
            "bulletCount": int(inputs.get("bulletCount") or 3),
            "outputLanguage": str(
                inputs.get("outputLanguage") or "zh-CN"
            ),
            "stepResults": [],
        }
        try:
            for step in steps:
                if step.get("condition") and not self._condition_met(
                    str(step["condition"]), inputs
                ):
                    continue
                action = str(step.get("action") or "")
                if action == "update_freetodo_task":
                    if not state.get("summary"):
                        raise RuntimeError("summary_not_composed")
                    state["updated"] = {
                        "status": "completed",
                        "percent_complete": 100,
                    }
                    state["completedAt"] = "simulated"
                else:
                    handler = getattr(self, f"_action_{action}", None)
                    if handler is None:
                        raise ValueError(
                            f"unsupported_workflow_action: {action}"
                        )
                    handler(state, step)
                state["stepResults"].append(
                    {
                        "id": step.get("id"),
                        "action": action,
                        "status": "simulated",
                    }
                )
        except Exception as error:
            return {
                "taskId": trajectory.get("taskId"),
                "mode": "safe_simulation",
                "passed": False,
                "mutatedHistoricalTask": False,
                "checks": {
                    "workflowSupported": True,
                    "inputAccepted": bool(state["sourceText"]),
                    "simulationCompleted": False,
                },
                "error": str(error)[:240],
            }

        summary = str(state.get("summary") or "")
        historical_outputs = trajectory.get("outputs") or []
        expected_points = max(2, min(5, state["bulletCount"]))
        checks = {
            "workflowSupported": True,
            "inputAccepted": bool(state["sourceText"]),
            "outputProduced": bool(summary),
            "outputShapeMatched": len(state.get("points") or [])
            == expected_points,
            "historicalOutputAvailable": self._historical_output_available(
                historical_outputs
            ),
            "successContractAvailable": bool(
                trajectory.get("successSignals")
            ),
            "completionPostcondition": (
                str((state.get("updated") or {}).get("status") or "")
                == "completed"
                and int(
                    (state.get("updated") or {}).get(
                        "percent_complete"
                    )
                    or 0
                )
                == 100
            ),
        }
        return {
            "taskId": trajectory.get("taskId"),
            "mode": "safe_simulation",
            "passed": all(checks.values()),
            "mutatedHistoricalTask": False,
            "checks": checks,
            "simulatedStepCount": len(state["stepResults"]),
            "outputDigest": hashlib.sha256(
                summary.encode("utf-8")
            ).hexdigest()[:16],
        }

    @staticmethod
    def _historical_output_available(outputs: list[Any]) -> bool:
        for item in outputs:
            if isinstance(item, dict):
                if any(
                    value not in (None, "", [], {})
                    for key, value in item.items()
                    if key not in {"type", "runId"}
                ):
                    return True
            elif item not in (None, ""):
                return True
        return False

    @staticmethod
    def _condition_met(condition: str, inputs: dict[str, Any]) -> bool:
        value = condition.strip()
        if not value:
            return True
        if value.startswith("has:"):
            return bool(inputs.get(value.split(":", 1)[1]))
        return False

    @staticmethod
    def _action_read_text_input(
        state: dict[str, Any], step: dict[str, Any]
    ) -> None:
        if len(state["sourceText"]) < 20:
            raise ValueError(
                "source_text_required: provide at least 20 characters"
            )

    def _action_extract_key_points(
        self, state: dict[str, Any], step: dict[str, Any]
    ) -> None:
        points = self._key_points(
            state["sourceText"], state["bulletCount"]
        )
        if not points:
            raise ValueError("no_key_points_extracted")
        state["points"] = points

    @staticmethod
    def _action_compose_summary(
        state: dict[str, Any], step: dict[str, Any]
    ) -> None:
        points = state.get("points") or []
        state["summary"] = "关键要点：\n" + "\n".join(
            f"- {point}" for point in points
        )

    def _action_update_freetodo_task(
        self, state: dict[str, Any], step: dict[str, Any]
    ) -> None:
        if not state.get("summary"):
            raise RuntimeError("summary_not_composed")
        completed_at = datetime.now().astimezone().isoformat()
        marker = f"由 Skill v{state['version']} 完成"
        state["updated"] = self.client.update_todo(
            state["todoId"],
            {
                "status": "completed",
                "percent_complete": 100,
                "completed_at": completed_at,
                "user_notes": f"{marker}\n\n{state['summary']}",
            },
        )
        state["completedAt"] = completed_at

    @staticmethod
    def _action_verify_task_completion(
        state: dict[str, Any], step: dict[str, Any]
    ) -> None:
        updated = state.get("updated") or {}
        if (
            str(updated.get("status") or "") != "completed"
            or int(updated.get("percent_complete") or 0) != 100
        ):
            raise RuntimeError("task_completion_verification_failed")
        if len(state.get("points") or []) != max(
            2, min(5, state["bulletCount"])
        ):
            raise RuntimeError("summary_bullet_count_verification_failed")
        if state["outputLanguage"].casefold().startswith("zh") and not re.search(
            r"[\u4e00-\u9fff]", state.get("summary") or ""
        ):
            raise RuntimeError("summary_language_verification_failed")

    @staticmethod
    def _key_points(text: str, limit: int) -> list[str]:
        limit = max(2, min(5, limit))
        candidates = [
            " ".join(item.split())
            for item in re.split(r"(?<=[。！？.!?；;])\s*|\n+", text)
            if len(" ".join(item.split())) >= 8
        ]
        if not candidates:
            candidates = [" ".join(text.split())]
        if len(candidates) < limit:
            expanded: list[str] = []
            for candidate in candidates:
                fragments = [
                    " ".join(item.split())
                    for item in re.split(r"[，,、：:]", candidate)
                    if len(" ".join(item.split())) >= 8
                ]
                expanded.extend(fragments or [candidate])
            if len(expanded) >= len(candidates):
                candidates = expanded
        points: list[str] = []
        for value in candidates:
            point = value.strip(" -•\t")[:180]
            if point and point not in points:
                points.append(point)
            if len(points) >= limit:
                break
        return points
