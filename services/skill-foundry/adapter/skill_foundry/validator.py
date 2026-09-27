from __future__ import annotations

import json
import re
from typing import Any

from adapter.skill_foundry.models import ValidationResult


class SkillValidator:
    REQUIRED_WORKFLOW_FIELDS = {
        "name",
        "version",
        "triggers",
        "parameters",
        "preconditions",
        "steps",
        "verification",
        "knownFailures",
        "requiredTools",
        "riskLevel",
    }
    DANGEROUS_ACTIONS = {
        "delete_file",
        "send_message",
        "modify_external_data",
        "payment",
        "purchase",
    }

    def validate(
        self,
        compiled: dict[str, Any],
        source_tasks: list[dict[str, Any]],
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        workflow = compiled.get("workflow") or {}
        evidence_manifest = compiled.get("evidenceManifest") or {}
        maturity = workflow.get("maturity") or {}
        missing = self.REQUIRED_WORKFLOW_FIELDS.difference(workflow)
        if missing:
            errors.append(f"workflow missing fields: {', '.join(sorted(missing))}")
        checks = {
            "source_count": len(source_tasks) >= 2,
            "source_ids_unique": len(
                {item.get("taskId") for item in source_tasks}
            )
            == len(source_tasks),
            "procedure_present": bool(workflow.get("steps")),
            "verification_present": bool(workflow.get("verification")),
            "source_traceable": all(
                item.get("taskId") for item in source_tasks
            ),
            "agent_skill_sections": all(
                heading in str(compiled.get("skillMarkdown") or "")
                for heading in (
                    "## When to Use",
                    "## Inputs",
                    "## Preconditions",
                    "## Procedure",
                    "## Pitfalls",
                    "## Verification",
                    "## Do Not Use",
                    "## Personalization",
                    "## Safety and Approval",
                )
            ),
            "evidence_manifest_present": bool(
                evidence_manifest.get("tasks")
            ),
            "evidence_completeness_declared": (
                isinstance(evidence_manifest.get("complete"), bool)
                and bool(
                    (evidence_manifest.get("completeness") or {}).get(
                        "requiredChecks"
                    )
                )
            ),
            "personalization_explicit": "personalization" in workflow,
            "maturity_declared": (
                isinstance(maturity.get("ready"), bool)
                and isinstance(maturity.get("readiness"), int)
                and bool(maturity.get("dimensions"))
            ),
        }
        for name, passed in checks.items():
            if not passed:
                errors.append(f"validation failed: {name}")
        for step in workflow.get("steps") or []:
            action = str(step.get("action") or "")
            if action in self.DANGEROUS_ACTIONS and not step.get(
                "requiresConfirmation"
            ):
                errors.append(
                    f"dangerous step {step.get('id')} lacks confirmation"
                )
            if not str(step.get("id") or "").strip():
                errors.append("workflow step is missing an id")
            if not str(step.get("tool") or "").strip():
                warnings.append(
                    f"workflow step {step.get('id')} has no explicit tool"
                )
        serialized = json.dumps(workflow, ensure_ascii=False)
        if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", serialized):
            errors.append("workflow contains a source-specific contact")
        if re.search(r"[A-Za-z]:[\\/][^\"']+", serialized):
            errors.append("workflow contains a source-specific absolute path")
        conflicts = compiled.get("distilled", {}).get("conflicts") or []
        if conflicts:
            warnings.append("source trajectories contain conflicts requiring review")
        inferred = [
            item
            for item in source_tasks
            if item.get("sourceQuality") == "inferred"
        ]
        if inferred:
            warnings.append(
                f"{len(inferred)} source trajectories were inferred from sparse evidence"
            )
        coverage = int(
            evidence_manifest.get("coverage") or 0
        )
        if coverage < 60:
            warnings.append(
                f"evidence coverage is only {coverage}%; add OCR, files, or captured trajectories"
            )
        if not evidence_manifest.get("complete"):
            missing = ", ".join(
                str(value)
                for value in evidence_manifest.get("missingEvidence") or []
            )
            warnings.append(
                "evidence is explicitly incomplete"
                + (f": {missing}" if missing else "")
            )
        if not maturity.get("ready"):
            blockers = ", ".join(
                str(item.get("code") or "")
                for item in maturity.get("blockers") or []
                if isinstance(item, dict)
            )
            warnings.append(
                "skill maturity is not ready"
                + (f": {blockers}" if blockers else "")
            )
        preferences = (
            (compiled.get("distilled") or {}).get("userPreferences") or []
        )
        unsupported_preferences = [
            item
            for item in preferences
            if isinstance(item, dict)
            and item.get("confidence") is not None
            and not item.get("evidenceRefs")
            and item.get("source") != "repeated_trajectory"
        ]
        if unsupported_preferences:
            warnings.append(
                f"{len(unsupported_preferences)} personalized preferences lack evidence references"
            )
        structural_score = max(
            0.0, 1.0 - len(errors) * 0.2 - len(warnings) * 0.03
        )
        maturity_score = int(maturity.get("readiness") or 0)
        score = (
            structural_score * 0.45
            + (coverage / 100) * 0.25
            + (maturity_score / 100) * 0.30
        )
        return ValidationResult(
            valid=not errors,
            score=round(score, 2),
            errors=errors,
            warnings=warnings,
            checks=checks,
        )
