from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from adapter.skill_foundry.maturity import SkillMaturityAssessor


DATASET_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "skill_foundry_maturity_eval.json"
)


def _load_dataset() -> dict[str, Any]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _trajectories(
    dataset: dict[str, Any], scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for sample in scenario["samples"]:
        variant = dataset["variants"][sample["variant"]]
        for _ in range(int(sample["count"])):
            trajectory = deepcopy(variant)
            trajectory["taskId"] = (
                f"{scenario['id']}-task-{len(result) + 1}"
            )
            trajectory["metadata"] = {
                "taskType": trajectory.pop("taskType")
            }
            result.append(trajectory)
    return result


def _manifest(
    scenario: dict[str, Any],
    trajectories: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = deepcopy(scenario["evidence"])
    evidence["tasks"] = [
        {
            "taskId": trajectory["taskId"],
            "checks": {"workflowTrace": True},
        }
        for trajectory in trajectories
    ]
    return evidence


def _safe_replay(
    workflow: dict[str, Any], trajectory: dict[str, Any]
) -> dict[str, Any]:
    passed = bool(trajectory.get("safeReplay"))
    return {
        "taskId": trajectory["taskId"],
        "passed": passed,
        "checks": {
            "workflowPresent": bool(workflow.get("steps")),
            "syntheticReplayAccepted": passed,
        },
    }


def test_privacy_safe_maturity_dataset_contract() -> None:
    dataset = _load_dataset()

    assert dataset["schemaVersion"] == "skill-foundry-maturity-eval-v1"
    serialized = json.dumps(dataset, ensure_ascii=False).casefold()
    for forbidden in (
        "e:\\",
        "c:\\users",
        "@example.com",
        "13800138000",
        "screenshot_path",
    ):
        assert forbidden not in serialized


def test_dynamic_maturity_against_versioned_scenarios() -> None:
    dataset = _load_dataset()
    assessor = SkillMaturityAssessor(replay_validator=_safe_replay)
    results: dict[str, dict[str, Any]] = {}

    for scenario in dataset["scenarios"]:
        trajectories = _trajectories(dataset, scenario)
        result = assessor.assess(
            trajectories,
            _manifest(scenario, trajectories),
            deepcopy(dataset["workflow"]),
            executable=bool(scenario["executable"]),
        )
        expected = scenario["expected"]
        blockers = {item["code"] for item in result["blockers"]}

        assert result["ready"] is expected["ready"], scenario["id"]
        assert result["stage"] == expected["stage"], scenario["id"]
        assert (
            expected["minimumReadiness"]
            <= result["readiness"]
            <= expected["maximumReadiness"]
        ), scenario["id"]
        assert set(expected["blockers"]).issubset(blockers), scenario["id"]
        assert result["readiness"] <= result["readinessCap"]
        results[scenario["id"]] = result

    for scenario in dataset["scenarios"]:
        reference = scenario["expected"].get("readinessBelowScenario")
        if reference:
            assert (
                results[scenario["id"]]["readiness"]
                < results[reference]["readiness"]
            )
