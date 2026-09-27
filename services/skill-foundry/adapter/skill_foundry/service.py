from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from adapter.skill_foundry.compiler import SkillCompiler
from adapter.skill_foundry.classification import (
    TaskClassificationProvider,
    TaskSemanticProfiler,
    build_task_classification_provider,
)
from adapter.skill_foundry.distiller import SkillDistiller
from adapter.skill_foundry.evidence import (
    TaskEvidenceAssembler,
    TaskTrajectoryNormalizer,
)
from adapter.skill_foundry.evidence_pack import (
    build_evidence_manifest,
    prompt_evidence_pack,
)
from adapter.skill_foundry.generation import (
    DeterministicSkillGenerationProvider,
    SkillGenerationError,
    SkillGenerationProvider,
    build_generation_provider,
)
from adapter.skill_foundry.matcher import SkillMatcher
from adapter.skill_foundry.maturity import SkillMaturityAssessor
from adapter.skill_foundry.memory import LocalMemoryAdapter, MemoryAdapter
from adapter.skill_foundry.registry import SkillRegistry
from adapter.skill_foundry.runner import ElfredTaskExecutionAdapter
from adapter.skill_foundry.validator import SkillValidator
from adapter.storage.store import now_iso


class SkillFoundryService:
    """Orchestrate the nine Skill Foundry components over Elfred's current data."""

    def __init__(
        self,
        settings: Any,
        store: Any,
        freetodo_client: Any,
        memory: MemoryAdapter | None = None,
        generation_provider: SkillGenerationProvider | None = None,
        classification_provider: TaskClassificationProvider | None = None,
        harness_client: Any | None = None,
    ) -> None:
        root = settings.skill_root or (Path(settings.db_path).parent / "skills")
        self.settings = settings
        self.store = store
        self.client = freetodo_client
        self.evidence_assembler = TaskEvidenceAssembler(
            store, freetodo_client, settings
        )
        self.trajectory_normalizer = TaskTrajectoryNormalizer()
        self.distiller = SkillDistiller()
        self.compiler = SkillCompiler()
        self.validator = SkillValidator()
        self.registry = SkillRegistry(store, root)
        self.matcher = SkillMatcher(self.registry)
        self.runner = ElfredTaskExecutionAdapter(freetodo_client)
        self.maturity_assessor = SkillMaturityAssessor(
            replay_validator=self.runner.validate_historical_case
        )
        self.feedback_recorder = self.registry
        self.memory = memory or LocalMemoryAdapter(store)
        self.generation_provider = (
            generation_provider or build_generation_provider(settings, harness_client)
        )
        self.semantic_profiler = TaskSemanticProfiler(
            store,
            classification_provider
            or build_task_classification_provider(settings, harness_client),
            max_chars=settings.skill_classification_max_chars,
        )

    def start_draft(
        self, freetodo_todo_ids: list[int]
    ) -> dict[str, Any]:
        return self.registry.create_build(freetodo_todo_ids)

    def create_draft(
        self,
        freetodo_todo_ids: list[int],
        *,
        skill_id: str | None = None,
        build_id: str | None = None,
    ) -> dict[str, Any]:
        build = (
            self.registry.build(build_id)
            if build_id
            else self.registry.create_build(freetodo_todo_ids)
        )
        if not build:
            raise KeyError(build_id or "")
        build_id = str(build["build_id"])
        try:
            self.registry.update_build(
                build_id,
                "extracting",
                progress=12,
                detail="正在读取任务标题、总结与完成状态",
            )

            def report_evidence_progress(
                completed: int, total: int, live_metrics: dict[str, int]
            ) -> None:
                progress = 12 + round(36 * completed / max(1, total))
                self.registry.update_build(
                    build_id,
                    "extracting",
                    progress=progress,
                    detail=(
                        f"已真实读取 {completed}/{total} 个任务的附件、"
                        "Observer、OCR、截图、日报与 Skill 运行记录"
                    ),
                    metrics={
                        "tasksRead": completed,
                        "tasksTotal": total,
                        **live_metrics,
                    },
                )

            evidence_sets = self.evidence_assembler.assemble(
                freetodo_todo_ids,
                progress_callback=report_evidence_progress,
            )
            trajectories = self.trajectory_normalizer.normalize_many(evidence_sets)
            trajectory_dicts = [item.to_dict() for item in trajectories]
            evidence_manifest = build_evidence_manifest(
                evidence_sets, trajectory_dicts
            )
            metrics = dict(evidence_manifest["totals"])
            metrics["evidenceCoverage"] = evidence_manifest["coverage"]
            metrics["evidenceComplete"] = evidence_manifest["complete"]
            metrics["missingEvidence"] = evidence_manifest["missingEvidence"]
            self.registry.update_build(
                build_id,
                "extracting",
                progress=58,
                detail="证据读取已结束，正在归一化成功轨迹与用户修正",
                metrics=metrics,
            )
            preferences = self.memory.get_user_preferences("document_summary")
            baseline = self.distiller.distill(
                trajectories,
                preferences,
            )
            user_profile = {
                "preferences": preferences,
                "relatedExperiences": self.memory.search_related_experiences(
                    str(baseline.get("commonGoal") or baseline.get("name") or "")
                ),
            }
            pack = prompt_evidence_pack(
                evidence_sets,
                trajectory_dicts,
                max_chars=self.settings.skill_max_evidence_chars,
            )
            model_files = [
                file
                for item in evidence_sets
                for file in item.get("_model_files") or []
            ]
            self.registry.update_build(
                build_id,
                "extracting",
                progress=72,
                detail="正在通过个性化生成器比较共同流程与用户偏好",
                metrics=metrics,
            )
            try:
                generated = self.generation_provider.generate(
                    baseline, pack, user_profile, model_files
                )
            except SkillGenerationError as error:
                generated = DeterministicSkillGenerationProvider(
                    str(error)[:500]
                ).generate(baseline, pack, user_profile, model_files)
            distilled = generated.distilled
            distilled["generation"] = generated.metadata()
            distilled["evidenceCoverage"] = evidence_manifest["coverage"]
            distilled["evidenceCompleteness"] = evidence_manifest[
                "completeness"
            ]
            version = self.registry.next_version(skill_id)
            model = f"{generated.provider}/{generated.model}"
            self.registry.update_build(
                build_id,
                "validating",
                progress=86,
                detail="正在编译 SKILL.md、workflow.json 与个性化约束",
                metrics={
                    **metrics,
                    "generationMode": generated.mode,
                    "modelImages": generated.image_count,
                },
            )
            compiled = self.compiler.compile(
                distilled,
                version=version,
                model=model,
                trajectories=trajectory_dicts,
                evidence_manifest=evidence_manifest,
                generation=generated.metadata(),
            )
            compiled["distilled"] = distilled
            executable = self.runner.can_execute(
                {"current_version": {"workflow": compiled["workflow"]}},
                {},
            )
            maturity = self.maturity_assessor.assess(
                trajectory_dicts,
                evidence_manifest,
                compiled["workflow"],
                executable=executable,
            )
            compiled["workflow"]["maturity"] = maturity
            compiled["provenance"]["maturity"] = maturity
            self.registry.update_build(
                build_id,
                "validating",
                progress=95,
                detail="正在验证变量、来源追踪、风险确认与成功判定",
                metrics=metrics,
            )
            validation = self.validator.validate(compiled, trajectory_dicts)
            if not validation.valid:
                raise ValueError(
                    "Skill validation failed: " + "; ".join(validation.errors)
                )
            validation_payload = validation.to_dict()
            validation_payload["executable"] = executable
            validation_payload["maturityReady"] = maturity["ready"]
            validation_payload["readiness"] = maturity["readiness"]
            validation_payload.setdefault("checks", {})[
                "execution_adapter"
            ] = executable
            validation_payload.setdefault("checks", {})[
                "maturity_ready"
            ] = maturity["ready"]
            if not executable:
                validation_payload.setdefault("warnings", []).append(
                    "no verified Elfred execution adapter supports this workflow yet"
                )
                validation_payload["score"] = round(
                    max(0.0, float(validation_payload["score"]) - 0.1), 2
                )
            if not maturity["ready"]:
                validation_payload.setdefault("warnings", []).append(
                    "Skill maturity gates are not complete; continue observing"
                )
            skill = self.registry.register_draft(
                compiled=compiled,
                distilled=distilled,
                validation=validation_payload,
                trajectories=trajectory_dicts,
                version=version,
                skill_id=skill_id,
            )
            final_build = self.registry.update_build(
                build_id,
                "draft_ready",
                skill_id=skill["skill_id"],
                version_id=skill["current_version"]["version_id"],
                progress=100,
                detail="Skill 草稿已完整编译并通过验证，等待你的审核",
                metrics={
                    **metrics,
                    "validationScore": validation_payload["score"],
                    "validationPassed": validation.valid,
                    "generationMode": generated.mode,
                    "model": model,
                    "maturityReadiness": maturity["readiness"],
                    "maturityReady": maturity["ready"],
                    "maturityStage": maturity["stage"],
                },
            )
            return {
                "build": final_build,
                "skill": skill,
                "trajectories": [
                    self._trajectory_summary(item) for item in trajectory_dicts
                ],
                "evidenceManifest": evidence_manifest,
                "generation": generated.metadata(),
                "maturity": maturity,
            }
        except Exception as error:
            self.registry.update_build(
                build_id,
                "failed",
                error=str(error)[:2000],
                detail=f"Skill 生成失败：{str(error)[:240]}",
            )
            raise

    def approve(
        self, skill_id: str, *, allow_heuristic: bool = False
    ) -> dict[str, Any]:
        candidate = self.registry.get(skill_id)
        if candidate is None:
            raise KeyError(skill_id)
        review_skill = dict(candidate)
        review_skill["current_version"] = candidate.get("current_version")
        if not self.runner.can_execute(review_skill, {}):
            raise ValueError(
                "Skill has no verified Elfred execution adapter yet"
            )
        skill = self.registry.approve(
            skill_id, allow_heuristic=allow_heuristic
        )
        self.memory.save_skill_learning(
            {
                "type": "skill_approved",
                "skillId": skill_id,
                "version": skill["current_version"]["version"],
                "at": now_iso(),
            }
        )
        return skill

    def match(self, task_context: dict[str, Any]) -> list[dict[str, Any]]:
        return self.matcher.match(task_context)

    def set_auto_execute(
        self,
        skill_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        skill = self.registry.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        if enabled:
            if skill["status"] not in {"approved", "active"}:
                raise ValueError(
                    "Only approved or active skills can enable auto execution"
                )
            execution_skill = dict(skill)
            execution_skill["current_version"] = (
                skill.get("published_version")
                or skill.get("current_version")
            )
            if not self.runner.can_execute(execution_skill, {}):
                raise ValueError(
                    "Skill has no verified Elfred execution adapter"
                )
            plan = self.runner.dry_run(execution_skill, {})
            if plan["requiresConfirmation"]:
                raise ValueError(
                    "Skills requiring confirmation cannot auto execute"
                )
        return self.registry.set_auto_execute(skill_id, enabled)

    def scan_active_task_matches(self) -> dict[str, Any]:
        todos = self.client.list_todos()
        known_todo_ids = {
            int(todo["id"])
            for todo in todos
            if todo.get("id") is not None
        }
        scanned = 0
        suggestions = 0
        auto_runs = 0
        errors: list[dict[str, Any]] = []
        for todo in todos:
            todo_id = todo.get("id")
            if todo_id is None:
                continue
            status = str(todo.get("status") or "active").casefold()
            if (
                status in {"completed", "canceled"}
                or int(todo.get("percent_complete") or 0) >= 100
            ):
                self.registry.upsert_task_matches(
                    freetodo_todo_id=int(todo_id),
                    task_id=None,
                    task_context=self._task_match_context(todo),
                    matches=[],
                )
                continue
            scanned += 1
            context = self._task_match_context(todo)
            canonical = self.store.canonical_task_by_freetodo_id(
                int(todo_id)
            )
            matches = [
                match
                for match in self.match(context)
                if float(match.get("score") or 0)
                >= float(self.settings.skill_match_min_score)
                and match.get("versionId")
            ]
            stored = self.registry.upsert_task_matches(
                freetodo_todo_id=int(todo_id),
                task_id=(
                    str(canonical["task_id"]) if canonical else None
                ),
                task_context=context,
                matches=matches,
            )
            suggestions += sum(
                1 for item in stored if item["status"] == "suggested"
            )
            for match in stored:
                if not self._can_auto_execute_match(match, todo):
                    continue
                self.registry.update_task_match(
                    freetodo_todo_id=int(todo_id),
                    skill_id=str(match["skill_id"]),
                    status="running",
                )
                try:
                    outcome = self.run_skill(
                        str(match["skill_id"]),
                        inputs={
                            "sourceText": context.get("sourceText") or "",
                            "bulletCount": 3,
                        },
                        task_context={
                            "freetodoTodoId": int(todo_id),
                            "userConfirmed": False,
                            "automatic": True,
                        },
                    )
                    if (outcome.get("run") or {}).get("status") == "succeeded":
                        auto_runs += 1
                except Exception as error:
                    self.registry.update_task_match(
                        freetodo_todo_id=int(todo_id),
                        skill_id=str(match["skill_id"]),
                        status="failed",
                        error=str(error),
                    )
                    errors.append(
                        {
                            "freetodoTodoId": int(todo_id),
                            "skillId": match["skill_id"],
                            "error": str(error)[:240],
                        }
                    )
                break
        self.registry.stale_missing_task_matches(known_todo_ids)
        return {
            "scannedTasks": scanned,
            "suggestions": suggestions,
            "autoRuns": auto_runs,
            "errors": errors,
        }

    @staticmethod
    def _task_match_context(todo: dict[str, Any]) -> dict[str, Any]:
        source_text = str(
            todo.get("description")
            or todo.get("user_notes")
            or ""
        ).strip()
        task_text = " ".join(
            [
                str(todo.get("name") or ""),
                str(todo.get("description") or ""),
                str(todo.get("categories") or ""),
            ]
        ).casefold()
        task_type = (
            "document_summary"
            if any(
                marker in task_text
                for marker in ("摘要", "总结", "summary", "summarize")
            )
            else ""
        )
        return {
            "title": str(todo.get("name") or ""),
            "description": str(todo.get("description") or ""),
            "context": str(todo.get("user_notes") or ""),
            "currentApp": str(todo.get("categories") or ""),
            "taskType": task_type,
            "sourceText": source_text,
            "hasSourceText": bool(source_text),
            "freetodoTodoId": todo.get("id"),
        }

    def _can_auto_execute_match(
        self,
        match: dict[str, Any],
        todo: dict[str, Any],
    ) -> bool:
        if match.get("status") != "suggested":
            return False
        if not match.get("auto_execute"):
            return False
        if float(match.get("score") or 0) < float(
            self.settings.skill_auto_execute_min_score
        ):
            return False
        if str(todo.get("status") or "active").casefold() == "draft":
            return False
        source_text = str(
            (match.get("task_context") or {}).get("sourceText") or ""
        ).strip()
        return len(source_text) >= 20

    def run_skill(
        self,
        skill_id: str,
        *,
        inputs: dict[str, Any],
        task_context: dict[str, Any],
    ) -> dict[str, Any]:
        skill = self.registry.get(skill_id)
        if skill is None:
            raise KeyError(skill_id)
        if skill["status"] not in {"approved", "active"}:
            raise ValueError("Only approved or active skills can run")
        execution_skill = dict(skill)
        execution_skill["current_version"] = (
            skill.get("published_version") or skill.get("current_version")
        )
        if not self.runner.can_execute(execution_skill, task_context):
            raise ValueError("No current Elfred execution adapter supports this skill")
        plan = self.runner.dry_run(execution_skill, inputs)
        todo_id = task_context.get("freetodoTodoId")
        canonical = (
            self.store.canonical_task_by_freetodo_id(int(todo_id))
            if todo_id is not None
            else None
        )
        run = self.registry.create_run(
            skill_id=skill_id,
            version_id=execution_skill["current_version"]["version_id"],
            task_id=canonical.get("task_id") if canonical else None,
            freetodo_todo_id=int(todo_id) if todo_id is not None else None,
            inputs=inputs,
            plan=plan,
            requires_confirmation=bool(plan["requiresConfirmation"]),
        )
        if plan["requiresConfirmation"] and not task_context.get("userConfirmed"):
            stopped = self.registry.finish_run(
                run["run_id"],
                status="confirmation_required",
                result={
                    "message": "Explicit user confirmation is required before execution"
                },
            )
            if todo_id is not None:
                self.registry.update_task_match(
                    freetodo_todo_id=int(todo_id),
                    skill_id=skill_id,
                    status="confirmation_required",
                    run_id=run["run_id"],
                )
            return {"run": stopped, "result": stopped["result"]}
        try:
            result = self.runner.execute(
                execution_skill, inputs, task_context
            )
            completed = self.registry.finish_run(
                run["run_id"], status="succeeded", result=result
            )
            self.memory.save_skill_learning(
                {
                    "type": "skill_run_succeeded",
                    "skillId": skill_id,
                    "runId": run["run_id"],
                    "at": now_iso(),
                }
            )
            if todo_id is not None:
                self.registry.update_task_match(
                    freetodo_todo_id=int(todo_id),
                    skill_id=skill_id,
                    status="completed",
                    run_id=run["run_id"],
                )
            return {"run": completed, "result": result}
        except Exception as error:
            failed = self.registry.finish_run(
                run["run_id"], status="failed", error=str(error)
            )
            self.memory.save_skill_learning(
                {
                    "type": "skill_run_failed",
                    "skillId": skill_id,
                    "runId": run["run_id"],
                    "error": str(error),
                    "at": now_iso(),
                }
            )
            if todo_id is not None:
                self.registry.update_task_match(
                    freetodo_todo_id=int(todo_id),
                    skill_id=skill_id,
                    status="failed",
                    run_id=run["run_id"],
                    error=str(error),
                )
            return {"run": failed, "result": {}, "error": str(error)}

    def record_feedback(
        self,
        run_id: str,
        *,
        rating: int | None = None,
        outcome: str | None = None,
        comment: str | None = None,
        corrections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        feedback = self.feedback_recorder.record_feedback(
            run_id,
            rating=rating,
            outcome=outcome,
            comment=comment,
            corrections=corrections or [],
        )
        self.memory.save_skill_learning(
            {"type": "skill_feedback", **feedback}
        )
        return feedback

    def create_demo_task(
        self,
        *,
        title: str,
        source_text: str,
        current_app: str = "Elfred Web",
    ) -> dict[str, Any]:
        if len(source_text.strip()) < 20:
            raise ValueError("sourceText must contain at least 20 characters")
        task = self.client.create_todo(
            {
                "uid": "elfred-skill-demo-run-" + uuid.uuid4().hex[:24],
                "name": title.strip() or "读取新文档并生成三点摘要",
                "summary": title.strip() or "读取新文档并生成三点摘要",
                "description": source_text.strip(),
                "categories": "Skill Foundry 演示",
                "status": "active",
                "priority": "medium",
                "percent_complete": 0,
            }
        )
        context = {
            "title": task["name"],
            "description": task.get("description") or "",
            "currentApp": current_app,
            "inputFileTypes": [".txt"],
            "context": "用户要求读取文档并生成中文关键要点摘要",
            "taskType": "document_summary",
            "sourceText": source_text,
            "hasSourceText": True,
        }
        return {"task": task, "matches": self.match(context), "context": context}

    def seed_demo(self) -> dict[str, Any]:
        definitions = self._demo_definitions()
        seeded: list[dict[str, Any]] = []
        for index, definition in enumerate(definitions, 1):
            uid = f"elfred-skill-foundry-demo-{index:03d}"
            todo = self.client.find_todo_by_uid(uid)
            if todo is None:
                todo = self.client.create_todo(
                    {
                        "uid": uid,
                        "name": definition["title"],
                        "summary": definition["title"],
                        "description": definition["summary"],
                        "user_notes": definition["output"],
                        "categories": "Skill Foundry 演示",
                        "status": "completed",
                        "priority": "medium",
                        "percent_complete": 100,
                        "completed_at": definition["completed_at"],
                    }
                )
            task_id = f"demo_doc_summary_{index:03d}"
            canonical = self.store.upsert_canonical_task(
                task_id,
                title=definition["title"],
                description=definition["summary"],
                domain="work",
                project="Skill Foundry Demo",
                stage="completed",
                progress_percent=100,
                priority="medium",
                confidence=1.0,
                freetodo_todo_id=int(todo["id"]),
                freetodo_uid=str(todo["uid"]),
                last_remote=todo,
                metadata={"demo": True, "task_type": "document_summary"},
                observed_at=definition["completed_at"],
            )
            evidence_id = self.store.upsert_task_evidence(
                task_id,
                f"demo_event_doc_summary_{index:03d}",
                "completed_document_summary",
                relation="update",
                confidence=1.0,
                evidence={
                    "summary": definition["summary"],
                    "trajectory": definition["trajectory"],
                },
            )
            seeded.append(
                {
                    "taskId": canonical["task_id"],
                    "freetodoTodoId": todo["id"],
                    "evidenceId": evidence_id,
                    "title": todo["name"],
                }
            )
        return {"seeded": seeded, "total": len(seeded)}

    @staticmethod
    def _trajectory_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "taskId": item["taskId"],
            "freetodoTodoId": item["freetodoTodoId"],
            "intent": item["intent"],
            "stepCount": len(item["steps"]),
            "sourceQuality": item["sourceQuality"],
            "evidenceRefs": item["evidenceRefs"],
        }

    @staticmethod
    def _demo_definitions() -> list[dict[str, Any]]:
        source_texts = [
            "产品调研显示，用户希望摘要能够直接回写任务卡。核心需求是保留来源、控制在三个要点，并在保存后检查任务状态。",
            "项目周报记录了 Observer、Adapter 与 FreeTodo 的联调结果。主要结论是证据已落库、任务卡可更新、完成状态需要二次核验。",
            "实验记录比较了长段落与三点摘要。三点结构更容易复查，中文输出更符合当前用户习惯，失败时应保留原任务。",
        ]
        titles = [
            "阅读产品调研备忘录并生成三点摘要",
            "阅读项目周报并生成三点摘要",
            "阅读实验记录并生成三点摘要",
        ]
        summaries = [
            "调研备忘录已经读取，并将来源追踪、三点结构和完成状态验证写入摘要。",
            "项目周报已经读取，并提炼 Observer、Adapter、FreeTodo 三项联调结论。",
            "实验记录已经读取，确认中文三点摘要更适合复查且失败时不得覆盖原任务。",
        ]
        definitions = []
        for index in range(3):
            completed_at = f"2026-07-{10 + index:02d}T18:00:00+08:00"
            trajectory = {
                "taskType": "document_summary",
                "intent": "读取文档并生成中文三点要点摘要",
                "summary": summaries[index],
                "inputs": {
                    "sourceText": source_texts[index],
                    "documentTitle": titles[index],
                    "outputLanguage": "zh-CN",
                    "bulletCount": 3,
                },
                "contextApps": [["Edge"], ["Word"], ["PDF Reader"]][index],
                "steps": [
                    {
                        "sequence": 1,
                        "actionType": "read_document",
                        "tool": "document_reader",
                        "target": "${documentTitle}",
                        "arguments": {"text": "${sourceText}"},
                        "result": "success",
                    },
                    {
                        "sequence": 2,
                        "actionType": "extract_key_points",
                        "tool": "local_text_analyzer",
                        "arguments": {"limit": "${bulletCount}"},
                        "result": "success",
                    },
                    {
                        "sequence": 3,
                        "actionType": "write_summary",
                        "tool": "summary_writer",
                        "arguments": {"language": "${outputLanguage}"},
                        "result": "success",
                    },
                    {
                        "sequence": 4,
                        "actionType": "create_task_card",
                        "tool": "freetodo_task_api",
                        "arguments": {"status": "completed"},
                        "result": "success",
                    },
                    {
                        "sequence": 5,
                        "actionType": "verify_output",
                        "tool": "task_verifier",
                        "arguments": {
                            "status": "completed",
                            "percentComplete": 100,
                        },
                        "result": "success",
                    },
                ],
                "outputs": [
                    {"type": "task_summary", "value": summaries[index]}
                ],
                "successSignals": [
                    "摘要使用中文",
                    "摘要包含三个关键要点",
                    "任务状态为 completed",
                    "原任务卡仍然存在",
                ],
                "corrections": (
                    [
                        {
                            "step": "write_summary",
                            "reason": "初稿要点过多",
                            "correction": "固定为三个可核验要点",
                        }
                    ]
                    if index == 2
                    else []
                ),
            }
            definitions.append(
                {
                    "title": titles[index],
                    "summary": summaries[index],
                    "output": "关键要点：\n- 来源可追溯\n- 三点中文摘要\n- 完成状态已验证",
                    "completed_at": completed_at,
                    "trajectory": trajectory,
                }
            )
        return definitions
