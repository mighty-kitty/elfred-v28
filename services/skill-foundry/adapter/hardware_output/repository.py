from __future__ import annotations

import json
import uuid
from typing import Any

from adapter.contracts import canonical_json
from adapter.hardware_output.models import (
    ActionProposal,
    JournalSnapshot,
    K3_OWNED_ADAPTER_IDS,
)
from adapter.storage import SQLiteStore
from adapter.storage.store import now_iso


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex


class HardwareOutputRepository:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def create_plan(
        self,
        *,
        journal: JournalSnapshot,
        journal_version: str,
        journal_hash: str,
        requested_mode: str,
        effective_mode: str,
        actions: list[ActionProposal],
        warnings: list[str],
        model_detail: dict[str, Any],
        force: bool,
    ) -> tuple[dict[str, Any], bool]:
        if not force:
            existing = self.find_plan(
                str(journal.journal_id),
                journal_version,
                journal_hash,
            )
            if existing is not None:
                return existing, False

        plan_id = _id("hplan_")
        timestamp = now_iso()
        status = (
            "awaiting_confirmation"
            if any(action.requires_confirmation for action in actions)
            else "ready"
        )
        with self.store.transaction() as connection:
            connection.execute(
                """INSERT INTO hardware_output_plans
                (plan_id,journal_id,journal_version,journal_date,journal_hash,
                 status,requested_mode,effective_mode,journal_json,warnings_json,
                 model_detail_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    plan_id,
                    str(journal.journal_id),
                    journal_version,
                    journal.date[:10],
                    journal_hash,
                    status,
                    requested_mode,
                    effective_mode,
                    canonical_json(journal.model_dump(mode="json", by_alias=False)),
                    canonical_json(warnings),
                    canonical_json(model_detail),
                    timestamp,
                    timestamp,
                ),
            )
            for position, action in enumerate(actions):
                connection.execute(
                    """INSERT INTO hardware_output_actions
                    (action_id,plan_id,position,adapter_id,command,preset,
                     parameters_json,summary,rationale,risk_level,
                     requires_confirmation,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
                    (
                        _id("haction_"),
                        plan_id,
                        position,
                        action.adapter_id.value,
                        action.command,
                        action.preset,
                        canonical_json(action.parameters),
                        action.summary,
                        action.rationale,
                        action.risk_level.value,
                        int(action.requires_confirmation),
                        timestamp,
                        timestamp,
                    ),
                )
            connection.execute(
                """INSERT INTO audit_logs(created_at,action,target,detail_json)
                VALUES(?,?,?,?)""",
                (
                    timestamp,
                    "hardware_plan_create",
                    plan_id,
                    canonical_json(
                        {
                            "journal_id": str(journal.journal_id),
                            "journal_version": journal_version,
                            "action_count": len(actions),
                            "effective_mode": effective_mode,
                        }
                    ),
                ),
            )
        return self.get_plan(plan_id) or {}, True

    def find_plan(
        self,
        journal_id: str,
        journal_version: str,
        journal_hash: str,
    ) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT plan_id FROM hardware_output_plans
                WHERE journal_id=? AND journal_version=? AND journal_hash=?
                ORDER BY created_at DESC LIMIT 1""",
                (journal_id, journal_version, journal_hash),
            ).fetchone()
        return self.get_plan(str(row["plan_id"])) if row else None

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            plan = connection.execute(
                "SELECT * FROM hardware_output_plans WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
            actions = connection.execute(
                """SELECT * FROM hardware_output_actions
                WHERE plan_id=? ORDER BY position""",
                (plan_id,),
            ).fetchall()
        if plan is None:
            return None
        return self._decode_plan(dict(plan), [dict(item) for item in actions])

    def list_plans(
        self,
        *,
        limit: int = 50,
        journal_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT plan_id FROM hardware_output_plans"
        params: list[Any] = []
        if journal_id is not None:
            sql += " WHERE journal_id=?"
            params.append(journal_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self.store.connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return [
            plan
            for row in rows
            if (plan := self.get_plan(str(row["plan_id"]))) is not None
        ]

    def queue_run(
        self,
        *,
        plan_id: str,
        action_ids: list[str],
        confirmed_action_ids: list[str],
        idempotency_key: str,
        force: bool,
    ) -> tuple[dict[str, Any], bool]:
        existing = self.get_run_by_idempotency(idempotency_key)
        if existing is not None:
            return existing, False
        plan = self.get_plan(plan_id)
        if plan is None:
            raise KeyError("hardware output plan not found")
        known = {item["action_id"]: item for item in plan["actions"]}
        selected_ids = action_ids or list(known)
        unknown = sorted(set(selected_ids) - set(known))
        if unknown:
            raise ValueError(f"unknown action ids: {', '.join(unknown)}")
        if action_ids and any(
            known[action_id]["adapter_id"] in K3_OWNED_ADAPTER_IDS
            for action_id in selected_ids
        ):
            raise ValueError(
                "base, arm, and printer actions are owned by K3 and cannot run on the PC"
            )

        confirmed = set(confirmed_action_ids)
        runnable: list[str] = []
        blocked: list[str] = []
        timestamp = now_iso()
        with self.store.transaction() as connection:
            for action_id in selected_ids:
                action = known[action_id]
                if (
                    action["status"] in {"completed", "canceled"}
                    and not force
                ):
                    continue
                if action["requires_confirmation"] and action_id not in confirmed:
                    blocked.append(action_id)
                    connection.execute(
                        """UPDATE hardware_output_actions
                        SET status='confirmation_required',updated_at=?
                        WHERE action_id=?""",
                        (timestamp, action_id),
                    )
                    continue
                runnable.append(action_id)
                connection.execute(
                    """UPDATE hardware_output_actions
                    SET status='queued',last_error=NULL,updated_at=?
                    WHERE action_id=?""",
                    (timestamp, action_id),
                )

            if runnable:
                run_status = "queued"
                plan_status = "running"
            elif blocked:
                run_status = "awaiting_confirmation"
                plan_status = "awaiting_confirmation"
            else:
                run_status = "completed"
                plan_status = self._calculate_plan_status(connection, plan_id)

            run_id = _id("hrun_")
            connection.execute(
                """INSERT INTO hardware_output_runs
                (run_id,plan_id,status,idempotency_key,
                 requested_action_ids_json,confirmed_action_ids_json,
                 blocked_action_ids_json,force,result_json,created_at,finished_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    plan_id,
                    run_status,
                    idempotency_key,
                    canonical_json(runnable),
                    canonical_json(sorted(confirmed)),
                    canonical_json(blocked),
                    int(force),
                    canonical_json({}),
                    timestamp,
                    timestamp if run_status != "queued" else None,
                ),
            )
            connection.execute(
                """UPDATE hardware_output_plans
                SET status=?,updated_at=? WHERE plan_id=?""",
                (plan_status, timestamp, plan_id),
            )
            connection.execute(
                """INSERT INTO audit_logs(created_at,action,target,detail_json)
                VALUES(?,?,?,?)""",
                (
                    timestamp,
                    "hardware_run_queue",
                    run_id,
                    canonical_json(
                        {
                            "plan_id": plan_id,
                            "runnable": runnable,
                            "blocked": blocked,
                        }
                    ),
                ),
            )
        return self.get_run(run_id) or {}, True

    def claim_next_run(self) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self.store.transaction() as connection:
            row = connection.execute(
                """SELECT run_id FROM hardware_output_runs
                WHERE status='queued' ORDER BY created_at LIMIT 1"""
            ).fetchone()
            if row is None:
                return None
            run_id = str(row["run_id"])
            cursor = connection.execute(
                """UPDATE hardware_output_runs SET status='running',started_at=?
                WHERE run_id=? AND status='queued'""",
                (timestamp, run_id),
            )
            if cursor.rowcount != 1:
                return None
        return self.get_run(run_id)

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM hardware_output_actions WHERE action_id=?",
                (action_id,),
            ).fetchone()
        return self._decode_action(dict(row)) if row else None

    def mark_action_running(self, action_id: str, run_id: str) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """UPDATE hardware_output_actions
                SET status='running',last_run_id=?,last_error=NULL,updated_at=?
                WHERE action_id=?""",
                (run_id, now_iso(), action_id),
            )

    def record_attempt(
        self,
        *,
        run_id: str,
        action_id: str,
        adapter_id: str,
        attempt_number: int,
        request: dict[str, Any],
        response: dict[str, Any],
        ok: bool,
        error: str | None,
        started_at: str,
        finished_at: str,
    ) -> None:
        attempt_id = _id("hattempt_")
        log_id = "k3log_" + attempt_id.removeprefix("hattempt_")
        log_payload = {
            "protocolVersion": "elfred-hardware-execution-log-v1",
            "recordType": "execution_log",
            "executable": False,
            "logId": log_id,
            "runId": run_id,
            "actionId": action_id,
            "adapterId": adapter_id,
            "attemptNumber": attempt_number,
            "operation": str(request.get("command") or ""),
            "preset": str(request.get("preset") or ""),
            "status": str(response.get("status") or "unknown"),
            "ok": bool(ok),
        }
        with self.store.transaction() as connection:
            connection.execute(
                """INSERT INTO hardware_output_attempts
                (attempt_id,run_id,action_id,adapter_id,attempt_number,status,
                 request_json,response_json,error,started_at,finished_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    run_id,
                    action_id,
                    adapter_id,
                    attempt_number,
                    "completed" if ok else "failed",
                    canonical_json(request),
                    canonical_json(response),
                    error,
                    started_at,
                    finished_at,
                ),
            )
            connection.execute(
                """INSERT INTO k3_execution_log_outbox
                (log_id,attempt_id,run_id,payload_json,status,created_at)
                VALUES(?,?,?,?,'pending',?)""",
                (log_id, attempt_id, run_id, canonical_json(log_payload), finished_at),
            )
            connection.execute(
                """UPDATE hardware_output_actions
                SET status=?,last_run_id=?,last_error=?,updated_at=?
                WHERE action_id=?""",
                (
                    "completed" if ok else "failed",
                    run_id,
                    error,
                    finished_at,
                    action_id,
                ),
            )

    def pending_k3_logs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT log_id,payload_json,send_attempts
                FROM k3_execution_log_outbox
                WHERE status='pending'
                AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                ORDER BY created_at,log_id LIMIT ?""",
                (now_iso(), max(1, min(int(limit), 100))),
            ).fetchall()
        return [
            {
                "log_id": str(row["log_id"]),
                "payload": json.loads(row["payload_json"]),
                "send_attempts": int(row["send_attempts"]),
            }
            for row in rows
        ]

    def mark_k3_log_sent(self, log_id: str) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """UPDATE k3_execution_log_outbox
                SET status='sent',send_attempts=send_attempts+1,
                    next_attempt_at=NULL,last_error=NULL,sent_at=?
                WHERE log_id=?""",
                (now_iso(), log_id),
            )

    def mark_k3_log_failed(self, log_id: str, error: str, next_attempt_at: str) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """UPDATE k3_execution_log_outbox
                SET send_attempts=send_attempts+1,last_error=?,next_attempt_at=?
                WHERE log_id=? AND status='pending'""",
                (str(error)[:500], next_attempt_at, log_id),
            )

    def k3_log_counts(self) -> dict[str, int]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) AS count FROM k3_execution_log_outbox GROUP BY status"
            ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        result: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT plan_id FROM hardware_output_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise KeyError("hardware output run not found")
            plan_id = str(row["plan_id"])
            connection.execute(
                """UPDATE hardware_output_runs
                SET status=?,result_json=?,error=?,finished_at=?
                WHERE run_id=?""",
                (status, canonical_json(result), error, timestamp, run_id),
            )
            plan_status = self._calculate_plan_status(connection, plan_id)
            connection.execute(
                """UPDATE hardware_output_plans
                SET status=?,updated_at=? WHERE plan_id=?""",
                (plan_status, timestamp, plan_id),
            )
            connection.execute(
                """INSERT INTO audit_logs(created_at,action,target,detail_json)
                VALUES(?,?,?,?)""",
                (
                    timestamp,
                    "hardware_run_finish",
                    run_id,
                    canonical_json({"status": status, "plan_status": plan_status}),
                ),
            )
        return self.get_run(run_id) or {}

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM hardware_output_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            attempts = connection.execute(
                """SELECT * FROM hardware_output_attempts
                WHERE run_id=? ORDER BY started_at,attempt_number""",
                (run_id,),
            ).fetchall()
        if row is None:
            return None
        result = self._decode_run(dict(row))
        result["attempts"] = [
            self._decode_attempt(dict(attempt)) for attempt in attempts
        ]
        return result

    def get_run_by_idempotency(self, key: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT run_id FROM hardware_output_runs
                WHERE idempotency_key=?""",
                (key,),
            ).fetchone()
        return self.get_run(str(row["run_id"])) if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT run_id FROM hardware_output_runs
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            run
            for row in rows
            if (run := self.get_run(str(row["run_id"]))) is not None
        ]

    def recover_interrupted_runs(self) -> int:
        """Make process-interrupted executions explicitly retryable."""

        timestamp = now_iso()
        with self.store.transaction() as connection:
            rows = connection.execute(
                """SELECT run_id,plan_id FROM hardware_output_runs
                WHERE status='running'"""
            ).fetchall()
            for row in rows:
                connection.execute(
                    """UPDATE hardware_output_runs
                    SET status='failed',error=?,finished_at=? WHERE run_id=?""",
                    (
                        "adapter process stopped during execution; retry explicitly",
                        timestamp,
                        row["run_id"],
                    ),
                )
                connection.execute(
                    """UPDATE hardware_output_actions
                    SET status='failed',last_error=?,updated_at=?
                    WHERE last_run_id=? AND status='running'""",
                    (
                        "adapter process stopped during execution",
                        timestamp,
                        row["run_id"],
                    ),
                )
                connection.execute(
                    """UPDATE hardware_output_plans
                    SET status='failed',updated_at=? WHERE plan_id=?""",
                    (timestamp, row["plan_id"]),
                )
        return len(rows)

    def counts(self) -> dict[str, Any]:
        with self.store.connect() as connection:
            plan_rows = connection.execute(
                """SELECT status,COUNT(*) AS count FROM hardware_output_plans
                GROUP BY status"""
            ).fetchall()
            run_rows = connection.execute(
                """SELECT status,COUNT(*) AS count FROM hardware_output_runs
                GROUP BY status"""
            ).fetchall()
        return {
            "plans": {str(row["status"]): int(row["count"]) for row in plan_rows},
            "runs": {str(row["status"]): int(row["count"]) for row in run_rows},
        }

    def record_device_event(
        self,
        adapter_id: str,
        event_type: str,
        status: str,
        detail: dict[str, Any],
    ) -> None:
        with self.store.transaction() as connection:
            connection.execute(
                """INSERT INTO hardware_device_events
                (event_id,adapter_id,event_type,status,detail_json,created_at)
                VALUES(?,?,?,?,?,?)""",
                (
                    _id("hdevice_"),
                    adapter_id,
                    event_type,
                    status,
                    canonical_json(detail),
                    now_iso(),
                ),
            )

    def recent_device_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM hardware_device_events
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        result = []
        for raw in rows:
            item = dict(raw)
            item["detail"] = json.loads(item.pop("detail_json"))
            result.append(item)
        return result

    @staticmethod
    def _calculate_plan_status(connection: Any, plan_id: str) -> str:
        rows = connection.execute(
            """SELECT status,COUNT(*) AS count FROM hardware_output_actions
            WHERE plan_id=? GROUP BY status""",
            (plan_id,),
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        if counts.get("running") or counts.get("queued"):
            return "running"
        if counts.get("confirmation_required"):
            return "awaiting_confirmation"
            if counts.get("failed"):
                return "partial" if counts.get("completed") else "failed"
            terminal = counts.get("completed", 0) + counts.get("canceled", 0)
            if counts and terminal == sum(counts.values()):
                return "completed"
        return "ready"

    @staticmethod
    def _decode_plan(
        plan: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        plan["journal"] = json.loads(plan.pop("journal_json"))
        plan["warnings"] = json.loads(plan.pop("warnings_json"))
        plan["model_detail"] = json.loads(plan.pop("model_detail_json"))
        plan["actions"] = [
            HardwareOutputRepository._decode_action(action) for action in actions
        ]
        return plan

    @staticmethod
    def _decode_action(action: dict[str, Any]) -> dict[str, Any]:
        action["parameters"] = json.loads(action.pop("parameters_json"))
        action["requires_confirmation"] = bool(action["requires_confirmation"])
        return action

    @staticmethod
    def _decode_run(run: dict[str, Any]) -> dict[str, Any]:
        run["requested_action_ids"] = json.loads(
            run.pop("requested_action_ids_json")
        )
        run["confirmed_action_ids"] = json.loads(
            run.pop("confirmed_action_ids_json")
        )
        run["blocked_action_ids"] = json.loads(
            run.pop("blocked_action_ids_json")
        )
        run["result"] = json.loads(run.pop("result_json"))
        run["force"] = bool(run["force"])
        return run

    @staticmethod
    def _decode_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
        attempt["request"] = json.loads(attempt.pop("request_json"))
        attempt["response"] = json.loads(attempt.pop("response_json"))
        return attempt
