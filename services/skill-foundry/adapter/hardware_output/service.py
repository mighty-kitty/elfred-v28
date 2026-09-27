from __future__ import annotations

import platform
import uuid
from pathlib import Path
from typing import Any

from adapter.config import Settings
from adapter.contracts import payload_hash
from adapter.freetodo_client import FreeTodoClient
from adapter.hardware_output.adapters import (
    AdapterCommand,
    HardwareAdapterRegistry,
)
from adapter.hardware_output.memory import (
    HardwareMemoryPort,
    NullHardwareMemoryPort,
)
from adapter.hardware_output.k3_logs import K3ExecutionLogReplicator, K3ExecutionLogSink
from adapter.hardware_output.models import (
    AdapterResult,
    ExecutePlanRequest,
    JournalSnapshot,
    K3_OWNED_ADAPTER_IDS,
    PlanCreateRequest,
)
from adapter.hardware_output.planner import HardwareActionPlanner
from adapter.hardware_output.repository import HardwareOutputRepository
from adapter.storage import SQLiteStore
from adapter.storage.store import now_iso


class HardwareOutputService:
    def __init__(
        self,
        settings: Settings,
        store: SQLiteStore,
        client: FreeTodoClient,
        memory_port: HardwareMemoryPort | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.client = client
        self.memory_port = memory_port or NullHardwareMemoryPort()
        self.repository = HardwareOutputRepository(store)
        config_path = settings.hardware_output_config_path
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parents[2]
                / "config"
                / "hardware_output.local.json"
            )
        self.registry = HardwareAdapterRegistry(
            config_path,
            timeout_seconds=settings.hardware_output_http_timeout_seconds,
        )
        self.planner = HardwareActionPlanner()
        self.recovered_runs = self.repository.recover_interrupted_runs()
        self.k3_log_config_error: str | None = None
        sink: K3ExecutionLogSink | None = None
        if settings.k3_log_url or settings.k3_log_hmac_secret:
            try:
                sink = K3ExecutionLogSink(
                    settings.k3_log_url,
                    settings.k3_log_hmac_secret,
                    settings.k3_log_timeout_seconds,
                )
            except ValueError as error:
                self.k3_log_config_error = str(error)
        self.k3_log_replicator = K3ExecutionLogReplicator(self.repository, sink)

    def create_plan(
        self,
        request: PlanCreateRequest,
    ) -> dict[str, Any]:
        journal = request.journal
        journal_data = journal.model_dump(mode="json", by_alias=False)
        journal_hash = payload_hash(journal_data)
        journal_version = (
            journal.journal_version
            or journal.updated_at
            or f"content-{journal_hash[:16]}"
        )
        requested_mode = request.planning_mode
        effective_request = requested_mode
        if requested_mode == "auto":
            effective_request = "deterministic"
        result = self.planner.plan(journal, effective_request)
        plan, created = self.repository.create_plan(
            journal=journal,
            journal_version=journal_version,
            journal_hash=journal_hash,
            requested_mode=requested_mode,
            effective_mode=result.effective_mode,
            actions=result.actions,
            warnings=result.warnings,
            model_detail=result.model_detail,
            force=request.force,
        )
        plan["created"] = created
        return plan

    def create_plan_from_remote(
        self,
        journal_id: int,
        *,
        planning_mode: str = "auto",
        force: bool = False,
    ) -> dict[str, Any]:
        journal = self.client.get_journal(journal_id)
        snapshot = self.snapshot_from_remote(journal)
        return self.create_plan(
            PlanCreateRequest(
                journal=snapshot,
                planning_mode=planning_mode,
                force=force,
            )
        )

    def create_plan_from_generated(
        self,
        payload: dict[str, Any],
        *,
        planning_mode: str = "auto",
        force: bool = False,
    ) -> dict[str, Any]:
        snapshot = self.snapshot_from_generated(payload)
        return self.create_plan(
            PlanCreateRequest(
                journal=snapshot,
                planning_mode=planning_mode,
                force=force,
            )
        )

    def list_journals(self, limit: int = 100) -> list[dict[str, Any]]:
        items = self.client.list_journals()
        items.sort(
            key=lambda item: str(
                item.get("updated_at") or item.get("date") or ""
            ),
            reverse=True,
        )
        return items[:limit]

    @staticmethod
    def snapshot_from_remote(item: dict[str, Any]) -> JournalSnapshot:
        date = item.get("date") or item.get("day_bucket_start")
        if not date:
            raise ValueError("remote Journal has no date")
        return JournalSnapshot(
            journal_id=item.get("id") or item.get("uid") or "unknown",
            journal_version=(
                item.get("version")
                or item.get("version_id")
                or item.get("updated_at")
            ),
            date=str(date),
            title=str(item.get("name") or "Elfred Personal Journal"),
            content=str(item.get("content") or ""),
            content_objective=str(item.get("content_objective") or ""),
            content_ai=str(item.get("content_ai") or ""),
            user_notes=str(item.get("user_notes") or ""),
            mood=item.get("mood"),
            energy=item.get("energy"),
            tags=[
                str(tag.get("tag_name") if isinstance(tag, dict) else tag)
                for tag in (item.get("tags") or [])
            ],
            updated_at=item.get("updated_at"),
            metadata={
                "uid": item.get("uid"),
                "content_format": item.get("content_format"),
                "source": "freetodo",
            },
        )

    @staticmethod
    def snapshot_from_generated(payload: dict[str, Any]) -> JournalSnapshot:
        date = payload.get("date")
        if not date:
            raise ValueError("generated Journal has no date")
        journal_id = (
            payload.get("journal_id")
            or payload.get("uid")
            or f"generated-journal-{date}"
        )
        return JournalSnapshot(
            journal_id=str(journal_id),
            journal_version=payload.get("version") or payload.get("updated_at"),
            date=str(date),
            title=str(payload.get("name") or "Elfred Personal Journal"),
            content=str(payload.get("content") or ""),
            content_objective=str(payload.get("content_objective") or ""),
            content_ai=str(payload.get("content_ai") or ""),
            user_notes=str(payload.get("user_notes") or ""),
            mood=payload.get("mood"),
            energy=payload.get("energy"),
            tags=[str(tag) for tag in (payload.get("tags") or [])],
            updated_at=payload.get("updated_at"),
            metadata={
                "source": "journal_generator",
                "related_todo_ids": payload.get("related_todo_ids") or [],
                "related_activity_ids": payload.get("related_activity_ids") or [],
            },
        )

    def queue_plan(
        self,
        plan_id: str,
        request: ExecutePlanRequest,
    ) -> dict[str, Any]:
        idempotency_key = request.idempotency_key or (
            "hardware:"
            + payload_hash(
                {
                    "plan_id": plan_id,
                    "action_ids": sorted(request.action_ids),
                    "confirmed": sorted(request.confirmed_action_ids),
                    "force": request.force,
                }
            )
        )
        run, created = self.repository.queue_run(
            plan_id=plan_id,
            action_ids=request.action_ids,
            confirmed_action_ids=request.confirmed_action_ids,
            idempotency_key=idempotency_key,
            force=request.force,
        )
        run["created"] = created
        return run

    def execute_next(self) -> dict[str, Any] | None:
        run = self.repository.claim_next_run()
        if run is None:
            return None
        return self.execute_run(run["run_id"])

    def execute_run(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError("hardware output run not found")
        if run["status"] not in {"running", "queued"}:
            return run

        results: list[dict[str, Any]] = []
        successes = 0
        failures = 0
        max_attempts = max(1, min(self.settings.hardware_output_max_attempts, 5))
        for action_id in run["requested_action_ids"]:
            action = self.repository.get_action(action_id)
            if action is None:
                failures += 1
                results.append(
                    {
                        "action_id": action_id,
                        "ok": False,
                        "error": "action not found",
                    }
                )
                continue
            if action["adapter_id"] in K3_OWNED_ADAPTER_IDS:
                failures += 1
                blocked = AdapterResult(
                    ok=False,
                    status="ownership_blocked",
                    error=f"{action['adapter_id']} is owned locally by K3",
                )
                self.repository.record_attempt(
                    run_id=run_id,
                    action_id=action_id,
                    adapter_id=action["adapter_id"],
                    attempt_number=1,
                    request={"command": action["command"], "preset": action["preset"]},
                    response=blocked.model_dump(mode="json", by_alias=False),
                    ok=False,
                    error=blocked.error,
                    started_at=now_iso(),
                    finished_at=now_iso(),
                )
                results.append(
                    {
                        "action_id": action_id,
                        "adapter_id": action["adapter_id"],
                        "ok": False,
                        "status": blocked.status,
                        "error": blocked.error,
                    }
                )
                continue
            self.repository.mark_action_running(action_id, run_id)
            adapter = self.registry.get(action["adapter_id"])
            command = AdapterCommand(
                run_id=run_id,
                action_id=action_id,
                adapter_id=action["adapter_id"],
                command=action["command"],
                preset=action["preset"],
                parameters=action["parameters"],
            )
            action_max_attempts = (
                max_attempts
                if adapter.automatic_retry_safe
                else 1
            )
            final_result: AdapterResult | None = None
            for attempt_number in range(1, action_max_attempts + 1):
                started_at = now_iso()
                try:
                    final_result = adapter.execute(command)
                except Exception as error:  # a vendor bridge must not kill the worker
                    final_result = AdapterResult(
                        ok=False,
                        status="adapter_exception",
                        error=str(error),
                    )
                finished_at = now_iso()
                response = final_result.model_dump(mode="json", by_alias=False)
                self.repository.record_attempt(
                    run_id=run_id,
                    action_id=action_id,
                    adapter_id=action["adapter_id"],
                    attempt_number=attempt_number,
                    request=command.payload(),
                    response=response,
                    ok=final_result.ok,
                    error=final_result.error,
                    started_at=started_at,
                    finished_at=finished_at,
                )
                if final_result.ok:
                    break
                if attempt_number < action_max_attempts:
                    self.repository.mark_action_running(action_id, run_id)
            final_result = final_result or AdapterResult(
                ok=False,
                status="adapter_exception",
                error="adapter returned no result",
            )
            successes += int(final_result.ok)
            failures += int(not final_result.ok)
            results.append(
                {
                    "action_id": action_id,
                    "adapter_id": action["adapter_id"],
                    **final_result.model_dump(mode="json", by_alias=False),
                }
            )

        blocked = run["blocked_action_ids"]
        if failures and successes:
            status = "partial"
        elif failures:
            status = "failed"
        elif blocked:
            status = "partial"
        else:
            status = "completed"
        error = (
            f"{failures} hardware action(s) failed"
            if failures
            else None
        )
        return self.repository.finish_run(
            run_id,
            status=status,
            result={
                "actions": results,
                "blocked_action_ids": blocked,
                "success_count": successes,
                "failure_count": failures,
            },
            error=error,
        )

    def retry_run(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError("hardware output run not found")
        failed = [
            attempt["action_id"]
            for attempt in run["attempts"]
            if attempt["status"] == "failed"
        ]
        failed = list(dict.fromkeys(failed))
        if not failed:
            raise ValueError("run has no failed actions to retry")
        return self.queue_plan(
            run["plan_id"],
            ExecutePlanRequest(
                action_ids=failed,
                confirmed_action_ids=[
                    action_id
                    for action_id in failed
                    if action_id in run["confirmed_action_ids"]
                ],
                idempotency_key=f"retry:{run_id}:{uuid.uuid4().hex}",
            ),
        )

    def probe_adapter(self, adapter_id: str) -> dict[str, Any]:
        adapter = self.registry.get(adapter_id)
        result = adapter.probe()
        detail = result.model_dump(mode="json", by_alias=False)
        self.repository.record_device_event(
            adapter_id,
            "probe",
            result.status,
            {"ok": result.ok, "error": result.error},
        )
        return detail

    def test_adapter(
        self,
        adapter_id: str,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if adapter_id == "arm" and not confirm:
            raise PermissionError("robot arm self-test requires explicit confirmation")
        command, preset, parameters = {
            "pendant": ("notify", "journal_ready", {"title": "Elfred 自检"}),
            "base": ("play_scene", "welcome_home", {"diagnostic": True}),
            "arm": ("run_preset", "diagnostic", {"diagnostic": True}),
            "printer": (
                "print_journal",
                "diagnostic",
                {
                    "document": {
                        "title": "Elfred Hardware Diagnostic",
                        "date": now_iso()[:10],
                        "body": "This is a hardware adapter diagnostic page.",
                    }
                },
            ),
        }[adapter_id]
        adapter_command = AdapterCommand(
            run_id="diagnostic",
            action_id=f"diagnostic-{uuid.uuid4().hex}",
            adapter_id=adapter_id,
            command=command,
            preset=preset,
            parameters=parameters,
        )
        result = self.registry.get(adapter_id).execute(adapter_command)
        detail = result.model_dump(mode="json", by_alias=False)
        self.repository.record_device_event(
            adapter_id,
            "self_test",
            result.status,
            {"ok": result.ok, "error": result.error},
        )
        return detail

    def stop_adapter(self, adapter_id: str) -> dict[str, Any]:
        result = self.registry.get(adapter_id).stop()
        detail = result.model_dump(mode="json", by_alias=False)
        self.repository.record_device_event(
            adapter_id,
            "stop",
            result.status,
            {"ok": result.ok, "error": result.error},
        )
        return detail

    def status(self, *, probe: bool = False) -> dict[str, Any]:
        return {
            "enabled": self.settings.hardware_output_enabled,
            "protocol_version": "1.0",
            "planning": {
                "model_enabled": False,
                "cloud_consent": self.settings.llm_cloud_consent,
                "effective_mode": "deterministic",
                "provider": None,
                "model": None,
                "journal_auto_plan": (
                    self.settings.hardware_output_enabled
                    and self.settings.hardware_output_auto_plan_on_journal
                ),
            },
            "adapters": self.registry.describe(probe=probe),
            "counts": self.repository.counts(),
            "worker_interval_seconds": (
                self.settings.hardware_output_worker_interval_seconds
            ),
            "k3_log_replication": {
                "enabled": self.k3_log_replicator.enabled,
                "config_error": self.k3_log_config_error,
                "outbox": self.repository.k3_log_counts(),
                "execution_dependency": False,
            },
            "recovered_interrupted_runs": self.recovered_runs,
            "config": {
                "path": str(self.registry.config_path),
                "exists": self.registry.config_path.exists(),
                "load_error": self.registry.load_error,
            },
        }

    def doctor(self) -> dict[str, Any]:
        status = self.status(probe=True)
        status["database"] = {
            "path": str(self.store.path),
            "exists": self.store.path.exists(),
        }
        status["platform"] = {
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        }
        status["checks"] = {
            "database_ready": True,
            "four_logical_adapters": len(status["adapters"]) == 4,
            "all_adapters_ready": all(
                bool(item.get("health", {}).get("ok"))
                for item in status["adapters"]
            ),
            "model_is_optional": True,
        }
        return status

    def support_bundle(self) -> dict[str, Any]:
        """Return diagnostics without Journal text, commands, headers, or secrets."""

        status = self.status(probe=False)
        events = self.repository.recent_device_events(50)
        runs = self.repository.list_runs(20)
        return {
            "generated_at": now_iso(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
            },
            "status": status,
            "recent_device_events": [
                {
                    "event_id": item["event_id"],
                    "adapter_id": item["adapter_id"],
                    "event_type": item["event_type"],
                    "status": item["status"],
                    "created_at": item["created_at"],
                }
                for item in events
            ],
            "recent_runs": [
                {
                    "run_id": item["run_id"],
                    "plan_id": item["plan_id"],
                    "status": item["status"],
                    "error": item["error"],
                    "created_at": item["created_at"],
                    "started_at": item["started_at"],
                    "finished_at": item["finished_at"],
                    "attempt_count": len(item["attempts"]),
                }
                for item in runs
            ],
            "redaction": {
                "journal_text_included": False,
                "adapter_headers_included": False,
                "command_parameters_included": False,
            },
        }
