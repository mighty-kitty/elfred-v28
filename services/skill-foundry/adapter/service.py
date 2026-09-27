from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from adapter.config import Settings
from adapter.harness import build_codex_client
from adapter.contracts import SyncResult, normalize_event_payload, payload_hash
from adapter.freetodo_client import FreeTodoClient, FreeTodoError, FreeTodoNotFound
from adapter.hardware_output import HardwareOutputService
from adapter.privacy import decide, safe_event_view
from adapter.skill_foundry import SkillFoundryService
from adapter.journal.generator import JournalGenerator
from adapter.journal.images import JournalImageLoader
from adapter.journal.coordinator import JournalCoordinator
from adapter.journal.service import JournalService
from adapter.storage import SQLiteStore
from adapter.task_analyzer import (
    CodexTaskAnalyzer,
    TaskAnalysisError,
    TaskAnalyzer,
    is_private_communication_event,
    is_task_analysis_candidate,
    local_observer_tasks,
)
from adapter.task_reconciler import (
    freetodo_payload,
    project_task_candidates,
    reconcile_task_observation,
    select_task_candidates,
)
from adapter.topics import TopicRegistry
from adapter.transform import extract_tasks, weekly_digest


ANALYSIS_PROMPT_VERSION = "context-analysis-v2"
ANALYSIS_SCHEMA_VERSION = "2.0"
_PREVIOUS_PRODUCT = bytes.fromhex("616c66726564").decode("ascii")
_PREVIOUS_PRODUCT_PATTERN = re.compile(
    re.escape(_PREVIOUS_PRODUCT),
    re.IGNORECASE,
)


class AdapterService:
    def __init__(
        self,
        settings: Settings,
        client: FreeTodoClient | None = None,
        task_analyzer: TaskAnalyzer | None = None,
    ) -> None:
        self.settings = settings
        self.store = SQLiteStore(settings.db_path)
        self.client = client or FreeTodoClient(settings.freetodo_base_url, settings.request_timeout_seconds)
        self.topics = TopicRegistry(self.store)
        self.harness = build_codex_client(settings)
        self.task_analyzer = task_analyzer or self._build_task_analyzer()
        self.skill_foundry = SkillFoundryService(
            settings, self.store, self.client, harness_client=self.harness
        )
        self.hardware_output = HardwareOutputService(
            settings,
            self.store,
            self.client,
        )
        self.journal = self._build_journal_service()
        self.journal_coordinator = JournalCoordinator(
            self.journal,
            self.store,
            self.client,
            max_events=self.settings.journal_max_events,
            max_attempts=self.settings.journal_max_attempts,
            retry_base_seconds=self.settings.journal_retry_base_seconds,
            lease_seconds=self.settings.journal_lease_seconds,
            on_published=(
                self._plan_generated_journal
                if self.settings.hardware_output_enabled
                and self.settings.hardware_output_auto_plan_on_journal
                else None
            ),
        )
        self._legacy_task_adoption_done = False

    def _build_task_analyzer(self) -> TaskAnalyzer | None:
        provider = self.settings.llm_provider.casefold().strip()
        if provider in {"", "deterministic", "disabled", "none"}:
            return None
        if provider not in {"codex", "hermes"}:
            raise ValueError(
                f"Unsupported ELFRED_LLM_PROVIDER: {self.settings.llm_provider}"
            )
        if not self.settings.llm_model_id:
            raise ValueError("ELFRED_LLM_MODEL is required for Codex")
        return CodexTaskAnalyzer(
            base_url="",
            api_key="",
            provider_id=self.settings.llm_provider_id,
            model_id=self.settings.llm_model_id,
            reasoning_effort=self.settings.llm_reasoning_effort,
            client=self.harness,
        )

    def _build_journal_service(self) -> JournalService:
        """创建日报服务——只在 journal_enabled 且 LLM provider 配置时启用"""
        generator: JournalGenerator | None = None
        image_loader: JournalImageLoader | None = None
        provider = self.settings.llm_provider.casefold().strip()
        if self.settings.journal_enabled and provider not in {
            "",
            "deterministic",
            "disabled",
            "none",
        }:
            generator = JournalGenerator(
                base_url="",
                api_key="",
                provider_id=self.settings.llm_provider_id,
                model_id=self.settings.llm_model_id,
                reasoning_effort=self.settings.llm_reasoning_effort,
                timeout_seconds=self.settings.llm_timeout_seconds,
                vision_provider_id=self.settings.journal_vision_provider_id,
                vision_model_id=self.settings.journal_vision_model_id,
                client=self.harness,
            )
            if (
                self.settings.llm_cloud_consent
                and self.settings.journal_vision_model_id.strip()
            ):
                image_loader = JournalImageLoader(
                    self.settings.observer_base_url,
                    max_images=self.settings.journal_max_model_images,
                    max_image_bytes=self.settings.journal_max_image_bytes,
                    timeout_seconds=self.settings.request_timeout_seconds,
                )
        return JournalService(generator, image_loader)

    def _plan_generated_journal(self, response: Any) -> None:
        """Create a reviewable plan without executing hardware actions."""

        if response.payload is None:
            return
        self.hardware_output.create_plan_from_generated(
            response.payload,
            planning_mode="auto",
        )

    def process_payload(self, payload: dict[str, Any]) -> SyncResult:
        envelope, canonical, digest = normalize_event_payload(payload)
        event_id = envelope.event.event_id
        disposition = self.store.ingest_event(canonical, digest)
        if disposition == "duplicate":
            links = self.store.remote_links(event_id)
            return SyncResult(
                event_id=event_id,
                status="duplicate",
                payload_hash=digest,
                todo_ids=[x["freetodo_todo_id"] for x in links["todo"] if x.get("freetodo_todo_id")],
                journal_ids=[x["freetodo_journal_id"] for x in links["journal"] if x.get("freetodo_journal_id")],
                activity_state=links["activity"][0]["status"] if links["activity"] else None,
            )
        if disposition == "conflict":
            return SyncResult(event_id=event_id, status="conflict", payload_hash=digest)
        return self._sync_event(canonical, digest, job_type="ingest")

    def enqueue_payload(
        self,
        payload: dict[str, Any],
        *,
        force_analysis: bool = False,
    ) -> SyncResult:
        """Persist an event quickly and queue semantic work for the background worker."""

        if self.task_analyzer is None:
            _, preview, _ = normalize_event_payload(payload)
            preview_event = preview["event"]
            preview_decision = decide(preview_event)
            preview_safe_event, _ = safe_event_view(preview_event)
            has_local_private_tasks = (
                preview_decision.local_allowed
                and is_private_communication_event(preview_safe_event)
                and bool(local_observer_tasks(preview_safe_event))
            )
            if not has_local_private_tasks:
                return self.process_payload(payload)

        envelope, canonical, digest = normalize_event_payload(payload)
        event = canonical["event"]
        event_id = envelope.event.event_id
        disposition = self.store.ingest_event(canonical, digest)
        if disposition == "conflict":
            return SyncResult(event_id=event_id, status="conflict", payload_hash=digest)

        decision = decide(event)
        provider = self.settings.llm_provider_id
        model = self.settings.llm_model_id
        if not decision.local_allowed:
            detail = {
                "status": "skipped_privacy",
                "provider": provider,
                "model": model,
                "task_count": 0,
                "reason": decision.reason,
                "schema_version": ANALYSIS_SCHEMA_VERSION,
            }
            self.store.record_privacy(
                event_id, False, False, decision.reason, decision.redactions
            )
            self.store.upsert_task_analysis(
                event_id,
                "skipped_privacy",
                provider,
                model,
                digest,
                False,
                detail,
                prompt_version=ANALYSIS_PROMPT_VERSION,
                schema_version=ANALYSIS_SCHEMA_VERSION,
            )
            self.store.set_event_status(event_id, "privacy_blocked")
            return SyncResult(
                event_id=event_id,
                status="privacy_blocked",
                payload_hash=digest,
                warnings=[decision.reason],
            )

        safe_event, redactions = safe_event_view(event)
        effective_cloud_consent = (
            decision.cloud_allowed or self.settings.llm_cloud_consent
        ) and self._cloud_task_analysis_allowed_for_app(safe_event)
        private_communication = is_private_communication_event(safe_event)
        local_projection = (
            private_communication
            and bool(local_observer_tasks(safe_event))
            and (not effective_cloud_consent or self.task_analyzer is None)
        )
        analysis_cloud_consent = effective_cloud_consent and not local_projection
        self.store.record_privacy(
            event_id,
            True,
            analysis_cloud_consent,
            decision.reason,
            redactions,
        )
        source_hash = self._analysis_source_hash(safe_event)
        if not effective_cloud_consent and not local_projection:
            detail = {
                "status": "skipped_no_cloud_consent",
                "provider": provider,
                "model": model,
                "task_count": 0,
                "schema_version": ANALYSIS_SCHEMA_VERSION,
            }
            self.store.upsert_task_analysis(
                event_id,
                "skipped_no_cloud_consent",
                provider,
                model,
                source_hash,
                False,
                detail,
                prompt_version=ANALYSIS_PROMPT_VERSION,
                schema_version=ANALYSIS_SCHEMA_VERSION,
            )
            self.store.set_event_status(event_id, "synced")
            return SyncResult(
                event_id=event_id,
                status="skipped_no_cloud_consent",
                payload_hash=digest,
                warnings=["llm_analysis_skipped_no_cloud_consent"],
            )

        model_candidate = is_task_analysis_candidate(safe_event) or (
            private_communication and analysis_cloud_consent
        )
        if not local_projection and not model_candidate:
            has_text = bool(str((safe_event.get("content") or {}).get("clean_text") or "").strip())
            status = "skipped_not_task_candidate" if has_text else "skipped_empty"
            detail = {
                "status": status,
                "provider": provider,
                "model": model,
                "task_count": 0,
                "schema_version": ANALYSIS_SCHEMA_VERSION,
            }
            self.store.upsert_task_analysis(
                event_id,
                status,
                provider,
                model,
                source_hash,
                True,
                detail,
                prompt_version=ANALYSIS_PROMPT_VERSION,
                schema_version=ANALYSIS_SCHEMA_VERSION,
            )
            self.store.set_event_status(event_id, "synced")
            return SyncResult(event_id=event_id, status=status, payload_hash=digest)

        queued = self.store.enqueue_task_analysis(
            event_id,
            "observer_local" if local_projection else provider,
            "deterministic" if local_projection else model,
            source_hash,
            analysis_cloud_consent,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            schema_version=ANALYSIS_SCHEMA_VERSION,
            force=force_analysis,
        )
        if queued:
            self.store.set_event_status(event_id, "analysis_pending")
            status = "analysis_pending"
        else:
            current = self.store.task_analysis(event_id) or {}
            status = "duplicate" if disposition == "duplicate" else str(current.get("status") or "duplicate")
        return SyncResult(event_id=event_id, status=status, payload_hash=digest)

    @staticmethod
    def _analysis_source_hash(event: dict[str, Any]) -> str:
        content = event.get("content") or {}
        return payload_hash(
            {
                "event_id": event.get("event_id"),
                "created_at": event.get("created_at"),
                "app": event.get("app"),
                "content_type": content.get("content_type"),
                "text": content.get("clean_text"),
                "prompt_version": ANALYSIS_PROMPT_VERSION,
            }
        )

    def process_analysis_batch(self, claimed_batch: list[dict[str, Any]]) -> None:
        """批量分析：复用 LLM 会话处理多个事件，减少握手开销"""
        _blog = logging.getLogger("elfred.analysis_batch")

        # (claimed_dict, safe_event, candidates)
        prepped: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
        for claimed in claimed_batch:
            event_id = str(claimed["event_id"])
            existing_analysis = claimed.get("analysis") or {}
            pending_ids = [
                str(item)
                for item in existing_analysis.get("pending_task_ids") or []
                if str(item).strip()
            ]
            if existing_analysis.get("publish_pending") and pending_ids:
                try:
                    self._resume_task_publication(
                        event_id, existing_analysis, pending_ids
                    )
                except Exception as error:
                    self._schedule_analysis_failure(claimed, error)
                continue
            record = self.store.get_event(event_id)
            if record is None:
                self.store.fail_task_analysis(event_id, "source event missing", retryable=False)
                continue
            event = record["payload"]["event"]
            # 隐私检查
            decision = decide(event)
            if not decision.local_allowed:
                self.store.complete_task_analysis(event_id, {"status": "skipped_privacy", "reason": str(decision.reason)}, status="skipped_privacy")
                self.store.set_event_status(event_id, "privacy_blocked")
                continue
            safe_event, _ = safe_event_view(event)
            if not bool(claimed.get("cloud_consent")):
                self.store.complete_task_analysis(event_id, {"status": "skipped_no_cloud_consent"}, status="skipped_no_cloud_consent")
                self.store.set_event_status(event_id, "synced")
                continue
            if existing_analysis.get("reconcile_pending"):
                try:
                    self._reconcile_and_publish_analysis(
                        event_id, safe_event, existing_analysis
                    )
                except Exception as error:
                    self._schedule_analysis_failure(claimed, error)
                continue
            if not is_task_analysis_candidate(safe_event):
                self.store.complete_task_analysis(event_id, {"status": "skipped_empty"}, status="skipped_empty")
                self.store.set_event_status(event_id, "synced")
                continue
            if self.task_analyzer is None:
                self.store.fail_task_analysis(event_id, "no task analyzer configured", retryable=False)
                continue
            all_candidates = self.store.canonical_task_candidates(1000)
            candidates = select_task_candidates(
                safe_event,
                all_candidates,
                limit=self.settings.task_candidate_limit,
            )
            prepped.append((claimed, safe_event, project_task_candidates(candidates, limit=self.settings.task_candidate_limit)))

        if not prepped:
            return

        # 批量调用 LLM
        batch_args = [(safe_evt, cands) for _, safe_evt, cands in prepped]
        try:
            results = self.task_analyzer.analyze_batch(batch_args)
        except Exception as error:
            for claimed, _, _ in prepped:
                self._schedule_analysis_failure(claimed, error)
            _blog.warning("Batch analysis failed (%d events): %s", len(prepped), error)
            return

        # 保存结果
        for idx in range(min(len(prepped), len(results))):
            claimed, safe_event, _ = prepped[idx]
            analysis = results[idx]
            event_id = str(claimed["event_id"])
            try:
                detail = analysis.to_dict() | {
                    "status": "succeeded",
                    "task_count": len(analysis.tasks),
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "prompt_version": ANALYSIS_PROMPT_VERSION,
                    "reconcile_pending": True,
                }
                self.store.complete_task_analysis(
                    event_id, detail, status="publish_pending"
                )
                self._reconcile_and_publish_analysis(event_id, safe_event, detail)
            except Exception as error:
                self._schedule_analysis_failure(claimed, error)
                _blog.warning("Batch reconciliation failed for %s: %s", event_id, error)

        for claimed, _, _ in prepped[len(results) :]:
            self._schedule_analysis_failure(
                claimed,
                 TaskAnalysisError("Codex returned fewer batch results than requested"),
            )

    def process_next_analysis(self) -> dict[str, Any] | None:
        claimed = self.store.claim_task_analysis(
            lease_seconds=self.settings.analysis_lease_seconds
        )
        if claimed is None:
            return None
        event_id = str(claimed["event_id"])
        record = self.store.get_event(event_id)
        if record is None:
            self.store.fail_task_analysis(
                event_id, "source event is missing", retryable=False
            )
            return {"event_id": event_id, "status": "failed_terminal", "error": "source event is missing"}

        try:
            self._adopt_legacy_product_tasks()
            existing_analysis = claimed.get("analysis") or {}
            pending_ids = [
                str(item)
                for item in existing_analysis.get("pending_task_ids") or []
                if str(item).strip()
            ]
            if existing_analysis.get("publish_pending") and pending_ids:
                final_status, published, _ = self._resume_task_publication(
                    event_id, existing_analysis, pending_ids
                )
                return {"event_id": event_id, "status": final_status, "todo_ids": published}

            event = record["payload"]["event"]
            decision = decide(event)
            if not decision.local_allowed:
                detail = {
                    "status": "skipped_privacy",
                    "task_count": 0,
                    "reason": decision.reason,
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                }
                self.store.complete_task_analysis(event_id, detail, status="skipped_privacy")
                self.store.set_event_status(event_id, "privacy_blocked")
                return {"event_id": event_id, "status": "skipped_privacy"}

            safe_event, _ = safe_event_view(event)
            if existing_analysis.get("reconcile_pending"):
                final_status, published, detail = self._reconcile_and_publish_analysis(
                    event_id, safe_event, existing_analysis
                )
                return {
                    "event_id": event_id,
                    "status": final_status,
                    "todo_ids": published,
                    "context_kind": detail.get("context_kind"),
                    "domain": detail.get("domain"),
                }
            private_communication = is_private_communication_event(safe_event)
            observer_tasks = (
                local_observer_tasks(safe_event) if private_communication else []
            )
            use_local_tasks = bool(observer_tasks) and (
                not bool(claimed.get("cloud_consent"))
                or self.task_analyzer is None
            )
            if use_local_tasks:
                detail = {
                    "provider": "observer_local",
                    "model": "deterministic",
                    "is_task_context": True,
                    "context_kind": "task",
                    "domain": "uncategorized",
                    "summary": (
                        str((safe_event.get("content") or {}).get("summary") or "").strip()
                        or str(observer_tasks[0]["task"])
                    ),
                    "reason": "privacy-safe local Observer task evidence",
                    "tasks": observer_tasks,
                    "status": "succeeded",
                    "task_count": len(observer_tasks),
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "prompt_version": ANALYSIS_PROMPT_VERSION,
                }
            elif not bool(claimed.get("cloud_consent")):
                detail = {"status": "skipped_no_cloud_consent", "task_count": 0}
                self.store.complete_task_analysis(
                    event_id, detail, status="skipped_no_cloud_consent"
                )
                self.store.set_event_status(event_id, "synced")
                return {"event_id": event_id, "status": "skipped_no_cloud_consent"}
            elif not (
                is_task_analysis_candidate(safe_event)
                or private_communication
            ):
                has_text = bool(str((safe_event.get("content") or {}).get("clean_text") or "").strip())
                status = "skipped_not_task_candidate" if has_text else "skipped_empty"
                self.store.complete_task_analysis(event_id, {"status": status, "task_count": 0}, status=status)
                self.store.set_event_status(event_id, "synced")
                return {"event_id": event_id, "status": status}
            else:
                if self.task_analyzer is None:
                    raise TaskAnalysisError("No real task analyzer is configured")
                model_candidates = self.store.canonical_task_candidates(1000)
                candidates = select_task_candidates(
                    safe_event,
                    model_candidates,
                    limit=self.settings.task_candidate_limit,
                )
                analysis = self.task_analyzer.analyze(
                    safe_event,
                    project_task_candidates(
                        candidates, limit=self.settings.task_candidate_limit
                    ),
                )
                detail = analysis.to_dict() | {
                    "status": "succeeded",
                    "task_count": len(analysis.tasks),
                    "schema_version": ANALYSIS_SCHEMA_VERSION,
                    "prompt_version": ANALYSIS_PROMPT_VERSION,
                }
            detail["reconcile_pending"] = True
            self.store.complete_task_analysis(
                event_id, detail, status="publish_pending"
            )
            final_status, published, detail = self._reconcile_and_publish_analysis(
                event_id, safe_event, detail
            )
            return {
                "event_id": event_id,
                "status": final_status,
                "todo_ids": published,
                "context_kind": detail.get("context_kind"),
                "domain": detail.get("domain"),
            }
        except (TaskAnalysisError, FreeTodoError, OSError, ValueError) as error:
            return self._schedule_analysis_failure(claimed, error)
        except Exception as error:  # preserve the durable queue for unexpected integration errors
            return self._schedule_analysis_failure(claimed, error)

    def _resume_task_publication(
        self,
        event_id: str,
        analysis: dict[str, Any],
        pending_ids: list[str],
    ) -> tuple[str, list[int], dict[str, Any]]:
        published = self._publish_canonical_tasks(pending_ids)
        detail = dict(analysis)
        detail.update(
            publish_pending=False,
            pending_task_ids=[],
            published_todo_ids=published,
        )
        final_status = "succeeded" if detail.get("tasks") else "succeeded_no_task"
        self.store.complete_task_analysis(event_id, detail, status=final_status)
        self.store.set_event_status(event_id, "synced")
        record = self.store.get_event(event_id)
        if record is not None:
            safe_event, _ = safe_event_view(record["payload"]["event"])
            self._record_analysis_side_effects(safe_event, detail)
        return final_status, published, detail

    def _reconcile_and_publish_analysis(
        self,
        event_id: str,
        safe_event: dict[str, Any],
        analysis: dict[str, Any],
    ) -> tuple[str, list[int], dict[str, Any]]:
        detail = dict(analysis)
        all_candidates = self.store.canonical_task_candidates(1000)
        reconciliation = self._reconcile_model_tasks(
            event_id,
            safe_event,
            detail,
            all_candidates,
        )
        detail["reconciliation"] = reconciliation["decisions"]
        detail["pending_task_ids"] = reconciliation["pending_task_ids"]
        detail["publish_pending"] = bool(reconciliation["pending_task_ids"])
        detail["reconcile_pending"] = False
        published: list[int] = []
        if reconciliation["pending_task_ids"]:
            self.store.complete_task_analysis(
                event_id, detail, status="publish_pending"
            )
            published = self._publish_canonical_tasks(
                reconciliation["pending_task_ids"]
            )
            detail.update(
                published_todo_ids=published,
                pending_task_ids=[],
                publish_pending=False,
            )
        final_status = (
            "succeeded"
            if published or reconciliation["canonical_task_ids"]
            else "succeeded_no_task"
        )
        self.store.complete_task_analysis(event_id, detail, status=final_status)
        self.store.set_event_status(event_id, "synced")
        self._record_analysis_side_effects(safe_event, detail)
        return final_status, published, detail

    def _schedule_analysis_failure(
        self, claimed: dict[str, Any], error: Exception
    ) -> dict[str, Any]:
        event_id = str(claimed["event_id"])
        attempt_count = int(claimed.get("attempt_count") or 1)
        retryable = attempt_count < max(1, self.settings.analysis_max_attempts)
        next_attempt_at = None
        if retryable:
            delay = self.settings.analysis_retry_base_seconds * (2 ** max(0, attempt_count - 1))
            next_attempt_at = (
                datetime.now().astimezone() + timedelta(seconds=delay)
            ).isoformat()
        self.store.fail_task_analysis(
            event_id,
            str(error),
            retryable=retryable,
            next_attempt_at=next_attempt_at,
        )
        self.store.set_event_status(
            event_id,
            "analysis_retry" if retryable else "analysis_failed",
            str(error),
        )
        status = "failed_retryable" if retryable else "failed_terminal"
        return {"event_id": event_id, "status": status, "error": str(error)}

    def _reconcile_model_tasks(
        self,
        event_id: str,
        safe_event: dict[str, Any],
        analysis: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decisions: list[dict[str, Any]] = []
        pending_task_ids: list[str] = []
        canonical_task_ids: list[str] = []
        working_candidates = list(candidates)
        domain = str(analysis.get("domain") or "uncategorized")
        for task in analysis.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            decision = reconcile_task_observation(
                task,
                domain=domain,
                candidates=working_candidates,
                merge_threshold=self.settings.task_merge_confidence_threshold,
                publish_threshold=self.settings.active_task_threshold,
                observed_at=str(safe_event.get("created_at") or "") or None,
            )
            decision_record = {
                "action": decision.action,
                "task_id": decision.task_id,
                "reason": decision.reason,
                "observation_key": decision.observation_key,
            }
            decisions.append(decision_record)
            if decision.action == "observe":
                continue

            current = self.store.canonical_task(decision.task_id)
            if decision.action != "evidence":
                values = decision.values
                current = self.store.upsert_canonical_task(
                    decision.task_id,
                    title=values["title"],
                    description=values.get("description") or None,
                    domain=values.get("domain") or "uncategorized",
                    project=values.get("project") or None,
                    stage=values.get("stage") or "unknown",
                    progress_percent=values.get("progress_percent"),
                    priority=values.get("priority") or "none",
                    due_at=values.get("due_at"),
                    confidence=values.get("confidence") or 0.0,
                    observed_at=str(safe_event.get("created_at") or "") or None,
                )
                pending_task_ids.append(decision.task_id)
                working_candidates = [
                    item for item in working_candidates
                    if item.get("task_id") != decision.task_id
                ]
                working_candidates.insert(0, current)
            if current is None:
                continue
            canonical_task_ids.append(decision.task_id)
            self.store.upsert_task_evidence(
                decision.task_id,
                event_id,
                decision.observation_key,
                relation=str(task.get("relation") or "new"),
                confidence=float(task.get("confidence") or 0.0),
                evidence={
                    "captured_at": safe_event.get("created_at"),
                    "app": (safe_event.get("app") or {}).get("name"),
                    "summary": analysis.get("summary"),
                    "facts": task.get("evidence") or [],
                },
            )
        return {
            "decisions": decisions,
            "pending_task_ids": list(dict.fromkeys(pending_task_ids)),
            "canonical_task_ids": list(dict.fromkeys(canonical_task_ids)),
        }

    def _publish_canonical_tasks(self, task_ids: list[str]) -> list[int]:
        published: list[int] = []
        for task_id in dict.fromkeys(task_ids):
            result = self._publish_canonical_task(task_id)
            if result.get("todo_id"):
                published.append(int(result["todo_id"]))
        return published

    def _publish_canonical_task(self, task_id: str) -> dict[str, Any]:
        task = self.store.canonical_task(task_id)
        if task is None:
            raise ValueError(f"Canonical task not found: {task_id}")
        payload = freetodo_payload(task, observed_at=task.get("last_seen_at"))
        remote: dict[str, Any] | None = None
        if task.get("freetodo_todo_id"):
            try:
                remote = self.client.get_todo(int(task["freetodo_todo_id"]))
            except FreeTodoNotFound:
                remote = None
            if remote is not None and str(remote.get("uid") or "") != str(
                task["freetodo_uid"]
            ):
                self.store.audit(
                    "canonical_task_stale_remote_id",
                    task_id,
                    {
                        "freetodo_todo_id": remote.get("id"),
                        "expected_uid": task["freetodo_uid"],
                    },
                )
                remote = None
        if remote is None:
            remote = self.client.find_todo_by_uid(str(task["freetodo_uid"]))
        if remote is None:
            remote = self._find_adoptable_legacy_todo(task)
            if remote is not None:
                task = self._checkpoint_legacy_adoption(task, remote)

        if remote is not None and (task.get("metadata") or {}).get("publish_state") == "manual_modified":
            self.store.audit(
                "canonical_task_manual_modification_preserved",
                task_id,
                {"freetodo_todo_id": remote.get("id"), "source": "legacy_adoption"},
            )
            return {
                "task_id": task_id,
                "status": "manual_modified",
                "todo_id": remote.get("id"),
            }

        if remote is not None and task.get("last_remote_hash"):
            current_hash = payload_hash(self.store.remote_semantic(remote))
            # A process can die after FreeTodo accepted a PUT but before the new
            # response hash is committed locally. If the remote already equals
            # the current desired task, adopt it instead of misclassifying that
            # recovered write as a user's manual edit.
            remote_is_desired = self._remote_matches_desired(remote, payload)
            if current_hash != task["last_remote_hash"] and not remote_is_desired:
                metadata = dict(task.get("metadata") or {})
                metadata["publish_state"] = "manual_modified"
                self.store.upsert_canonical_task(
                    task_id,
                    title=task["title"],
                    description=task.get("description"),
                    domain=task.get("domain") or "uncategorized",
                    project=task.get("project"),
                    stage=task.get("stage") or "unknown",
                    progress_percent=task.get("progress_percent"),
                    priority=task.get("priority") or "none",
                    due_at=task.get("due_at"),
                    confidence=task.get("confidence") or 0.0,
                    metadata=metadata,
                )
                self.store.audit(
                    "canonical_task_manual_modification_preserved",
                    task_id,
                    {"freetodo_todo_id": remote.get("id")},
                )
                return {"task_id": task_id, "status": "manual_modified", "todo_id": remote.get("id")}

        if remote is None:
            remote = self.client.upsert_todo(str(task["freetodo_uid"]), payload)
            operation = "upsert"
        else:
            update_payload = {key: value for key, value in payload.items() if key != "uid"}
            remote = self.client.update_todo(int(remote["id"]), update_payload)
            operation = "update"
        metadata = dict(task.get("metadata") or {})
        metadata["publish_state"] = "synced"
        self.store.upsert_canonical_task(
            task_id,
            title=task["title"],
            description=task.get("description"),
            domain=task.get("domain") or "uncategorized",
            project=task.get("project"),
            stage=task.get("stage") or "unknown",
            progress_percent=task.get("progress_percent"),
            priority=task.get("priority") or "none",
            due_at=task.get("due_at"),
            confidence=task.get("confidence") or 0.0,
            freetodo_todo_id=int(remote["id"]),
            freetodo_uid=str(remote.get("uid") or task["freetodo_uid"]),
            last_remote=remote,
            metadata=metadata,
        )
        self.store.audit(
            "canonical_task_published",
            task_id,
            {"operation": operation, "freetodo_todo_id": remote.get("id")},
        )
        return {"task_id": task_id, "status": "synced", "todo_id": remote.get("id")}

    def repair_task_projections(self, limit: int = 200) -> dict[str, Any]:
        """Repair canonical tasks whose FreeTodo projection is missing or stale."""

        repaired: list[int] = []
        failed: list[dict[str, str]] = []
        for task in self.store.canonical_task_candidates(
            max(1, min(1000, limit)), include_archived=False
        ):
            task_id = str(task.get("task_id") or "")
            if not task_id:
                continue
            try:
                result = self._publish_canonical_task(task_id)
                if result.get("todo_id"):
                    repaired.append(int(result["todo_id"]))
            except Exception as error:
                failed.append({"task_id": task_id, "error": str(error)})
        self.store.audit(
            "canonical_task_projection_repair",
            "startup",
            {"repaired": len(repaired), "failed": len(failed)},
        )
        return {"repaired_todo_ids": repaired, "failures": failed}

    @staticmethod
    def _task_title_key(value: Any) -> str:
        normalized = _PREVIOUS_PRODUCT_PATTERN.sub(
            "Elfred",
            str(value or ""),
        )
        return " ".join(normalized.split()).casefold()

    @staticmethod
    def _legacy_domain(remote: dict[str, Any]) -> str:
        tags = remote.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        labels = " ".join(
            [str(remote.get("categories") or ""), *(str(item) for item in tags)]
        )
        if "工作项目" in labels:
            return "work"
        if "个人生活" in labels:
            return "life"
        if "学习提升" in labels:
            return "learning"
        return "uncategorized"

    @staticmethod
    def _legacy_stage(remote: dict[str, Any]) -> tuple[str, int]:
        status = str(remote.get("status") or "").casefold()
        try:
            progress = max(0, min(100, int(remote.get("percent_complete") or 0)))
        except (TypeError, ValueError):
            progress = 0
        if status == "completed":
            return "completed", 100
        if status in {"cancelled", "canceled"}:
            return "cancelled", progress
        if progress > 0:
            return "in_progress", min(99, progress)
        return "not_started", 0

    @staticmethod
    def _is_legacy_product_todo(remote: dict[str, Any]) -> bool:
        uid = str(remote.get("uid") or "")
        notes = str(remote.get("user_notes") or "")
        prefixes = ("elfred-", f"{_PREVIOUS_PRODUCT}-")
        canonical_prefixes = (
            "elfred-task-",
            f"{_PREVIOUS_PRODUCT}-task-",
        )
        source_markers = (
            "[ELFRED_SOURCE ",
            f"[{_PREVIOUS_PRODUCT.upper()}_SOURCE ",
        )
        return (
            uid.startswith(prefixes)
            and not uid.startswith(canonical_prefixes)
            and notes.startswith(source_markers)
            and bool(str(remote.get("name") or "").strip())
        )

    def _legacy_remote_was_manually_modified(self, remote: dict[str, Any]) -> bool:
        remote_id = remote.get("id")
        if remote_id is None:
            return False
        link = self.store.todo_link_by_remote_id(int(remote_id))
        if not link or not link.get("last_remote_hash"):
            return False
        return (
            payload_hash(self.store.remote_semantic(remote))
            != link["last_remote_hash"]
        )

    def _checkpoint_legacy_adoption(
        self, task: dict[str, Any], remote: dict[str, Any]
    ) -> dict[str, Any]:
        metadata = dict(task.get("metadata") or {})
        metadata["migrated_from"] = "legacy_product_todo"
        metadata["publish_state"] = (
            "manual_modified"
            if self._legacy_remote_was_manually_modified(remote)
            else "synced"
        )
        return self.store.upsert_canonical_task(
            str(task["task_id"]),
            title=str(task["title"]),
            description=task.get("description"),
            domain=task.get("domain") or "uncategorized",
            project=task.get("project"),
            stage=task.get("stage") or "unknown",
            progress_percent=task.get("progress_percent"),
            priority=task.get("priority") or "none",
            due_at=task.get("due_at"),
            confidence=task.get("confidence") or 0.0,
            freetodo_todo_id=int(remote["id"]),
            freetodo_uid=str(remote.get("uid") or task["freetodo_uid"]),
            last_remote=remote,
            metadata=metadata,
        )

    def _find_adoptable_legacy_todo(
        self, task: dict[str, Any]
    ) -> dict[str, Any] | None:
        title_key = self._task_title_key(task.get("title"))
        assigned_ids = {
            int(item["freetodo_todo_id"])
            for item in self.store.canonical_task_candidates(
                1000, include_archived=True
            )
            if item.get("task_id") != task.get("task_id")
            and item.get("freetodo_todo_id") is not None
        }
        for remote in self.client.list_todos():
            if not self._is_legacy_product_todo(remote):
                continue
            if remote.get("id") is None or int(remote["id"]) in assigned_ids:
                continue
            if self._task_title_key(remote.get("name")) == title_key:
                return remote
        return None

    def _adopt_legacy_product_tasks(self) -> int:
        if self._legacy_task_adoption_done:
            return 0
        existing = self.store.canonical_task_candidates(1000, include_archived=True)
        assigned_ids = {
            int(item["freetodo_todo_id"])
            for item in existing
            if item.get("freetodo_todo_id") is not None
        }
        existing_title_keys = {
            self._task_title_key(item.get("title")) for item in existing
        }
        adopted = 0
        for remote in self.client.list_todos():
            if not self._is_legacy_product_todo(remote) or remote.get("id") is None:
                continue
            if int(remote["id"]) in assigned_ids:
                continue
            title = " ".join(str(remote.get("name") or "").split())
            title_key = self._task_title_key(title)
            if not title_key or title_key in existing_title_keys:
                continue
            domain = self._legacy_domain(remote)
            stage, progress = self._legacy_stage(remote)
            task_id = "task_" + payload_hash([title_key, "", domain])[:24]
            metadata = {
                "migrated_from": "legacy_product_todo",
                "publish_state": (
                    "manual_modified"
                    if self._legacy_remote_was_manually_modified(remote)
                    else "synced"
                ),
            }
            self.store.upsert_canonical_task(
                task_id,
                title=title,
                description=remote.get("description"),
                domain=domain,
                stage=stage,
                progress_percent=progress,
                priority=str(remote.get("priority") or "none").casefold(),
                due_at=remote.get("due"),
                confidence=0.70,
                freetodo_todo_id=int(remote["id"]),
                freetodo_uid=str(remote.get("uid")),
                last_remote=remote,
                metadata=metadata,
                # Legacy cards predate the canonical evidence timeline. Do not
                # let their FreeTodo creation timestamp make historical
                # Observer events look stale during the first safe backfill.
                observed_at="1970-01-01T00:00:00+00:00",
            )
            assigned_ids.add(int(remote["id"]))
            existing_title_keys.add(title_key)
            adopted += 1
        self._legacy_task_adoption_done = True
        if adopted:
            self.store.audit(
                "legacy_product_tasks_adopted",
                None,
                {"count": adopted},
            )
        return adopted

    @staticmethod
    def _remote_matches_desired(
        remote: dict[str, Any], desired: dict[str, Any]
    ) -> bool:
        """Compare fields Elfred owns while tolerating server-managed fields."""

        backward_compatible_metadata = {
            "source_type",
            "source_key",
            "workflow_stage",
            "project",
            "confidence",
            "last_observed_at",
        }
        for key, expected in desired.items():
            if key == "completed_at":
                continue
            if key in backward_compatible_metadata and key not in remote:
                continue
            actual = remote.get(key)
            if key == "tags":
                actual = sorted(str(value) for value in (actual or []))
                expected = sorted(str(value) for value in (expected or []))
            if actual != expected:
                return False
        return True

    def _record_analysis_side_effects(
        self, safe_event: dict[str, Any], analysis: dict[str, Any]
    ) -> None:
        event_id = str(safe_event["event_id"])
        content = safe_event.setdefault("content", {})
        content["tasks"] = analysis.get("tasks") or []
        content["analysis_summary"] = analysis.get("summary")
        self.store.upsert_activity(
            event_id,
            {
                "event_id": event_id,
                "created_at": safe_event.get("created_at"),
                "app": safe_event.get("app"),
                "summary": analysis.get("summary"),
                "context_kind": analysis.get("context_kind"),
                "domain": analysis.get("domain"),
                "task_analysis": analysis,
            },
        )
        self._enqueue_partner_outboxes(safe_event, True)

    def retry_event(self, event_id: str) -> SyncResult:
        record = self.store.get_event(event_id)
        if not record:
            raise KeyError(event_id)
        event = record["payload"]["event"]
        safe_event, _ = safe_event_view(event)
        has_local_private_tasks = (
            decide(event).local_allowed
            and is_private_communication_event(safe_event)
            and bool(local_observer_tasks(safe_event))
        )
        if self.task_analyzer is not None or has_local_private_tasks:
            return self.enqueue_payload(record["payload"], force_analysis=True)
        return self._sync_event(record["payload"], record["payload_hash"], job_type="retry")

    def _sync_event(self, canonical: dict[str, Any], digest: str, job_type: str) -> SyncResult:
        event = canonical["event"]
        event_id = event["event_id"]
        job_id = self.store.create_job(event_id, job_type, {"payload_hash": digest})
        result = SyncResult(event_id=event_id, status="processing", payload_hash=digest, job_id=job_id)
        decision = decide(event)
        if not decision.local_allowed:
            self.store.record_privacy(event_id, False, False, decision.reason, decision.redactions)
            self.store.set_event_status(event_id, "privacy_blocked")
            self.store.finish_job(job_id, "completed", {"privacy": decision.reason, "remote_calls": 0})
            result.status = "privacy_blocked"
            result.warnings.append(decision.reason)
            return result

        safe_event, redactions = safe_event_view(event)
        self.store.record_privacy(
            event_id, True, decision.cloud_allowed, decision.reason, redactions
        )
        analysis_detail, analysis_warnings = self._apply_task_analysis(
            safe_event, job_id=job_id, source_cloud_allowed=decision.cloud_allowed
        )
        result.warnings.extend(analysis_warnings)
        topic_records = self.topics.resolve_event(safe_event)
        tasks = extract_tasks(
            safe_event, self.settings.active_task_threshold, topic_records
        )
        remote_failed = False
        remote_errors: list[str] = []
        for task in tasks:
            try:
                remote = self._sync_todo(event_id, task, job_id)
                if remote.get("id"):
                    result.todo_ids.append(int(remote["id"]))
            except FreeTodoError as error:
                remote_failed = True
                remote_errors.append(str(error))
                self.store.add_attempt(
                    job_id, "freetodo", "todo_upsert", "failed", error=str(error), request=task["payload"]
                )

        activity_detail = {
            "event_id": event_id,
            "created_at": safe_event["created_at"],
            "app": safe_event["app"],
            "summary": safe_event["content"]["summary"],
            "reason": "FreeTodo 0.1.2 has no external Event/Activity create API",
            "task_analysis": analysis_detail,
        }
        self.store.upsert_activity(event_id, activity_detail)
        result.activity_state = "local_only"

        result.outbox_ids.extend(self._enqueue_partner_outboxes(safe_event, decision.cloud_allowed))

        if not remote_failed and self.settings.journal_enabled:
            self.journal_coordinator.enqueue(
                str(safe_event["created_at"])[:10],
                trigger="event",
            )
        elif not remote_failed:
            try:
                journal, warnings = self.sync_journal_day(str(safe_event["created_at"])[:10], job_id=job_id)
                result.warnings.extend(warnings)
                if journal and journal.get("id"):
                    result.journal_ids.append(int(journal["id"]))
            except FreeTodoError as error:
                remote_failed = True
                remote_errors.append(str(error))
                self.store.add_attempt(job_id, "freetodo", "journal_upsert", "failed", error=str(error))

        if remote_failed:
            error = " | ".join(dict.fromkeys(remote_errors))
            self.store.set_event_status(event_id, "retry", error)
            self.store.finish_job(
                job_id,
                "retry",
                {
                    "errors": remote_errors,
                    "outbox_ids": result.outbox_ids,
                    "task_analysis": analysis_detail,
                },
            )
            result.status = "retry"
            result.warnings.extend(remote_errors)
        else:
            self.store.set_event_status(event_id, "synced")
            self.store.finish_job(
                job_id,
                "completed",
                {
                    "todo_ids": result.todo_ids,
                    "journal_ids": result.journal_ids,
                    "outbox_ids": result.outbox_ids,
                    "task_analysis": analysis_detail,
                },
            )
            result.status = "synced"
        return result

    def _cloud_task_analysis_allowed_for_app(
        self,
        event: dict[str, Any],
    ) -> bool:
        allowed_apps = tuple(self.settings.task_analysis_cloud_apps)
        if not allowed_apps:
            return True
        app = event.get("app") or {}
        identity = " ".join(
            [
                str(app.get("name") or ""),
                str(app.get("process_name") or ""),
                str(app.get("category") or ""),
            ]
        ).casefold()
        return any(
            allowed.casefold() in identity
            for allowed in allowed_apps
            if allowed.strip()
        )

    def _apply_task_analysis(
        self,
        event: dict[str, Any],
        *,
        job_id: str,
        source_cloud_allowed: bool,
    ) -> tuple[dict[str, Any], list[str]]:
        event_id = event["event_id"]
        content = event.get("content") or {}
        source_hash = payload_hash(
            {
                "event_id": event_id,
                "app": event.get("app"),
                "text": content.get("clean_text"),
            }
        )
        provider = self.settings.llm_provider.casefold().strip() or "deterministic"
        model = self.settings.llm_model_id if provider == "codex" else "deterministic"
        if self.task_analyzer is None:
            detail = {
                "status": "deterministic_fallback",
                "provider": "deterministic",
                "model": "deterministic",
                "task_count": len(content.get("tasks") or []),
            }
            self.store.upsert_task_analysis(
                event_id, detail["status"], detail["provider"], detail["model"],
                source_hash, False, detail
            )
            return detail, []

        effective_cloud_consent = (
            source_cloud_allowed or self.settings.llm_cloud_consent
        ) and self._cloud_task_analysis_allowed_for_app(event)
        if not effective_cloud_consent:
            content["tasks"] = []
            detail = {
                "status": "skipped_no_cloud_consent",
                "provider": provider,
                "model": model,
                "task_count": 0,
            }
            self.store.upsert_task_analysis(
                event_id, detail["status"], provider, model, source_hash, False, detail
            )
            return detail, ["llm_analysis_skipped_no_cloud_consent"]

        if not is_task_analysis_candidate(event):
            content["tasks"] = []
            detail = {
                "status": "skipped_not_task_candidate",
                "provider": provider,
                "model": model,
                "task_count": 0,
            }
            self.store.upsert_task_analysis(
                event_id, detail["status"], provider, model, source_hash, True, detail
            )
            return detail, []

        try:
            analysis = self.task_analyzer.analyze(event)
        except TaskAnalysisError as error:
            content["tasks"] = []
            detail = {
                "status": "failed",
                "provider": provider,
                "model": model,
                "task_count": 0,
            }
            self.store.upsert_task_analysis(
                event_id, detail["status"], provider, model, source_hash, True, detail, str(error)
            )
            self.store.add_attempt(
                job_id,
                "codex",
                "task_analysis",
                "failed",
                error=str(error),
                request={"event_id": event_id, "source_hash": source_hash},
            )
            return detail, [f"llm_analysis_failed: {error}"]

        content["tasks"] = analysis.tasks
        content["analysis_summary"] = analysis.summary
        detail = analysis.to_dict() | {
            "status": "succeeded",
            "task_count": len(analysis.tasks),
        }
        self.store.upsert_task_analysis(
            event_id,
            "succeeded",
            analysis.provider,
            analysis.model,
            source_hash,
            True,
            detail,
        )
        self.store.add_attempt(
            job_id,
            "codex",
            "task_analysis",
            "succeeded",
            request={"event_id": event_id, "source_hash": source_hash},
        )
        return detail, []

    def _sync_todo(self, event_id: str, task: dict[str, Any], job_id: str) -> dict[str, Any]:
        links = self.store.remote_links(event_id, "todo")["todo"]
        existing_link = next((link for link in links if link["local_key"] == task["local_key"]), None)
        remote: dict[str, Any] | None = None
        if existing_link and existing_link.get("freetodo_todo_id"):
            try:
                remote = self.client.get_todo(int(existing_link["freetodo_todo_id"]))
            except FreeTodoNotFound:
                remote = None
        if remote is None:
            remote = self.client.find_todo_by_uid(task["uid"])
        if remote is None:
            remote = self.client.create_todo(task["payload"] | {"uid": task["uid"]})
            operation = "todo_create"
        else:
            operation = "todo_reuse"
        self.store.upsert_remote_link(
            "todo", event_id, task["local_key"], int(remote["id"]), task["uid"], "synced", remote
        )
        self.store.add_attempt(job_id, "freetodo", operation, "succeeded", request=task["payload"])
        return remote

    def _enqueue_partner_outboxes(self, event: dict[str, Any], cloud_allowed: bool) -> list[str]:
        event_id = event["event_id"]
        content = event["content"]
        memory_payload = {
            "contract_version": "1.0",
            "kind": "memory_candidate",
            "candidate_id": "memory_candidate_" + payload_hash(event_id)[:20],
            "source_event_id": event_id,
            "created_at": event["created_at"],
            "title": content.get("summary") or (event.get("app") or {}).get("window_title") or "Elfred context",
            "summary": content.get("summary"),
            "detail": content.get("clean_text"),
            "topics": [item["display_name"] for item in self.store.topics_for_event(event_id)],
            "delivery_gate": "eligible" if event["privacy"].get("allowed_to_write_long_term_memory") else "confirm_required",
            "cloud_allowed": cloud_allowed,
        }
        pa_payload = {
            "contract_version": "1.0",
            "kind": "personal_agent_context",
            "context_id": "pa_context_" + payload_hash(event_id)[:20],
            "source_event_id": event_id,
            "created_at": event["created_at"],
            "app": event["app"],
            "summary": content.get("summary"),
            "tasks": content.get("tasks") or [],
            "topics": [item["display_name"] for item in self.store.topics_for_event(event_id)],
            "freshness": "current",
        }
        return [
            self.store.enqueue("memory", event_id, memory_payload),
            self.store.enqueue("personal_agent", event_id, pa_payload),
        ]

    def sync_journal_day(self, day: str, job_id: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
        from adapter.journal.models import GenerateRequest

        response = self.journal_coordinator.sync(
            GenerateRequest(
                date=day,
                max_events=self.settings.journal_max_events,
            ),
            trigger="event" if job_id else "manual",
        )
        remote = (
            self.client.get_journal(response.journal_id)
            if response.journal_id is not None
            else None
        )
        if job_id and response.payload is not None:
            self.store.add_attempt(
                job_id,
                "freetodo",
                "journal_sync",
                "succeeded" if response.journal_id else response.status,
                request={"date": day, "source": "journal_coordinator"},
            )
        return remote, response.warnings

    def _delete_empty_journal(self, links: list[dict[str, Any]]) -> dict[str, Any] | None:
        link = links[0]
        remote_id = link.get("freetodo_journal_id")
        if not remote_id:
            return None
        try:
            remote = self.client.get_journal(int(remote_id))
        except FreeTodoNotFound:
            for item in links:
                self.store.set_link_status("journal", item["link_id"], "remote_missing")
            return None
        if payload_hash(self.store.remote_semantic(remote)) == link.get("last_remote_hash"):
            self.client.delete_journal(int(remote_id))
            for item in links:
                self.store.set_link_status("journal", item["link_id"], "deleted")
            return None
        for item in links:
            self.store.set_link_status("journal", item["link_id"], "preserved_user_modified")
        return remote

    def forget_event(self, event_id: str) -> dict[str, Any]:
        record = self.store.get_event(event_id)
        if not record:
            raise KeyError(event_id)
        day = record["created_at"][:10]
        job_id = self.store.create_job(event_id, "forget")
        links = self.store.remote_links(event_id)
        deleted: list[int] = []
        preserved: list[int] = []
        errors: list[str] = []
        for link in links["todo"]:
            remote_id = link.get("freetodo_todo_id")
            if not remote_id:
                self.store.set_link_status("todo", link["link_id"], "unlinked")
                continue
            try:
                current = self.client.get_todo(int(remote_id))
                current_hash = payload_hash(self.store.remote_semantic(current))
                if current_hash == link.get("last_remote_hash"):
                    self.client.delete_todo(int(remote_id))
                    self.store.set_link_status("todo", link["link_id"], "deleted")
                    deleted.append(int(remote_id))
                else:
                    self.store.set_link_status("todo", link["link_id"], "preserved_user_modified")
                    preserved.append(int(remote_id))
            except FreeTodoNotFound:
                self.store.set_link_status("todo", link["link_id"], "remote_missing")
            except FreeTodoError as error:
                errors.append(str(error))
        for link in links["activity"]:
            self.store.set_link_status("activity", link["link_id"], "forgotten")

        self.store.soft_delete_event(event_id, "forget_pending" if errors else "forgotten")
        journal_warnings: list[str] = []
        if not errors:
            try:
                has_remaining = bool(self.store.events_for_day(day))
                if has_remaining:
                    _, journal_warnings = self.sync_journal_day(day, job_id=job_id)
                else:
                    self._delete_empty_journal(links["journal"])
                if has_remaining:
                    for link in links["journal"]:
                        if link["status"] == "synced":
                            self.store.set_link_status("journal", link["link_id"], "unlinked")
            except FreeTodoError as error:
                errors.append(str(error))
        status = "retry" if errors else "completed"
        detail = {"deleted_todo_ids": deleted, "preserved_todo_ids": preserved, "warnings": journal_warnings, "errors": errors}
        self.store.finish_job(job_id, status, detail)
        self.store.audit("event_forget", event_id, detail)
        return {"event_id": event_id, "status": status, **detail}

    def delete_event(self, event_id: str) -> dict[str, Any]:
        if not self.store.soft_delete_event(event_id, "deleted"):
            raise KeyError(event_id)
        return {"event_id": event_id, "status": "deleted", "remote_objects": "unchanged"}

    def reconcile(self, repair: bool = False) -> dict[str, Any]:
        job_id = self.store.create_job(None, "reconcile", {"repair": repair})
        counts = {"checked": 0, "missing": 0, "manual_modified": 0, "healthy": 0, "repaired": 0}
        errors: list[str] = []
        for kind in ("todo", "journal"):
            id_key = f"freetodo_{kind}_id"
            getter = self.client.get_todo if kind == "todo" else self.client.get_journal
            for link in self.store.all_links(kind):
                counts["checked"] += 1
                try:
                    remote = getter(int(link[id_key]))
                    if payload_hash(self.store.remote_semantic(remote)) != link.get("last_remote_hash"):
                        counts["manual_modified"] += 1
                        self.store.set_link_status(kind, link["link_id"], "manual_modified")
                    else:
                        counts["healthy"] += 1
                except FreeTodoNotFound:
                    counts["missing"] += 1
                    self.store.set_link_status(kind, link["link_id"], "remote_missing")
                    if repair and kind == "todo":
                        try:
                            self.retry_event(link["event_id"])
                            counts["repaired"] += 1
                        except Exception as error:  # reconciliation records and continues per object
                            errors.append(str(error))
                except FreeTodoError as error:
                    errors.append(str(error))
        status = "retry" if errors else "completed"
        self.store.finish_job(job_id, status, {"counts": counts, "errors": errors})
        return {"job_id": job_id, "status": status, "counts": counts, "errors": errors}

    def health(self) -> dict[str, Any]:
        remote: dict[str, Any]
        try:
            remote = self.client.health()
            remote_ok = remote.get("status") == "healthy"
        except FreeTodoError as error:
            remote = {"status": "unavailable", "error": str(error)}
            remote_ok = False
        store_status = self.store.status()
        harness_required = self.task_analyzer is not None or getattr(self.journal, "generator", None) is not None
        if harness_required:
            try:
                harness = self.harness.health(detailed=True)
            except Exception as error:
                harness = {"ready": False, "error": str(error)[:300]}
        else:
            status = self.harness.transport.status()
            harness = {"ready": status.ready, "pid": status.pid, "version": status.version}
        return {
            "status": "healthy" if remote_ok else "degraded",
            "adapter": "healthy",
            "freetodo": remote,
            "harness": "codex",
            "codex": harness,
            "active_backend": self.settings.active_backend,
            "llm_provider": self.settings.llm_provider,
            "task_analysis": {
                "enabled": self.task_analyzer is not None,
                "gateway": self.settings.llm_provider,
                "provider": self.settings.llm_provider_id if self.task_analyzer is not None else "deterministic",
                "model": self.settings.llm_model_id if self.task_analyzer is not None else "deterministic",
                "cloud_consent": self.settings.llm_cloud_consent,
                "cloud_allowed_apps": list(
                    self.settings.task_analysis_cloud_apps
                ),
                "sends_raw_screenshot": False,
                "input": "privacy-filtered OCR text",
            },
            "skill_foundry": {
                "generation_provider": self.settings.skill_generation_provider,
                "effective_mode": (
                    "codex"
                    if self.settings.llm_provider == "codex"
                    and self.settings.llm_cloud_consent
                    else "deterministic"
                ),
                "model": (
                    f"{self.settings.skill_model_provider_id or self.settings.llm_provider_id}/"
                    f"{self.settings.skill_model_id or self.settings.llm_model_id}"
                ),
                "vision_model": (
                    (
                        f"{self.settings.skill_vision_provider_id or self.settings.llm_provider_id}/"
                        f"{self.settings.skill_vision_model_id}"
                    )
                    if self.settings.skill_vision_model_id
                    else None
                ),
                "reads": [
                    "completed task title and summary",
                    "linked and bounded task-window Observer events",
                    "privacy-filtered OCR",
                    "FreeTodo attachments",
                    "captured trajectories",
                ],
                "raw_screenshot_policy": (
                    "requires global consent and per-event upload permission"
                ),
            },
            "analysis_worker": {
                "enabled": self.settings.analysis_worker_interval_seconds > 0,
                "interval_seconds": self.settings.analysis_worker_interval_seconds,
            },
            "analysis_queue": store_status.get("analysis_states", {}),
            "observer_auto_sync": {
                "enabled": self.settings.observer_auto_sync_interval_seconds > 0,
                "interval_seconds": self.settings.observer_auto_sync_interval_seconds,
                "backfill": self.settings.observer_auto_sync_backfill,
            },
            "journal": self.journal_coordinator.status(),
            "hardware_output": self.hardware_output.status(probe=False),
        }

    def status(self) -> dict[str, Any]:
        return self.store.status() | {
            "active_backend": self.settings.active_backend,
            "freetodo_base_url": self.settings.freetodo_base_url,
            "llm_provider": self.settings.llm_provider,
            "llm_model_provider": self.settings.llm_provider_id if self.task_analyzer is not None else "deterministic",
            "llm_model": self.settings.llm_model_id if self.task_analyzer is not None else "deterministic",
            "llm_cloud_consent": self.settings.llm_cloud_consent,
            "task_analysis_cloud_apps": list(
                self.settings.task_analysis_cloud_apps
            ),
            "analysis_worker_interval_seconds": self.settings.analysis_worker_interval_seconds,
            "journal": self.journal_coordinator.status(),
            "hardware_output": self.hardware_output.status(probe=False),
            "observer_auto_sync_interval_seconds": self.settings.observer_auto_sync_interval_seconds,
            "observer_auto_sync_backfill": self.settings.observer_auto_sync_backfill,
            "skill_generation_provider": self.settings.skill_generation_provider,
            "skill_include_screenshots": self.settings.skill_include_screenshots,
            "skill_vision_enabled": bool(
                self.settings.skill_vision_model_id
            ),
        }

    def weekly_report(self, iso_year: int, iso_week: int) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        with self.store.connect() as conn:
            rows = conn.execute("SELECT event_id FROM ingested_events WHERE deleted_at IS NULL ORDER BY created_at").fetchall()
        for row in rows:
            record = self.store.get_event(row["event_id"])
            if record:
                created = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
                year, week, _ = created.isocalendar()
                if year == iso_year and week == iso_week:
                    records.append(record)
        return weekly_digest(f"{iso_year}-W{iso_week:02d}", records)
