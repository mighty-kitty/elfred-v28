from __future__ import annotations

import hashlib
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from adapter.privacy import redact_text


TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".jsonl",
    ".csv",
    ".tsv",
    ".log",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

EVIDENCE_PROFILES = {
    "document_summary": {
        "title": 5,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 25,
        "successSignals": 15,
        "sourceContent": 20,
        "outputEvidence": 20,
    },
    "software_development": {
        "title": 5,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 30,
        "successSignals": 15,
        "outputEvidence": 15,
        "toolTrace": 20,
    },
    "research": {
        "title": 5,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 25,
        "successSignals": 15,
        "sourceContent": 20,
        "outputEvidence": 20,
    },
    "data_analysis": {
        "title": 5,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 25,
        "successSignals": 15,
        "sourceContent": 20,
        "outputEvidence": 20,
    },
    "task_planning": {
        "title": 10,
        "summary": 15,
        "timing": 5,
        "workflowTrace": 25,
        "successSignals": 20,
        "outputEvidence": 25,
    },
    "communication": {
        "title": 10,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 25,
        "successSignals": 20,
        "outputEvidence": 20,
        "contextEvidence": 10,
    },
    "unknown": {
        "title": 5,
        "summary": 10,
        "timing": 5,
        "workflowTrace": 30,
        "successSignals": 20,
        "outputEvidence": 20,
        "contextEvidence": 10,
    },
}


class FileEvidenceReader:
    """Inventory selected-task files and extract bounded, redacted local text."""

    def __init__(self, max_chars_per_file: int = 12000) -> None:
        self.max_chars_per_file = max(1000, int(max_chars_per_file))

    def read_many(
        self,
        attachments: list[dict[str, Any]],
        *,
        allow_model_images: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        manifest: list[dict[str, Any]] = []
        model_files: list[dict[str, Any]] = []
        for raw in attachments:
            if not isinstance(raw, dict):
                continue
            item, model_file = self.read(
                raw, allow_model_images=allow_model_images
            )
            manifest.append(item)
            if model_file:
                model_files.append(model_file)
        return manifest, model_files

    def read(
        self, attachment: dict[str, Any], *, allow_model_images: bool
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        raw_path = str(attachment.get("file_path") or "").strip()
        supplied_name = str(
            attachment.get("file_name")
            or attachment.get("filename")
            or ""
        ).strip()
        path = Path(raw_path).expanduser() if raw_path else None
        name = supplied_name or (path.name if path else "unnamed")
        suffix = (path.suffix if path else Path(name).suffix).casefold()
        mime = str(
            attachment.get("mime_type")
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream"
        )
        exists = bool(path and path.is_file())
        result: dict[str, Any] = {
            "attachmentId": attachment.get("id"),
            "name": name,
            "type": mime,
            "size": attachment.get("file_size"),
            "exists": exists,
            "reader": "metadata_only",
            "textExcerpt": "",
            "redactions": [],
            "sha256": None,
            "modelIncluded": False,
            "warning": None,
        }
        if not exists or path is None:
            result["warning"] = "attachment_file_missing"
            return result, None
        try:
            result["size"] = path.stat().st_size
            result["sha256"] = self._sha256(path)
            if suffix in TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                result["reader"] = "plain_text"
                self._set_excerpt(result, text)
            elif suffix == ".docx":
                result["reader"] = "docx"
                self._set_excerpt(result, self._read_docx(path))
            elif suffix == ".pdf":
                result["reader"] = "pdf"
                pdf_text = self._read_pdf(path)
                self._set_excerpt(result, pdf_text)
                if not pdf_text and allow_model_images:
                    result["reader"] = "model_document"
                    result["modelIncluded"] = True
                    return result, {
                        "path": str(path),
                        "filename": name,
                        "mime": "application/pdf",
                        "source": "todo_attachment",
                    }
                if not pdf_text:
                    result["warning"] = "pdf_reader_unavailable"
            elif suffix in IMAGE_SUFFIXES:
                result["reader"] = "vision_attachment"
                if allow_model_images:
                    result["modelIncluded"] = True
                    return result, {
                        "path": str(path),
                        "filename": name,
                        "mime": mime,
                        "source": "todo_attachment",
                    }
                result["warning"] = "image_requires_cloud_consent"
            else:
                result["warning"] = "unsupported_attachment_type"
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            result["warning"] = f"attachment_read_failed:{type(error).__name__}"
        return result, None

    def _set_excerpt(self, result: dict[str, Any], text: str) -> None:
        cleaned, redactions = redact_text(text)
        result["textExcerpt"] = cleaned[: self.max_chars_per_file]
        result["redactions"] = sorted(set(redactions))
        if len(cleaned) > self.max_chars_per_file:
            result["warning"] = "text_excerpt_truncated"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _read_docx(path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("word/document.xml")
        root = ElementTree.fromstring(raw)
        return "\n".join(
            value.strip()
            for value in root.itertext()
            if value and value.strip()
        )

    @staticmethod
    def _read_pdf(path: Path) -> str:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            return ""
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)


def build_evidence_manifest(
    evidence_sets: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a provenance-safe manifest and a measurable evidence coverage score."""

    trajectory_by_task = {
        str(item.get("taskId")): item for item in trajectories
    }
    task_manifests: list[dict[str, Any]] = []
    scores: list[int] = []
    optional_checks = {
        "observerContext",
        "ocrText",
        "screenshots",
        "attachments",
        "readableFiles",
        "journalContext",
        "executionHistory",
        "toolCalls",
        "userCorrections",
        "capturedTrajectory",
        "sourceContent",
        "outputEvidence",
        "toolTrace",
        "contextEvidence",
    }
    totals = {
        "tasks": len(evidence_sets),
        "observerEvents": 0,
        "ocrCharacters": 0,
        "screenshots": 0,
        "attachments": 0,
        "readableFiles": 0,
        "journals": 0,
        "skillRuns": 0,
        "toolCalls": 0,
        "userCorrections": 0,
        "redactions": 0,
        "privacySkipped": 0,
    }
    for assembled in evidence_sets:
        task_id = str(assembled["task_id"])
        todo = assembled.get("todo") or {}
        trajectory = trajectory_by_task.get(task_id) or {}
        events = assembled.get("observer_events") or []
        files = assembled.get("attachment_evidence") or []
        journals = assembled.get("linked_journals") or []
        execution_history = assembled.get("execution_history") or []
        tool_calls = [
            step
            for run in execution_history
            for step in (run.get("plan") or {}).get("steps") or []
        ]
        corrections = [
            correction
            for run in execution_history
            for feedback in run.get("feedback") or []
            for correction in feedback.get("corrections") or []
        ]
        screenshots = [
            artifact
            for event in events
            for artifact in event.get("artifacts") or []
            if artifact.get("kind") == "screenshot"
            and artifact.get("exists", True) is not False
            and (
                artifact.get("path")
                or artifact.get("fileId")
                or artifact.get("modelIncluded")
            )
        ]
        ocr_characters = sum(
            len(str((event.get("content") or {}).get("clean_text") or ""))
            for event in events
        )
        readable_files = [
            item
            for item in files
            if item.get("textExcerpt") or item.get("modelIncluded")
        ]
        trajectory_inputs = trajectory.get("inputs") or {}
        trajectory_outputs = trajectory.get("outputs") or []
        trajectory_steps = trajectory.get("steps") or []
        task_type = str(
            (trajectory.get("metadata") or {}).get("taskType") or "unknown"
        )
        weights = EVIDENCE_PROFILES.get(
            task_type, EVIDENCE_PROFILES["unknown"]
        )
        source_content = bool(
            str(
                trajectory_inputs.get("sourceText")
                or trajectory_inputs.get("content")
                or ""
            ).strip()
            or readable_files
            or ocr_characters
        )
        captured_trajectory = str(
            trajectory.get("sourceQuality") or ""
        ).startswith("captured")
        workflow_trace = bool(
            captured_trajectory
            or execution_history
            or (
                events
                and (
                    screenshots
                    or ocr_characters > 0
                )
            )
        )
        output_evidence = bool(
            [
                item
                for item in trajectory_outputs
                if isinstance(item, dict)
                and any(
                    value not in (None, "", [], {})
                    for key, value in item.items()
                    if key not in {"type", "runId"}
                )
            ]
            or str(todo.get("user_notes") or "").strip()
        )
        tool_trace = bool(
            [
                step
                for step in trajectory_steps
                if str(step.get("tool") or "").strip()
                not in {"", "unknown"}
            ]
            or tool_calls
        )
        context_evidence = bool(
            events
            or (trajectory.get("contextApps") or [])
            or journals
        )
        checks = {
            "title": bool(str(todo.get("name") or "").strip()),
            "summary": bool(
                str(
                    todo.get("user_notes")
                    or todo.get("description")
                    or todo.get("summary")
                    or ""
                ).strip()
            ),
            "timing": bool(
                todo.get("completed_at") or todo.get("updated_at")
            ),
            "capturedTrajectory": captured_trajectory,
            "workflowTrace": workflow_trace,
            "successSignals": bool(trajectory.get("successSignals")),
            "sourceContent": source_content,
            "outputEvidence": output_evidence,
            "toolTrace": tool_trace,
            "contextEvidence": context_evidence,
            "observerContext": bool(events),
            "ocrText": ocr_characters > 0,
            "screenshots": bool(screenshots),
            "attachments": bool(
                [
                    item
                    for item in files
                    if item.get("exists", True) is not False
                ]
            ),
            "readableFiles": bool(readable_files),
            "journalContext": bool(journals),
            "executionHistory": bool(execution_history),
            "toolCalls": bool(tool_calls),
            "userCorrections": bool(corrections),
        }
        score = sum(
            weight for name, weight in weights.items() if checks.get(name)
        )
        scores.append(score)
        redactions = sum(
            len(event.get("redactions") or []) for event in events
        ) + sum(
            len(item.get("redactions") or []) for item in files
        ) + sum(
            len(item.get("redactions") or []) for item in journals
        ) + sum(
            len(item.get("redactions") or [])
            + sum(
                len(feedback.get("redactions") or [])
                for feedback in item.get("feedback") or []
            )
            for item in execution_history
        )
        privacy_skipped = int(assembled.get("privacy_skipped") or 0)
        missing_required = [
            name for name in weights if not checks.get(name, False)
        ]
        missing_optional = sorted(
            name
            for name in optional_checks
            if name not in weights and not checks.get(name, False)
        )
        task_manifests.append(
            {
                "taskId": task_id,
                "freetodoTodoId": assembled["freetodo_todo_id"],
                "title": str(todo.get("name") or ""),
                "taskType": task_type,
                "evidenceProfile": dict(weights),
                "coverage": score,
                "checks": checks,
                "observerEventCount": len(events),
                "ocrCharacterCount": ocr_characters,
                "screenshots": screenshots,
                "attachments": files,
                "journals": journals,
                "executionHistory": execution_history,
                "taskEvidenceRefs": trajectory.get("evidenceRefs") or [],
                "privacySkipped": privacy_skipped,
                "redactions": redactions,
                "missingEvidence": missing_required,
                "missingOptionalEvidence": missing_optional,
            }
        )
        totals["observerEvents"] += len(events)
        totals["ocrCharacters"] += ocr_characters
        totals["screenshots"] += len(screenshots)
        totals["attachments"] += len(files)
        totals["readableFiles"] += len(readable_files)
        totals["journals"] += len(journals)
        totals["skillRuns"] += len(execution_history)
        totals["toolCalls"] += len(tool_calls)
        totals["userCorrections"] += len(corrections)
        totals["redactions"] += redactions
        totals["privacySkipped"] += privacy_skipped
    coverage = round(sum(scores) / len(scores)) if scores else 0
    missing = sorted(
        {
            name
            for task in task_manifests
            for name in task["missingEvidence"]
        }
    )
    complete = bool(task_manifests) and all(
        not task["missingEvidence"] for task in task_manifests
    )
    completeness = {
        "percentage": coverage,
        "complete": complete,
        "basis": (
            "Every task satisfies the reproducibility evidence profile for its task type"
        ),
        "requiredChecks": sorted(
            {
                name
                for task in task_manifests
                for name in task["evidenceProfile"]
            }
        ),
        "profilesByTask": {
            task["taskId"]: task["evidenceProfile"]
            for task in task_manifests
        },
        "missingByTask": {
            task["taskId"]: task["missingEvidence"]
            for task in task_manifests
            if task["missingEvidence"]
        },
        "optionalChecks": sorted(optional_checks),
        "missingOptionalByTask": {
            task["taskId"]: task["missingOptionalEvidence"]
            for task in task_manifests
            if task["missingOptionalEvidence"]
        },
    }
    return {
        "coverage": coverage,
        "complete": complete,
        "completeness": completeness,
        "qualityBand": (
            "rich" if coverage >= 85 else "usable" if coverage >= 60 else "sparse"
        ),
        "totals": totals,
        "missingEvidence": missing,
        "tasks": task_manifests,
        "privacy": {
            "rawScreenshotsRequirePerEventUploadPermission": True,
            "textIsLocallyRedacted": True,
        },
    }


def prompt_evidence_pack(
    evidence_sets: list[dict[str, Any]],
    trajectories: list[dict[str, Any]],
    *,
    max_chars: int,
) -> dict[str, Any]:
    """Build the bounded model input without local paths or private helper fields."""

    trajectory_by_task = {
        str(item.get("taskId")): item for item in trajectories
    }
    tasks: list[dict[str, Any]] = []
    remaining = max(4000, int(max_chars))

    def bounded(value: Any, limit: int) -> str:
        nonlocal remaining
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        size = min(limit, remaining)
        result = text[:size]
        remaining -= len(result)
        return result

    def safe_structure(value: Any, depth: int = 0) -> Any:
        if depth > 5 or remaining <= 0:
            return None
        if isinstance(value, dict):
            return {
                str(key): safe_structure(item, depth + 1)
                for key, item in list(value.items())[:50]
                if str(key).casefold()
                not in {
                    "path",
                    "localpath",
                    "absolutepath",
                    "screenshotpath",
                    "_model_files",
                }
            }
        if isinstance(value, list):
            return [
                safe_structure(item, depth + 1) for item in value[:50]
            ]
        if isinstance(value, str):
            return bounded(value, 1600)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return bounded(value, 400)

    for assembled in evidence_sets:
        if remaining <= 0:
            break
        todo = assembled.get("todo") or {}
        task_id = str(assembled["task_id"])
        events = []
        for event in assembled.get("observer_events") or []:
            content = event.get("content") or {}
            app = event.get("app") or {}
            events.append(
                {
                    "eventId": event.get("event_id"),
                    "at": event.get("created_at"),
                    "app": bounded(app.get("name"), 100),
                    "window": bounded(app.get("window_title"), 240),
                    "ocr": bounded(content.get("clean_text"), 4000),
                    "artifacts": [
                        {
                            "kind": artifact.get("kind"),
                            "exists": artifact.get("exists"),
                            "modelIncluded": artifact.get("modelIncluded"),
                            "source": artifact.get("source"),
                        }
                        for artifact in (event.get("artifacts") or [])[:20]
                        if isinstance(artifact, dict)
                    ],
                }
            )
        files = [
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "reader": item.get("reader"),
                "text": bounded(item.get("textExcerpt"), 8000),
                "warning": item.get("warning"),
            }
            for item in assembled.get("attachment_evidence") or []
        ]
        journals = [
            {
                "date": item.get("date"),
                "name": bounded(item.get("name"), 300),
                "objective": bounded(item.get("objective"), 1200),
                "summary": bounded(item.get("summary"), 4000),
                "userNotes": bounded(item.get("userNotes"), 2000),
                "tags": safe_structure(item.get("tags") or []),
            }
            for item in assembled.get("linked_journals") or []
        ]
        execution_history = [
            {
                "runId": item.get("runId"),
                "status": item.get("status"),
                "plan": safe_structure(item.get("plan") or {}),
                "result": {
                    "status": (item.get("result") or {}).get("status"),
                    "summary": bounded(
                        (item.get("result") or {}).get("summary"), 4000
                    ),
                    "completedBySkill": (item.get("result") or {}).get(
                        "completedBySkill"
                    ),
                },
                "feedback": [
                    {
                        "rating": feedback.get("rating"),
                        "outcome": feedback.get("outcome"),
                        "comment": bounded(feedback.get("comment"), 1200),
                        "corrections": safe_structure(
                            feedback.get("corrections") or []
                        ),
                    }
                    for feedback in item.get("feedback") or []
                ],
            }
            for item in assembled.get("execution_history") or []
        ]
        tasks.append(
            {
                "taskId": task_id,
                "title": bounded(todo.get("name"), 300),
                "goal": bounded(
                    todo.get("summary") or todo.get("description"), 1500
                ),
                "userNotes": bounded(todo.get("user_notes"), 2000),
                "startedAt": todo.get("start_time") or todo.get("created_at"),
                "completedAt": todo.get("completed_at") or todo.get("updated_at"),
                "trajectory": safe_structure(
                    trajectory_by_task.get(task_id)
                ),
                "observerEvents": events,
                "files": files,
                "journals": journals,
                "executionHistory": execution_history,
                "analyses": safe_structure(
                    assembled.get("task_analyses") or []
                ),
            }
        )
    return {"tasks": tasks, "truncated": remaining <= 0}
