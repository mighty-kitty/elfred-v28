from __future__ import annotations

from typing import Any

from adapter.skill_foundry.distiller import semantic_terms


class SkillMatcher:
    """Rule-filter reviewed skills, then rank by deterministic semantic overlap."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def match(
        self, task_context: dict[str, Any], *, limit: int = 3
    ) -> list[dict[str, Any]]:
        query_text = " ".join(
            str(task_context.get(key) or "")
            for key in ("title", "description", "currentApp", "context")
        )
        query_text += " " + " ".join(
            str(value) for value in task_context.get("inputFileTypes") or []
        )
        query_terms = semantic_terms(query_text)
        task_type = str(task_context.get("taskType") or "").casefold()
        matches: list[dict[str, Any]] = []
        for skill in self.registry.list({"approved", "active"}):
            version = (
                skill.get("published_version")
                or skill.get("current_version")
                or {}
            )
            workflow = version.get("workflow") or {}
            distilled = version.get("distilled") or {}
            skill_terms = semantic_terms(
                " ".join(
                    [
                        str(skill.get("name") or ""),
                        str(skill.get("description") or ""),
                        " ".join(skill.get("trigger_terms") or []),
                        " ".join(workflow.get("triggers") or []),
                        " ".join((workflow.get("parameters") or {}).keys()),
                    ]
                )
            )
            rule_score = self._rule_score(
                task_context, workflow, distilled, task_type
            )
            semantic_score = self._jaccard(query_terms, skill_terms)
            score = min(1.0, rule_score * 0.55 + semantic_score * 0.45)
            if score < 0.2:
                continue
            reasons = self._reasons(
                task_context,
                workflow,
                distilled,
                query_terms.intersection(skill_terms),
            )
            matches.append(
                {
                    "skillId": skill["skill_id"],
                    "name": skill["name"],
                    "description": skill["description"],
                    "version": version.get("version"),
                    "versionId": version.get("version_id"),
                    "status": skill["status"],
                    "autoExecuteEnabled": bool(
                        skill.get("auto_execute_enabled")
                    ),
                    "score": round(score, 3),
                    "whyMatched": reasons,
                    "sourceTaskCount": len(
                        skill.get("published_source_tasks")
                        or skill.get("source_tasks")
                        or []
                    ),
                    "requiredParameters": [
                        name
                        for name, spec in (
                            workflow.get("parameters") or {}
                        ).items()
                        if spec.get("required")
                    ],
                }
            )
        return sorted(
            matches, key=lambda item: (-item["score"], item["name"])
        )[: max(1, min(10, int(limit)))]

    @staticmethod
    def _rule_score(
        context: dict[str, Any],
        workflow: dict[str, Any],
        distilled: dict[str, Any],
        task_type: str,
    ) -> float:
        score = 0.0
        if task_type and task_type == str(
            distilled.get("taskType") or ""
        ).casefold():
            score += 0.55
        if context.get("sourceText") or context.get("hasSourceText"):
            if "sourceText" in (workflow.get("parameters") or {}):
                score += 0.25
        file_types = {
            str(value).casefold()
            for value in context.get("inputFileTypes") or []
        }
        if file_types.intersection({".txt", ".md", ".pdf", ".docx", "text"}):
            score += 0.15
        if context.get("currentApp"):
            score += 0.05
        return min(1.0, score)

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left.intersection(right)) / len(left.union(right))

    @staticmethod
    def _reasons(
        context: dict[str, Any],
        workflow: dict[str, Any],
        distilled: dict[str, Any],
        overlap: set[str],
    ) -> list[str]:
        reasons: list[str] = []
        if context.get("taskType") == distilled.get("taskType"):
            reasons.append("任务类型与 Skill 的受控演示类型一致")
        if context.get("sourceText") or context.get("hasSourceText"):
            if "sourceText" in (workflow.get("parameters") or {}):
                reasons.append("当前任务提供了 Skill 所需的正文输入")
        if overlap:
            reasons.append(
                "标题与触发词重合：" + "、".join(sorted(overlap)[:5])
            )
        if not reasons:
            reasons.append("任务上下文与 Skill 示例具有语义相似性")
        return reasons
