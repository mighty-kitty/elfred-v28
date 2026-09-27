from __future__ import annotations

import math
from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Callable

from adapter.skill_foundry.distiller import semantic_terms


class SkillMaturityAssessor:
    """Explain whether repeated work is sufficiently understood to approve."""

    VERSION = "skill-maturity-v3"
    MINIMUM_EXAMPLES = 2
    CLUSTER_THRESHOLD = 80
    PATTERN_THRESHOLD = 80
    STAGE_READINESS_CAPS = {
        "observing": 49,
        "evidence_gap": 69,
        "pattern_forming": 84,
        "validating_reproduction": 94,
        "review_ready": 100,
    }

    def __init__(
        self,
        replay_validator: Callable[
            [dict[str, Any], dict[str, Any]], dict[str, Any]
        ]
        | None = None,
    ) -> None:
        self.replay_validator = replay_validator

    def assess(
        self,
        trajectories: list[dict[str, Any]],
        evidence_manifest: dict[str, Any],
        workflow: dict[str, Any],
        *,
        executable: bool,
    ) -> dict[str, Any]:
        sample_count = len(trajectories)
        evidence_score = int(evidence_manifest.get("coverage") or 0)
        evidence_passed = bool(evidence_manifest.get("complete"))

        task_type_agreement = self._task_type_agreement(trajectories)
        sequence_agreement = self._sequence_agreement(trajectories)
        goal_agreement = self._goal_agreement(trajectories)
        cluster_score = round(
            task_type_agreement * 35
            + sequence_agreement * 45
            + goal_agreement * 20
        )
        cluster_passed = cluster_score >= self.CLUSTER_THRESHOLD

        core_step_support = self._core_step_support(trajectories)
        input_schema_agreement = self._key_agreement(
            [set((item.get("inputs") or {}).keys()) for item in trajectories]
        )
        success_signal_agreement = self._success_signal_agreement(trajectories)
        pattern_score = round(
            sequence_agreement * 50
            + core_step_support * 20
            + input_schema_agreement * 15
            + success_signal_agreement * 15
        )
        pattern_passed = pattern_score >= self.PATTERN_THRESHOLD

        evidence_by_task = {
            str(item.get("taskId")): item
            for item in evidence_manifest.get("tasks") or []
        }
        historical_results = [
            self._historical_replay(
                item,
                workflow,
                evidence_by_task.get(str(item.get("taskId"))) or {},
            )
            for item in trajectories
        ]
        historical_passes = sum(
            1 for item in historical_results if item["passed"]
        )
        safe_replay_results = [
            self._safe_replay(workflow, item) for item in trajectories
        ]
        held_out_passes = sum(
            1 for item in safe_replay_results if item["passed"]
        )
        replay_target = min(self.MINIMUM_EXAMPLES, sample_count)
        historical_ratio = (
            historical_passes / replay_target if replay_target else 0.0
        )
        held_out_ratio = (
            held_out_passes / replay_target if replay_target else 0.0
        )
        reproduction_score = (
            round(
                min(1.0, historical_ratio) * 35
                + min(1.0, held_out_ratio) * 35
                + (30 if executable else 0)
            )
            if sample_count
            else 0
        )
        reproduction_passed = (
            sample_count >= self.MINIMUM_EXAMPLES
            and historical_passes >= self.MINIMUM_EXAMPLES
            and held_out_passes >= self.MINIMUM_EXAMPLES
            and executable
        )

        blockers: list[dict[str, Any]] = []
        next_evidence: list[str] = []
        if sample_count < self.MINIMUM_EXAMPLES:
            blockers.append(
                {
                    "code": "need_independent_examples",
                    "message": "至少需要两次独立完成记录，才能判断哪些步骤可复用。",
                }
            )
            next_evidence.append("继续观察一次独立的同类任务")
        if not evidence_passed:
            missing = evidence_manifest.get("missingEvidence") or []
            blockers.append(
                {
                    "code": "evidence_incomplete",
                    "message": "部分历史任务缺少复刻所需的必需证据。",
                    "details": list(missing),
                }
            )
            next_evidence.append("补足缺失的输入、输出、操作轨迹或成功判定")
        if not cluster_passed:
            blockers.append(
                {
                    "code": "cluster_uncertain",
                    "message": "这些任务是否属于同一种可复用工作仍不够确定。",
                    "details": {
                        "taskTypeAgreement": round(task_type_agreement * 100),
                        "workflowAgreement": round(sequence_agreement * 100),
                        "goalAgreement": round(goal_agreement * 100),
                    },
                }
            )
            next_evidence.append("继续观察目标和操作流程更接近的任务")
        if not pattern_passed:
            blockers.append(
                {
                    "code": "workflow_not_converged",
                    "message": "固定步骤、变量或成功条件仍在变化，工作流尚未收敛。",
                    "details": {
                        "sequenceAgreement": round(sequence_agreement * 100),
                        "coreStepSupport": round(core_step_support * 100),
                        "inputSchemaAgreement": round(
                            input_schema_agreement * 100
                        ),
                        "successSignalAgreement": round(
                            success_signal_agreement * 100
                        ),
                    },
                }
            )
            next_evidence.append("继续观察能覆盖当前差异或条件分支的任务")
        if historical_passes < self.MINIMUM_EXAMPLES:
            blockers.append(
                {
                    "code": "historical_replay_insufficient",
                    "message": "当前流程还不能解释至少两次完整的历史输入、步骤、输出和成功判定。",
                    "details": {
                        "passes": historical_passes,
                        "required": self.MINIMUM_EXAMPLES,
                    },
                }
            )
            next_evidence.append("记录一次包含输入、完整轨迹、输出和验收结果的任务")
        if held_out_passes < self.MINIMUM_EXAMPLES:
            blockers.append(
                {
                    "code": "held_out_replay_insufficient",
                    "message": (
                        "生成的流程还不能在安全模拟中复刻至少两次"
                        "历史任务的输入、输出形态和完成条件。"
                    ),
                    "details": {
                        "passes": held_out_passes,
                        "required": self.MINIMUM_EXAMPLES,
                        "mode": "safe_simulation",
                    },
                }
            )
            next_evidence.append(
                "继续观察可由当前执行适配器安全复演的同类任务"
            )
        if not executable:
            blockers.append(
                {
                    "code": "execution_adapter_missing",
                    "message": "Elfred 还没有能够安全执行这条工作流的适配器。",
                }
            )
            next_evidence.append("为该工作流补充并验证执行适配器")

        ready = (
            sample_count >= self.MINIMUM_EXAMPLES
            and evidence_passed
            and cluster_passed
            and pattern_passed
            and reproduction_passed
        )
        weighted = round(
            evidence_score * 0.25
            + cluster_score * 0.25
            + pattern_score * 0.30
            + reproduction_score * 0.20
        )
        stage = self._stage(
            sample_count=sample_count,
            evidence_passed=evidence_passed,
            cluster_passed=cluster_passed,
            pattern_passed=pattern_passed,
            reproduction_passed=reproduction_passed,
        )
        readiness_cap = self.STAGE_READINESS_CAPS[stage]
        readiness = 100 if ready else min(readiness_cap, weighted)
        estimated_additional = self._estimated_additional_examples(
            sample_count=sample_count,
            evidence_passed=evidence_passed,
            cluster_score=cluster_score,
            pattern_score=pattern_score,
            replay_passes=min(historical_passes, held_out_passes),
            executable=executable,
        )
        return {
            "schemaVersion": self.VERSION,
            "ready": ready,
            "readiness": readiness,
            "readinessCap": readiness_cap,
            "stage": stage,
            "sampleCount": sample_count,
            "minimumExamples": self.MINIMUM_EXAMPLES,
            "dynamicSampleSufficient": ready,
            "estimatedAdditionalExamples": estimated_additional,
            "dimensions": {
                "evidence": {
                    "score": evidence_score,
                    "passed": evidence_passed,
                    "basis": "task-type-specific reproducibility evidence",
                },
                "cluster": {
                    "score": cluster_score,
                    "passed": cluster_passed,
                    "taskTypeAgreement": round(task_type_agreement * 100),
                    "workflowAgreement": round(sequence_agreement * 100),
                    "goalAgreement": round(goal_agreement * 100),
                },
                "pattern": {
                    "score": pattern_score,
                    "passed": pattern_passed,
                    "sequenceAgreement": round(sequence_agreement * 100),
                    "coreStepSupport": round(core_step_support * 100),
                    "inputSchemaAgreement": round(
                        input_schema_agreement * 100
                    ),
                    "successSignalAgreement": round(
                        success_signal_agreement * 100
                    ),
                },
                "reproduction": {
                    "score": reproduction_score,
                    "passed": reproduction_passed,
                    "historicalReplayPasses": historical_passes,
                    "safeReplayPasses": held_out_passes,
                    "heldOutReplayPasses": held_out_passes,
                    "requiredPasses": self.MINIMUM_EXAMPLES,
                    "executionAdapterAvailable": executable,
                    "mode": "safe_simulation",
                    "mutatesHistoricalTasks": False,
                    "cases": [
                        {
                            **historical,
                            "safeSimulation": safe,
                        }
                        for historical, safe in zip(
                            historical_results,
                            safe_replay_results,
                        )
                    ],
                },
            },
            "blockers": blockers,
            "nextEvidence": list(dict.fromkeys(next_evidence)),
            "assessmentBasis": [
                "任务数量只触发观察，不直接代表 Skill 已学会",
                "证据要求会根据任务类型和可替代证据来源变化",
                "流程必须在目标、步骤、变量和成功判定上趋于稳定",
                "至少两次历史记录必须能够被生成的工作流解释",
                "至少两次留出记录必须通过不修改历史任务的安全模拟",
                "100% 仅在全部门槛通过时出现",
            ],
        }

    def _safe_replay(
        self,
        workflow: dict[str, Any],
        trajectory: dict[str, Any],
    ) -> dict[str, Any]:
        if self.replay_validator is None:
            return {
                "taskId": trajectory.get("taskId"),
                "mode": "safe_simulation",
                "passed": False,
                "mutatedHistoricalTask": False,
                "checks": {"validatorAvailable": False},
                "error": "safe_replay_validator_missing",
            }
        try:
            result = self.replay_validator(workflow, trajectory)
        except Exception as error:
            return {
                "taskId": trajectory.get("taskId"),
                "mode": "safe_simulation",
                "passed": False,
                "mutatedHistoricalTask": False,
                "checks": {"validatorAvailable": True},
                "error": str(error)[:240],
            }
        sanitized = dict(result)
        sanitized["mode"] = "safe_simulation"
        sanitized["mutatedHistoricalTask"] = False
        return sanitized

    @staticmethod
    def _stage(
        *,
        sample_count: int,
        evidence_passed: bool,
        cluster_passed: bool,
        pattern_passed: bool,
        reproduction_passed: bool,
    ) -> str:
        if sample_count < SkillMaturityAssessor.MINIMUM_EXAMPLES:
            return "observing"
        if not evidence_passed:
            return "evidence_gap"
        if not cluster_passed or not pattern_passed:
            return "pattern_forming"
        if not reproduction_passed:
            return "validating_reproduction"
        return "review_ready"

    @staticmethod
    def _estimated_additional_examples(
        *,
        sample_count: int,
        evidence_passed: bool,
        cluster_score: int,
        pattern_score: int,
        replay_passes: int,
        executable: bool,
    ) -> int | None:
        if not executable or not evidence_passed:
            return None
        deficits = [
            max(0, SkillMaturityAssessor.MINIMUM_EXAMPLES - sample_count),
            math.ceil(
                max(0, SkillMaturityAssessor.CLUSTER_THRESHOLD - cluster_score)
                / 10
            ),
            math.ceil(
                max(0, SkillMaturityAssessor.PATTERN_THRESHOLD - pattern_score)
                / 10
            ),
            max(0, SkillMaturityAssessor.MINIMUM_EXAMPLES - replay_passes),
        ]
        return min(6, max(deficits))

    @staticmethod
    def _task_type_agreement(trajectories: list[dict[str, Any]]) -> float:
        values = [
            str((item.get("metadata") or {}).get("taskType") or "unknown")
            for item in trajectories
        ]
        if not values:
            return 0.0
        return max(values.count(value) for value in set(values)) / len(values)

    @classmethod
    def _sequence_agreement(
        cls, trajectories: list[dict[str, Any]]
    ) -> float:
        sequences = [cls._sequence(item) for item in trajectories]
        return cls._pairwise_agreement(
            sequences,
            lambda left, right: SequenceMatcher(
                None, left, right, autojunk=False
            ).ratio(),
        )

    @staticmethod
    def _goal_agreement(trajectories: list[dict[str, Any]]) -> float:
        goals = [
            semantic_terms(
                f"{item.get('intent') or ''} {item.get('summary') or ''}"
            )
            for item in trajectories
        ]
        return SkillMaturityAssessor._pairwise_agreement(
            goals, SkillMaturityAssessor._jaccard
        )

    @classmethod
    def _core_step_support(
        cls, trajectories: list[dict[str, Any]]
    ) -> float:
        step_sets = [set(cls._sequence(item)) for item in trajectories]
        return cls._key_agreement(step_sets)

    @staticmethod
    def _success_signal_agreement(
        trajectories: list[dict[str, Any]],
    ) -> float:
        values = [
            semantic_terms(" ".join(item.get("successSignals") or []))
            for item in trajectories
        ]
        lexical = SkillMaturityAssessor._pairwise_agreement(
            values, SkillMaturityAssessor._jaccard
        )
        present = (
            sum(bool(item.get("successSignals")) for item in trajectories)
            / len(trajectories)
            if trajectories
            else 0.0
        )
        return present * 0.5 + lexical * 0.5

    @classmethod
    def _historical_replay(
        cls,
        trajectory: dict[str, Any],
        workflow: dict[str, Any],
        task_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        historical = cls._sequence(trajectory)
        generated = [
            (
                str(step.get("sourceAction") or step.get("action") or ""),
                str(step.get("tool") or ""),
            )
            for step in workflow.get("steps") or []
        ]
        alignment = (
            SequenceMatcher(
                None, historical, generated, autojunk=False
            ).ratio()
            if historical and generated
            else 0.0
        )
        source_quality = str(trajectory.get("sourceQuality") or "")
        evidence_checks = task_evidence.get("checks") or {}
        checks = {
            "reproducibleTrace": (
                source_quality.startswith("captured")
                or bool(evidence_checks.get("workflowTrace"))
            ),
            "inputs": bool(trajectory.get("inputs")),
            "outputs": cls._has_output(trajectory.get("outputs") or []),
            "successSignals": bool(trajectory.get("successSignals")),
            "workflowAlignment": alignment >= 0.8,
        }
        return {
            "taskId": trajectory.get("taskId"),
            "passed": all(checks.values()),
            "workflowAlignment": round(alignment * 100),
            "checks": checks,
        }

    @staticmethod
    def _has_output(outputs: list[Any]) -> bool:
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
    def _sequence(item: dict[str, Any]) -> list[tuple[str, str]]:
        return [
            (
                str(step.get("actionType") or step.get("action") or ""),
                str(step.get("tool") or ""),
            )
            for step in item.get("steps") or []
            if str(step.get("result") or "success").casefold()
            in {"success", "completed", "ok"}
        ]

    @staticmethod
    def _key_agreement(values: list[set[Any]]) -> float:
        if not values:
            return 0.0
        union = set().union(*values)
        if not union:
            return 0.0
        intersection = set(values[0])
        for value in values[1:]:
            intersection.intersection_update(value)
        return len(intersection) / len(union)

    @staticmethod
    def _jaccard(left: set[Any], right: set[Any]) -> float:
        union = left | right
        if not union:
            return 0.0
        return len(left & right) / len(union)

    @staticmethod
    def _pairwise_agreement(
        values: list[Any], scorer: Any
    ) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return 1.0
        scores = [
            float(scorer(left, right))
            for left, right in combinations(values, 2)
        ]
        return sum(scores) / len(scores) if scores else 0.0
