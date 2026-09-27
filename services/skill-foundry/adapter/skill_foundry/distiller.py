from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePath
from typing import Any

from adapter.skill_foundry.models import TaskTrajectory


STOP_TERMS = {
    "任务",
    "完成",
    "已经",
    "进行",
    "相关",
    "使用",
    "the",
    "and",
    "with",
}
CHINESE_SEMANTIC_VOCAB = {
    "摘要",
    "总结",
    "要点",
    "文档",
    "网页",
    "阅读",
    "提取",
    "生成",
    "写回",
    "代码",
    "开发",
    "测试",
    "修复",
    "重构",
    "接口",
    "调研",
    "研究",
    "文献",
    "竞品",
    "数据",
    "分析",
    "统计",
    "图表",
    "计划",
    "规划",
    "排期",
    "邮件",
    "消息",
    "回复",
    "汇报",
}


def semantic_terms(value: Any) -> set[str]:
    text = str(value or "").casefold()
    latin = re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", text)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    chinese: list[str] = []
    for chunk in chinese_chunks:
        chinese.extend(
            term for term in CHINESE_SEMANTIC_VOCAB if term in chunk
        )
        if 2 <= len(chunk) <= 6:
            chinese.append(chunk)
    return {
        term
        for term in [*latin, *chinese]
        if term not in STOP_TERMS and len(term) > 1
    }


class SkillDistiller:
    """Merge successful trajectories while separating constants from variables."""

    VERSION = "skill-distiller-v2"

    def distill(
        self,
        trajectories: list[TaskTrajectory],
        memory_preferences: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if len(trajectories) < 2:
            raise ValueError("skill-distiller requires repeated trajectories")
        task_types = {
            str(item.metadata.get("taskType") or "unknown") for item in trajectories
        }
        conflicts: list[dict[str, Any]] = []
        if len(task_types) > 1:
            conflicts.append(
                {
                    "field": "taskType",
                    "values": sorted(task_types),
                    "resolution": "manual_review",
                }
            )

        fixed_steps, optional_steps = self._merge_steps(trajectories)
        parameters, preferences = self._classify_inputs(trajectories)
        environment = sorted(
            {
                app
                for trajectory in trajectories
                for app in trajectory.context_apps
                if app
            }
        )
        required_tools = list(
            dict.fromkeys(
                step["tool"]
                for step in [*fixed_steps, *optional_steps]
                if step["tool"] not in {"", "unknown"}
            )
        )
        failures = self._failures(trajectories)
        verification = self._verification(trajectories)
        triggers = self._triggers(trajectories)
        accidental = self._accidental_information(trajectories, parameters)
        name = (
            "文档要点摘要"
            if task_types == {"document_summary"}
            else self._common_name(trajectories)
        )
        description = (
            "读取一段网页或文档文本，提取中文关键要点，将摘要写回任务卡并验证完成状态。"
            if task_types == {"document_summary"}
            else f"复用 {name} 的已验证 Elfred 工作流。"
        )
        task_type = next(iter(task_types)) if len(task_types) == 1 else "mixed"
        usage = self._usage_for(task_type)
        if memory_preferences:
            preferences.extend(memory_preferences)
        return {
            "name": name,
            "description": description,
            "taskType": task_type,
            "commonGoal": self._common_goal(trajectories),
            "whenToUse": usage["when"],
            "doNotUse": usage["avoid"],
            "fixedWorkflow": fixed_steps,
            "parameters": parameters,
            "optionalSteps": optional_steps,
            "conditionalBranches": [
                {
                    "when": step.get("condition"),
                    "stepId": step["id"],
                }
                for step in optional_steps
                if step.get("condition")
            ],
            "requiredTools": required_tools,
            "toolParameterTemplates": {
                step["id"]: step.get("arguments") or {}
                for step in [*fixed_steps, *optional_steps]
            },
            "userPreferences": self._dedupe_dicts(preferences),
            "environmentDependencies": environment,
            "knownFailures": failures,
            "verification": verification,
            "accidentalInformationExcluded": accidental,
            "conflicts": conflicts,
            "triggers": triggers,
            "sourceTaskIds": [item.task_id for item in trajectories],
            "sourceTodoIds": [item.freetodo_todo_id for item in trajectories],
            "distillerVersion": self.VERSION,
        }

    @staticmethod
    def _usage_for(task_type: str) -> dict[str, list[str]]:
        when = {
            "document_summary": [
                "用户提供网页、文档正文或可读取附件，并希望提炼结构化关键要点。",
                "需要把结果写回原任务卡并验证完成状态。",
            ],
            "software_development": [
                "任务与已观察到的同类代码修改、测试和验证流程一致。",
                "工作区、目标文件和验证命令均可明确定位。",
            ],
            "research": [
                "用户需要按已验证的来源收集和综合流程完成同类调研。",
                "输出需要保留来源和可核验结论。",
            ],
            "data_analysis": [
                "输入数据结构和预期指标与来源任务相同。",
                "需要生成可复查的分析结果或图表。",
            ],
            "task_planning": [
                "目标需要按用户反复采用的拆解和排期方式形成计划。",
            ],
            "communication": [
                "用户需要按既有语气和结构起草同类沟通内容。",
            ],
        }.get(
            task_type,
            ["当前任务与来源任务具有相同目标、输入和成功判定。"],
        )
        return {
            "when": when,
            "avoid": [
                "关键输入、目标或成功判定与来源任务明显不同。",
                "任务包含未获确认的发送、删除、支付或外部数据修改。",
            ],
        }

    @staticmethod
    def _merge_steps(
        trajectories: list[TaskTrajectory],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        occurrence: Counter[tuple[str, str]] = Counter()
        first: dict[tuple[str, str], Any] = {}
        order: list[tuple[str, str]] = []
        for trajectory in trajectories:
            seen: set[tuple[str, str]] = set()
            for step in trajectory.steps:
                signature = (step.action_type, step.tool)
                if signature not in first:
                    first[signature] = step
                    order.append(signature)
                if signature not in seen and step.result == "success":
                    occurrence[signature] += 1
                    seen.add(signature)
        fixed: list[dict[str, Any]] = []
        optional: list[dict[str, Any]] = []
        for sequence, signature in enumerate(order, 1):
            step = first[signature]
            item = {
                "id": f"step_{sequence}_{step.action_type}",
                "sequence": sequence,
                "actionType": step.action_type,
                "tool": step.tool,
                "target": step.target,
                "arguments": step.arguments,
                "condition": step.condition,
                "rationale": (
                    f"该动作在 {occurrence[signature]}/{len(trajectories)} "
                    "条成功轨迹中出现。"
                ),
                "evidenceSupport": [
                    trajectory.task_id
                    for trajectory in trajectories
                    if any(
                        candidate.action_type == step.action_type
                        and candidate.tool == step.tool
                        and candidate.result == "success"
                        for candidate in trajectory.steps
                    )
                ],
            }
            if occurrence[signature] == len(trajectories) and not step.optional:
                fixed.append(item)
            else:
                item["optional"] = True
                optional.append(item)
        return fixed, optional

    @staticmethod
    def _classify_inputs(
        trajectories: list[TaskTrajectory],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        keys = sorted({key for item in trajectories for key in item.inputs})
        parameters: dict[str, dict[str, Any]] = {}
        preferences: list[dict[str, Any]] = []
        preference_keys = {
            "outputlanguage",
            "outputstyle",
            "bulletcount",
            "tone",
            "format",
        }
        for key in keys:
            values = [item.inputs.get(key) for item in trajectories]
            present = [value for value in values if value not in (None, "")]
            normalized = {str(value) for value in present}
            lowered = key.replace("_", "").casefold()
            if lowered in preference_keys and len(normalized) == 1:
                preferences.append(
                    {
                        "name": key,
                        "value": present[0],
                        "source": "repeated_trajectory",
                        "confidence": 1.0,
                        "scope": str(
                            trajectories[0].metadata.get("taskType")
                            or "task_type"
                        ),
                        "evidenceRefs": [
                            item.task_id for item in trajectories
                        ],
                        "overridable": True,
                    }
                )
                continue
            sample = present[0] if present else ""
            safe_examples = [str(value)[:160] for value in present[:3]]
            if lowered in {"sourcetext", "content", "body", "rawtext"}:
                safe_examples = ["<document text>"]
            elif lowered in {"documenttitle", "filename", "filepath", "path"}:
                safe_examples = [f"<{key}>"]
            parameters[key] = {
                "type": SkillDistiller._json_type(sample),
                "required": len(present) == len(trajectories),
                "description": f"每次运行可替换的 {key}",
                "examples": safe_examples,
            }
        if "sourceText" not in parameters:
            parameters["sourceText"] = {
                "type": "string",
                "required": True,
                "description": "需要提炼的网页或文档正文",
                "examples": [],
            }
        return parameters, preferences

    @staticmethod
    def _json_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "string"

    @staticmethod
    def _failures(trajectories: list[TaskTrajectory]) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        for trajectory in trajectories:
            for step in trajectory.steps:
                if step.result not in {"success", "completed", "ok"}:
                    failures.append(
                        {
                            "step": step.action_type,
                            "reason": step.result,
                            "mitigation": "保留原任务并要求用户修正输入后重试",
                        }
                    )
            for correction in trajectory.corrections:
                failures.append(
                    {
                        "step": correction.get("step") or "unknown",
                        "reason": correction.get("reason")
                        or correction.get("before")
                        or "user_correction",
                        "mitigation": correction.get("after")
                        or correction.get("correction")
                        or "follow_user_correction",
                    }
                )
        if not failures:
            failures.append(
                {
                    "step": "extract_key_points",
                    "reason": "source_text_too_short",
                    "mitigation": "停止运行并请求更完整的文本，不自动完成任务",
                }
            )
        return SkillDistiller._dedupe_dicts(failures)

    @staticmethod
    def _verification(trajectories: list[TaskTrajectory]) -> list[dict[str, Any]]:
        signals = [
            signal
            for trajectory in trajectories
            for signal in trajectory.success_signals
        ]
        unique = list(dict.fromkeys(signals))
        return [
            {"type": "assertion", "description": signal}
            for signal in unique[:8]
        ]

    @staticmethod
    def _triggers(trajectories: list[TaskTrajectory]) -> list[str]:
        counts: Counter[str] = Counter()
        for trajectory in trajectories:
            counts.update(
                semantic_terms(
                    f"{trajectory.intent} {trajectory.summary} "
                    f"{trajectory.metadata.get('category') or ''}"
                )
            )
        common = [
            term for term, count in counts.most_common(20) if count >= 2
        ]
        defaults = ["文档", "网页", "摘要", "要点", "总结"]
        return list(dict.fromkeys([*defaults, *common]))[:20]

    @staticmethod
    def _accidental_information(
        trajectories: list[TaskTrajectory],
        parameters: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        excluded: list[dict[str, Any]] = []
        parameter_examples = {
            example
            for spec in parameters.values()
            for example in spec.get("examples") or []
        }
        for trajectory in trajectories:
            for value in trajectory.inputs.values():
                text = str(value)
                if text in parameter_examples:
                    continue
                if re.search(r"[A-Za-z]:[\\/]|[/\\][\w.-]+\.\w{1,8}", text):
                    excluded.append({"type": "specific_path", "value": text[:160]})
                if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text):
                    excluded.append({"type": "specific_contact", "value": "[redacted]"})
                if PurePath(text).suffix:
                    excluded.append(
                        {"type": "specific_filename", "value": PurePath(text).name}
                    )
        return SkillDistiller._dedupe_dicts(excluded)

    @staticmethod
    def _common_goal(trajectories: list[TaskTrajectory]) -> str:
        if {
            str(item.metadata.get("taskType") or "") for item in trajectories
        } == {"document_summary"}:
            return "读取用户提供的文档文本，提取关键事实并将中文摘要保存到任务卡。"
        return "；".join(item.intent for item in trajectories)[:400]

    @staticmethod
    def _common_name(trajectories: list[TaskTrajectory]) -> str:
        first = trajectories[0].intent.strip()
        return first[:40] or "Elfred 可复用技能"

    @staticmethod
    def _dedupe_dicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            key = repr(sorted(value.items()))
            if key not in seen:
                result.append(value)
                seen.add(key)
        return result
