from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from adapter.privacy import decide, redact_text, safe_event_view
from adapter.skill_foundry.evidence_pack import FileEvidenceReader
from adapter.skill_foundry.passive import infer_task_type
from adapter.skill_foundry.models import TaskTrajectory, TrajectoryStep


COMPLETED_STAGES = {"completed", "done", "canceled"}


class TaskEvidenceError(ValueError):
    pass


class TaskEvidenceAssembler:
    """Join FreeTodo cards, canonical tasks, Observer events and task evidence."""

    def __init__(
        self, store: Any, freetodo_client: Any, settings: Any | None = None
    ) -> None:
        self.store = store
        self.client = freetodo_client
        self.settings = settings
        self.file_reader = FileEvidenceReader()

    def assemble(
        self,
        freetodo_todo_ids: list[int],
        progress_callback: Callable[[int, int, dict[str, int]], None] | None = None,
    ) -> list[dict[str, Any]]:
        if len(freetodo_todo_ids) < 2:
            raise TaskEvidenceError(
                "At least two completed tasks are required for repeated-work evidence"
            )
        maximum = max(
            2,
            int(
                getattr(
                    self.settings, "skill_passive_max_tasks", 20
                )
            ),
        )
        if len(freetodo_todo_ids) > maximum:
            raise TaskEvidenceError(
                f"At most {maximum} tasks may be processed in one bounded build"
            )
        normalized_ids = [int(value) for value in freetodo_todo_ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            raise TaskEvidenceError("Duplicate task IDs are not allowed")

        assembled: list[dict[str, Any]] = []
        for todo_id in normalized_ids:
            todo = self.client.get_todo(todo_id)
            if str(todo.get("status") or "").casefold() != "completed":
                raise TaskEvidenceError(
                    f"Task {todo_id} is not completed and cannot be fused"
                )
            canonical = self.store.canonical_task_by_freetodo_id(todo_id)
            task_id = (
                str(canonical["task_id"])
                if canonical
                else f"freetodo_{todo_id}"
            )
            evidence = (
                self.store.task_evidence(task_id=task_id, limit=500)
                if canonical
                else []
            )
            linked_event_ids = {
                str(item.get("event_id") or "")
                for item in evidence
                if item.get("event_id")
            }
            window_events = self._task_window_events(todo)
            event_records: list[dict[str, Any]] = []
            analyses: list[dict[str, Any]] = []
            model_files: list[dict[str, Any]] = []
            privacy_skipped = 0
            seen_event_ids: set[str] = set()
            locally_allowed_event_ids: set[str] = set()
            event_candidates: list[tuple[str, dict[str, Any] | None, str]] = [
                (
                    str(item.get("event_id") or ""),
                    None,
                    "task_evidence",
                )
                for item in evidence
            ]
            event_candidates.extend(
                (
                    str(record.get("event_id") or ""),
                    record,
                    "task_time_window",
                )
                for record in window_events
                if str(record.get("event_id") or "") not in linked_event_ids
            )
            for event_id, event, association in event_candidates:
                if not event_id or event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                event = event or self.store.get_event(
                    event_id, include_deleted=True
                )
                if event:
                    raw_event = event["payload"].get("event") or {}
                    decision = decide(raw_event)
                    if not decision.local_allowed:
                        privacy_skipped += 1
                    else:
                        locally_allowed_event_ids.add(event_id)
                        safe_event, redactions = safe_event_view(raw_event)
                        artifacts, screenshot_file = self._artifacts(
                            raw_event, cloud_allowed=decision.cloud_allowed
                        )
                        safe_event["artifacts"] = artifacts
                        safe_event["redactions"] = redactions
                        safe_event["cloudAllowed"] = decision.cloud_allowed
                        safe_event["association"] = association
                        event_records.append(safe_event)
                        if screenshot_file:
                            model_files.append(screenshot_file)
                        analysis = self.store.task_analysis(event_id)
                        if analysis:
                            analyses.append(analysis)
            attachments = [
                item
                for item in todo.get("attachments") or []
                if isinstance(item, dict)
            ]
            allow_attachment_images = bool(
                self.settings
                and self.settings.llm_cloud_consent
                and self.settings.skill_include_screenshots
                and self.settings.skill_vision_model_id
            )
            attachment_evidence, attachment_model_files = (
                self.file_reader.read_many(
                    attachments,
                    allow_model_images=allow_attachment_images,
                )
            )
            model_files.extend(attachment_model_files)
            linked_journals = self._linked_journals(
                locally_allowed_event_ids
            )
            execution_history = self._execution_history(todo_id)
            assembled.append(
                {
                    "task_id": task_id,
                    "freetodo_todo_id": todo_id,
                    "todo": todo,
                    "canonical_task": canonical,
                    "task_evidence": evidence,
                    "observer_events": event_records,
                    "task_analyses": analyses,
                    "attachment_evidence": attachment_evidence,
                    "linked_journals": linked_journals,
                    "execution_history": execution_history,
                    "privacy_skipped": privacy_skipped,
                    "_model_files": model_files,
                }
            )
            if progress_callback:
                progress_callback(
                    len(assembled),
                    len(normalized_ids),
                    {
                        "observerEvents": sum(
                            len(item.get("observer_events") or [])
                            for item in assembled
                        ),
                        "attachments": sum(
                            len(item.get("attachment_evidence") or [])
                            for item in assembled
                        ),
                        "journals": sum(
                            len(item.get("linked_journals") or [])
                            for item in assembled
                        ),
                        "skillRuns": sum(
                            len(item.get("execution_history") or [])
                            for item in assembled
                        ),
                    },
                )
        return assembled

    def _linked_journals(self, event_ids: set[str]) -> list[dict[str, Any]]:
        journals: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for event_id in sorted(event_ids):
            links = self.store.remote_links(event_id, "journal").get(
                "journal", []
            )
            for link in links:
                journal_id = link.get("freetodo_journal_id")
                if not journal_id or int(journal_id) in seen_ids:
                    continue
                try:
                    journal = self.client.get_journal(int(journal_id))
                except Exception:
                    continue
                seen_ids.add(int(journal_id))
                redactions: list[str] = []

                def clean(value: Any) -> str:
                    text, found = redact_text(str(value or ""))
                    redactions.extend(found)
                    return text

                journals.append(
                    {
                        "journalId": int(journal_id),
                        "date": clean(journal.get("date")),
                        "name": clean(journal.get("name")),
                        "objective": clean(journal.get("content_objective")),
                        "summary": clean(journal.get("content_ai")),
                        "userNotes": clean(journal.get("user_notes")),
                        "tags": [
                            clean(value) for value in journal.get("tags") or []
                        ],
                        "redactions": sorted(set(redactions)),
                    }
                )
        return journals

    def _execution_history(self, todo_id: int) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            runs = conn.execute(
                "SELECT * FROM skill_runs WHERE freetodo_todo_id=? "
                "ORDER BY started_at",
                (int(todo_id),),
            ).fetchall()
            output: list[dict[str, Any]] = []
            for row in runs:
                plan = json.loads(row["plan_json"])
                result = json.loads(row["result_json"])
                feedback_rows = conn.execute(
                    "SELECT * FROM skill_feedback WHERE run_id=? "
                    "ORDER BY created_at",
                    (row["run_id"],),
                ).fetchall()
                feedback = []
                for feedback_row in feedback_rows:
                    corrections = json.loads(
                        feedback_row["corrections_json"]
                    )
                    safe_corrections, correction_redactions = (
                        self._redact_structure(corrections)
                    )
                    comment, comment_redactions = redact_text(
                        str(feedback_row["comment"] or "")
                    )
                    feedback.append(
                        {
                            "rating": feedback_row["rating"],
                            "outcome": feedback_row["outcome"],
                            "comment": comment,
                            "corrections": safe_corrections,
                            "redactions": sorted(
                                set(
                                    correction_redactions
                                    + comment_redactions
                                )
                            ),
                        }
                    )
                summary, result_redactions = redact_text(
                    str(result.get("summary") or "")
                )
                output.append(
                    {
                        "runId": row["run_id"],
                        "skillId": row["skill_id"],
                        "status": row["status"],
                        "startedAt": row["started_at"],
                        "finishedAt": row["finished_at"],
                        "plan": {
                            "adapter": plan.get("adapter"),
                            "steps": [
                                {
                                    "id": step.get("id"),
                                    "action": step.get("action"),
                                    "sourceAction": step.get("sourceAction"),
                                    "tool": step.get("tool"),
                                }
                                for step in plan.get("steps") or []
                                if isinstance(step, dict)
                            ],
                            "requiresConfirmation": bool(
                                plan.get("requiresConfirmation")
                            ),
                        },
                        "result": {
                            "status": result.get("status"),
                            "summary": summary,
                            "completedBySkill": result.get(
                                "completedBySkill"
                            ),
                        },
                        "feedback": feedback,
                        "redactions": sorted(set(result_redactions)),
                    }
                )
        return output

    @staticmethod
    def _redact_structure(value: Any) -> tuple[Any, list[str]]:
        redactions: list[str] = []
        if isinstance(value, dict):
            output = {}
            for key, item in value.items():
                cleaned, found = TaskEvidenceAssembler._redact_structure(item)
                output[str(key)] = cleaned
                redactions.extend(found)
            return output, redactions
        if isinstance(value, list):
            output = []
            for item in value:
                cleaned, found = TaskEvidenceAssembler._redact_structure(item)
                output.append(cleaned)
                redactions.extend(found)
            return output, redactions
        if isinstance(value, str):
            return redact_text(value)
        return value, redactions

    def _task_window_events(self, todo: dict[str, Any]) -> list[dict[str, Any]]:
        started = todo.get("start_time")
        ended = todo.get("completed_at") or todo.get("updated_at")
        if not started or not ended or not hasattr(self.store, "events_between"):
            return []
        try:
            start_dt = datetime.fromisoformat(
                str(started).replace("Z", "+00:00")
            )
            end_dt = datetime.fromisoformat(str(ended).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return []
        try:
            duration = (end_dt - start_dt).total_seconds()
        except TypeError:
            return []
        if duration < 0 or duration > 12 * 60 * 60:
            return []
        return self.store.events_between(str(started), str(ended), limit=1000)

    def _artifacts(
        self, event: dict[str, Any], *, cloud_allowed: bool
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        raw = event.get("artifacts") or {}
        screenshot_id = str(raw.get("screenshot_id") or "").strip()
        screenshot_path = str(raw.get("screenshot_path") or "").strip()
        ocr_id = str(raw.get("ocr_id") or "").strip()
        artifacts: list[dict[str, Any]] = []
        model_file: dict[str, Any] | None = None
        if ocr_id:
            artifacts.append({"kind": "ocr", "id": ocr_id})
        if screenshot_id or screenshot_path:
            resolved = self._resolve_path(screenshot_path)
            can_include = bool(
                resolved
                and resolved.is_file()
                and cloud_allowed
                and self.settings
                and self.settings.llm_cloud_consent
                and self.settings.skill_include_screenshots
                and self.settings.skill_vision_model_id
            )
            artifacts.append(
                {
                    "kind": "screenshot",
                    "id": screenshot_id or None,
                    "name": resolved.name if resolved else Path(screenshot_path).name,
                    "exists": bool(resolved and resolved.is_file()),
                    "modelIncluded": can_include,
                }
            )
            if can_include and resolved:
                model_file = {
                    "path": str(resolved),
                    "filename": resolved.name,
                    "mime": "image/" + (
                        "jpeg"
                        if resolved.suffix.casefold() in {".jpg", ".jpeg"}
                        else resolved.suffix.casefold().lstrip(".") or "png"
                    ),
                    "source": "observer_screenshot",
                    "eventId": event.get("event_id"),
                }
        return artifacts, model_file

    def _resolve_path(self, value: str) -> Path | None:
        if not value:
            return None
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        candidates = [Path.cwd() / path]
        if self.settings:
            skill_root = getattr(self.settings, "skill_root", None)
            root = Path(skill_root).parent if skill_root else Path.cwd()
            candidates.extend([root / path, root / "elfred-observer" / path])
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return candidates[-1]


class TaskTrajectoryNormalizer:
    """Produce a stable trajectory even when Observer has only sparse evidence."""

    DEFAULT_STEPS = (
        ("read_document", "document_reader"),
        ("extract_key_points", "local_text_analyzer"),
        ("write_summary", "summary_writer"),
        ("create_task_card", "freetodo_task_api"),
        ("verify_output", "task_verifier"),
    )
    DEFAULT_WORKFLOWS = {
        "document_summary": DEFAULT_STEPS,
        "software_development": (
            ("inspect_context", "workspace_reader"),
            ("edit_code", "code_editor"),
            ("run_tests", "test_runner"),
            ("verify_output", "task_verifier"),
        ),
        "research": (
            ("gather_sources", "research_reader"),
            ("synthesize_findings", "research_analyzer"),
            ("save_output", "document_writer"),
            ("verify_output", "task_verifier"),
        ),
        "data_analysis": (
            ("read_dataset", "data_reader"),
            ("analyze_data", "data_analyzer"),
            ("create_output", "artifact_writer"),
            ("verify_output", "task_verifier"),
        ),
        "task_planning": (
            ("analyze_goal", "planning_agent"),
            ("create_plan", "planning_agent"),
            ("update_task", "freetodo_task_api"),
            ("verify_output", "task_verifier"),
        ),
        "communication": (
            ("read_context", "context_reader"),
            ("draft_content", "writing_agent"),
            ("review_content", "content_verifier"),
        ),
    }

    def normalize_many(self, evidence_sets: list[dict[str, Any]]) -> list[TaskTrajectory]:
        return [self.normalize(item) for item in evidence_sets]

    def normalize(self, assembled: dict[str, Any]) -> TaskTrajectory:
        todo = assembled["todo"]
        canonical = assembled.get("canonical_task") or {}
        evidence = assembled.get("task_evidence") or []
        trajectory_payload = self._trajectory_payload(evidence)
        task_type = str(
            trajectory_payload.get("taskType")
            or (canonical.get("metadata") or {}).get("task_type")
            or infer_task_type(
                " ".join(
                    str(value or "")
                    for value in (
                        todo.get("name"),
                        todo.get("summary"),
                        todo.get("description"),
                        todo.get("user_notes"),
                    )
                )
            )
            or "unknown"
        )
        execution_history = assembled.get("execution_history") or []
        context_apps = self._context_apps(assembled, trajectory_payload)
        intent = str(
            trajectory_payload.get("intent")
            or canonical.get("title")
            or todo.get("summary")
            or todo.get("name")
            or ""
        ).strip()
        summary = str(
            trajectory_payload.get("summary")
            or canonical.get("description")
            or todo.get("description")
            or todo.get("user_notes")
            or todo.get("summary")
            or ""
        ).strip()
        inputs = dict(trajectory_payload.get("inputs") or {})
        if not inputs:
            inputs = {
                "sourceText": summary,
                "documentTitle": str(todo.get("name") or ""),
                "outputLanguage": "zh-CN",
            }
        raw_steps = trajectory_payload.get("steps")
        source_quality = "captured"
        if not isinstance(raw_steps, list) or not raw_steps:
            raw_steps = self._execution_steps(execution_history)
            if raw_steps:
                source_quality = "captured_execution"
            else:
                workflow = self.DEFAULT_WORKFLOWS.get(
                    task_type, self.DEFAULT_STEPS
                )
                raw_steps = [
                    {
                        "sequence": index,
                        "actionType": action,
                        "tool": tool,
                        "target": "${documentTitle}" if index == 1 else "",
                        "arguments": {},
                        "result": "success",
                    }
                    for index, (action, tool) in enumerate(workflow, 1)
                ]
                source_quality = "inferred"
        steps = [self._step(raw, index) for index, raw in enumerate(raw_steps, 1)]
        outputs = trajectory_payload.get("outputs")
        if not isinstance(outputs, list):
            outputs = [
                {
                    "type": "skill_run_result",
                    "value": (run.get("result") or {}).get("summary"),
                    "runId": run.get("runId"),
                }
                for run in execution_history
                if (run.get("result") or {}).get("summary")
            ] or [{"type": "task_summary", "value": summary}]
        signals = trajectory_payload.get("successSignals")
        if not isinstance(signals, list) or not signals:
            signals = [
                "任务状态为 completed",
                "摘要包含可核验的关键要点",
                "输出保存在原任务卡",
            ]
        corrections = trajectory_payload.get("corrections")
        if not isinstance(corrections, list):
            corrections = []
        corrections = [
            *corrections,
            *[
                correction
                for run in execution_history
                for feedback in run.get("feedback") or []
                for correction in feedback.get("corrections") or []
                if isinstance(correction, dict)
            ],
        ]
        evidence_refs = [
            str(item.get("evidence_id"))
            for item in evidence
            if item.get("evidence_id")
        ]
        return TaskTrajectory(
            task_id=str(assembled["task_id"]),
            freetodo_todo_id=int(assembled["freetodo_todo_id"]),
            intent=intent,
            inputs=inputs,
            context_apps=context_apps,
            steps=steps,
            outputs=[item for item in outputs if isinstance(item, dict)],
            success_signals=[str(item) for item in signals if str(item).strip()],
            corrections=[item for item in corrections if isinstance(item, dict)],
            summary=summary,
            started_at=self._time(todo, "start_time", "created_at"),
            ended_at=self._time(todo, "completed_at", "updated_at"),
            evidence_refs=evidence_refs,
            source_quality=source_quality,
            metadata={
                "category": todo.get("categories"),
                "priority": todo.get("priority"),
                "taskType": task_type,
                "observerEventCount": len(assembled.get("observer_events") or []),
                "attachmentCount": len(assembled.get("attachment_evidence") or []),
                "journalCount": len(assembled.get("linked_journals") or []),
                "skillRunCount": len(execution_history),
                "privacySkipped": int(assembled.get("privacy_skipped") or 0),
            },
        )

    @staticmethod
    def _execution_steps(
        execution_history: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        for run in reversed(execution_history):
            if run.get("status") != "succeeded":
                continue
            steps = (run.get("plan") or {}).get("steps") or []
            if not steps:
                continue
            return [
                {
                    "sequence": index,
                    "actionType": step.get("sourceAction")
                    or step.get("action")
                    or "unknown",
                    "tool": step.get("tool") or "unknown",
                    "arguments": {},
                    "result": "success",
                }
                for index, step in enumerate(steps, 1)
                if isinstance(step, dict)
            ]
        return []

    @staticmethod
    def _trajectory_payload(evidence: list[dict[str, Any]]) -> dict[str, Any]:
        for item in evidence:
            payload = item.get("evidence") or {}
            trajectory = payload.get("trajectory")
            if isinstance(trajectory, dict):
                return trajectory
        return {}

    @staticmethod
    def _context_apps(
        assembled: dict[str, Any], trajectory_payload: dict[str, Any]
    ) -> list[str]:
        apps = [
            str(value).strip()
            for value in trajectory_payload.get("contextApps") or []
            if str(value).strip()
        ]
        for event in assembled.get("observer_events") or []:
            app = str((event.get("app") or {}).get("name") or "").strip()
            if app:
                apps.append(app)
        return list(dict.fromkeys(apps))

    @staticmethod
    def _step(raw: Any, fallback_sequence: int) -> TrajectoryStep:
        value = raw if isinstance(raw, dict) else {}
        return TrajectoryStep(
            sequence=int(value.get("sequence") or fallback_sequence),
            action_type=str(
                value.get("actionType") or value.get("action_type") or "unknown"
            ).strip(),
            tool=str(value.get("tool") or "unknown").strip(),
            target=str(value.get("target") or "").strip(),
            arguments=dict(value.get("arguments") or {}),
            observation_before=dict(
                value.get("observationBefore")
                or value.get("observation_before")
                or {}
            ),
            observation_after=dict(
                value.get("observationAfter")
                or value.get("observation_after")
                or {}
            ),
            result=str(value.get("result") or "success").strip().casefold(),
            optional=bool(value.get("optional", False)),
            condition=(
                str(value.get("condition")).strip()
                if value.get("condition") is not None
                else None
            ),
        )

    @staticmethod
    def _time(todo: dict[str, Any], primary: str, fallback: str) -> str | None:
        value = todo.get(primary) or todo.get(fallback)
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value) if value else None
