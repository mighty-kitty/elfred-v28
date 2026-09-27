from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from adapter.contracts import canonical_json, payload_hash


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


class SQLiteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema)
            self._ensure_analysis_schema(conn)
            self._ensure_skill_schema(conn)
            self._ensure_journal_schema(conn)
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_task_analyses_ready
                ON event_task_analyses(status,next_attempt_at,lease_until)"""
            )

    @staticmethod
    def _ensure_journal_schema(conn: sqlite3.Connection) -> None:
        """Add generation counters to databases created by Journal v2 previews."""

        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(journal_sync_state)"
            ).fetchall()
        }
        additions = {
            "requested_generation": "INTEGER NOT NULL DEFAULT 1",
            "processed_generation": "INTEGER NOT NULL DEFAULT 0",
            "lease_token": "TEXT",
            "remote_managed": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, declaration in additions.items():
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE journal_sync_state ADD COLUMN {name} {declaration}"
                )

    @staticmethod
    def _ensure_analysis_schema(conn: sqlite3.Connection) -> None:
        """Add queue metadata when opening a database created by an older Adapter."""

        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(event_task_analyses)").fetchall()
        }
        additions = {
            "attempt_count": "INTEGER NOT NULL DEFAULT 0",
            "next_attempt_at": "TEXT",
            "lease_until": "TEXT",
            "prompt_version": "TEXT NOT NULL DEFAULT 'task-analysis-v1'",
            "schema_version": "TEXT NOT NULL DEFAULT '1.0'",
        }
        for name, declaration in additions.items():
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE event_task_analyses ADD COLUMN {name} {declaration}"
                )

    @staticmethod
    def _ensure_skill_schema(conn: sqlite3.Connection) -> None:
        """Preserve a published version while passive learning prepares a draft."""

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(skills)").fetchall()
        }
        if "published_version_id" not in columns:
            conn.execute(
                "ALTER TABLE skills ADD COLUMN published_version_id TEXT"
            )
        if "auto_execute_enabled" not in columns:
            conn.execute(
                "ALTER TABLE skills ADD COLUMN "
                "auto_execute_enabled INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            """UPDATE skills SET published_version_id=current_version_id
            WHERE published_version_id IS NULL
            AND status IN ('approved','active')"""
        )
        SQLiteStore._ensure_skill_candidate_status_schema(conn)

    @staticmethod
    def _ensure_skill_candidate_status_schema(
        conn: sqlite3.Connection,
    ) -> None:
        """Expand the legacy candidate status check without losing rows."""

        row = conn.execute(
            """SELECT sql FROM sqlite_master
            WHERE type='table' AND name='skill_candidate_groups'"""
        ).fetchone()
        table_sql = str(row["sql"] or "") if row else ""
        if "validating_reproduction" in table_sql:
            return

        conn.execute(
            "ALTER TABLE skill_candidate_groups RENAME TO "
            "skill_candidate_groups_legacy"
        )
        conn.execute(
            """CREATE TABLE skill_candidate_groups (
              group_id TEXT PRIMARY KEY,
              group_key TEXT NOT NULL UNIQUE,
              label TEXT NOT NULL,
              status TEXT NOT NULL,
              skill_id TEXT,
              task_ids_json TEXT NOT NULL,
              profile_json TEXT NOT NULL,
              last_build_hash TEXT,
              last_build_id TEXT,
              error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              CHECK(status IN (
                'observing','ready','building','draft_ready','evidence_gap',
                'pattern_forming','validating_reproduction','failed','ignored'
              )),
              FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
            )"""
        )
        conn.execute(
            """INSERT INTO skill_candidate_groups
            (group_id,group_key,label,status,skill_id,task_ids_json,
             profile_json,last_build_hash,last_build_id,error,created_at,
             updated_at)
            SELECT group_id,group_key,label,status,skill_id,task_ids_json,
             profile_json,last_build_hash,last_build_id,error,created_at,
             updated_at
            FROM skill_candidate_groups_legacy"""
        )
        conn.execute("DROP TABLE skill_candidate_groups_legacy")
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_skill_candidate_groups_status
            ON skill_candidate_groups(status,updated_at)"""
        )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def ingest_event(self, canonical: dict[str, Any], digest: str) -> str:
        event = canonical["event"]
        event_id = event["event_id"]
        timestamp = now_iso()
        payload = canonical_json(canonical)
        with self.transaction() as conn:
            current = conn.execute(
                "SELECT payload_hash FROM ingested_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if current and current["payload_hash"] == digest:
                disposition = "duplicate"
            elif current:
                disposition = "conflict"
                conn.execute(
                    "UPDATE ingested_events SET status='conflict', last_error=?, updated_at=? WHERE event_id=?",
                    ("same event_id with different payload", timestamp, event_id),
                )
            else:
                disposition = "accepted"
                conn.execute(
                    """INSERT INTO ingested_events
                    (event_id,schema_version,producer,received_at,created_at,source,payload_hash,
                     payload_json,status,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id,
                        canonical["schema_version"],
                        canonical["producer"],
                        canonical["received_at"],
                        event["created_at"],
                        event["source"],
                        digest,
                        payload,
                        "accepted",
                        timestamp,
                    ),
                )
            version_id = "ver_" + payload_hash([event_id, digest])[:24]
            conn.execute(
                """INSERT OR IGNORE INTO event_payload_versions
                (version_id,event_id,payload_hash,payload_json,disposition,created_at)
                VALUES (?,?,?,?,?,?)""",
                (version_id, event_id, digest, payload, disposition, timestamp),
            )
            conn.execute(
                "INSERT INTO audit_logs(created_at,action,target,detail_json) VALUES(?,?,?,?)",
                (timestamp, "event_ingest", event_id, canonical_json({"disposition": disposition, "hash": digest})),
            )
        return disposition

    def get_event(self, event_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        sql = "SELECT * FROM ingested_events WHERE event_id=?"
        params: tuple[Any, ...] = (event_id,)
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        with self.connect() as conn:
            row = self._row(conn.execute(sql, params).fetchone())
        if row:
            row["payload"] = json.loads(row.pop("payload_json"))
        return row

    def events_for_day(self, day: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM ingested_events
                WHERE substr(created_at,1,10)=? AND deleted_at IS NULL
                AND status NOT IN ('conflict','privacy_blocked') ORDER BY created_at,event_id""",
                (day,),
            ).fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            row["payload"] = json.loads(row.pop("payload_json"))
            result.append(row)
        return result

    def event_days_through(self, day: str) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT substr(created_at,1,10) AS event_day
                FROM ingested_events
                WHERE deleted_at IS NULL AND substr(created_at,1,10)<=?
                ORDER BY event_day""",
                (day,),
            ).fetchall()
        return [str(row["event_day"]) for row in rows if row["event_day"]]

    def legacy_events_for_day(self, day: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT payload_json FROM ingested_events
                WHERE substr(created_at,1,10)=? AND deleted_at IS NULL
                ORDER BY created_at DESC,event_id DESC""",
                (day,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            event = payload.get("event")
            if isinstance(event, dict):
                events.append(event)
        return events

    def enqueue_journal_day(self, day: str, trigger: str) -> dict[str, Any]:
        timestamp = now_iso()
        uid = f"elfred-daily-{day}"
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO journal_sync_state
                (journal_date,uid,status,trigger_name,created_at,updated_at)
                VALUES(?,?,'pending',?,?,?)
                ON CONFLICT(journal_date) DO UPDATE SET
                status=CASE
                  WHEN journal_sync_state.status IN ('manual_modified','duplicate_uid')
                  THEN journal_sync_state.status
                  WHEN journal_sync_state.lease_until IS NOT NULL
                    AND journal_sync_state.lease_until>excluded.updated_at
                  THEN journal_sync_state.status
                  ELSE 'pending' END,
                trigger_name=excluded.trigger_name,
                requested_generation=journal_sync_state.requested_generation+1,
                next_attempt_at=CASE
                  WHEN journal_sync_state.lease_until IS NOT NULL
                    AND journal_sync_state.lease_until>excluded.updated_at
                  THEN journal_sync_state.next_attempt_at ELSE NULL END,
                updated_at=excluded.updated_at""",
                (day, uid, trigger, timestamp, timestamp),
            )
        return self.journal_sync_state(day) or {}

    def claim_journal_day(
        self,
        day: str,
        *,
        lease_seconds: float = 600.0,
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        base = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        lease_until = (
            base + timedelta(seconds=max(1.0, lease_seconds))
        ).isoformat()
        lease_token = uuid.uuid4().hex
        with self.transaction() as conn:
            cursor = conn.execute(
                """UPDATE journal_sync_state SET status='running',lease_until=?,
                lease_token=?,next_attempt_at=NULL,updated_at=?
                WHERE journal_date=?
                AND (lease_until IS NULL OR lease_until<=?)""",
                (lease_until, lease_token, timestamp, day, timestamp),
            )
            if cursor.rowcount != 1:
                return None
        return self.journal_sync_state(day)

    def claim_next_journal_day(
        self,
        *,
        lease_seconds: float = 600.0,
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        with self.connect() as conn:
            row = conn.execute(
                """SELECT journal_date FROM journal_sync_state
                WHERE (
                  status IN ('pending','retry_pending','failed_terminal')
                  AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                  AND (lease_until IS NULL OR lease_until<=?)
                ) OR (
                  status='running' AND lease_until IS NOT NULL AND lease_until<=?
                ) OR (
                  hardware_status IN ('pending','retry_pending')
                  AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                  AND (lease_until IS NULL OR lease_until<=?)
                )
                ORDER BY updated_at,journal_date LIMIT 1""",
                (timestamp, timestamp, timestamp, timestamp, timestamp),
            ).fetchone()
        if row is None:
            return None
        return self.claim_journal_day(
            str(row["journal_date"]),
            lease_seconds=lease_seconds,
        )

    def journal_sync_state(self, day: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM journal_sync_state WHERE journal_date=?",
                (day,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        for source, target in (
            ("candidate_json", "candidate"),
            ("last_remote_json", "last_remote"),
        ):
            raw = item.pop(source, None)
            item[target] = json.loads(raw) if raw else None
        return item

    def update_journal_sync_state(self, day: str, **values: Any) -> None:
        allowed = {
            "status",
            "trigger_name",
            "source_hash",
            "candidate_hash",
            "candidate_status",
            "candidate_json",
            "remote_id",
            "last_remote_hash",
            "last_remote_json",
            "source_event_count",
            "included_event_count",
            "excluded_event_count",
            "requested_generation",
            "processed_generation",
            "attempt_count",
            "next_attempt_at",
            "lease_until",
            "lease_token",
            "last_error",
            "prompt_version",
            "privacy_version",
            "hardware_status",
            "hardware_error",
            "remote_managed",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(
                "Unsupported journal state fields: " + ", ".join(sorted(unknown))
            )
        if not values:
            return
        serialized = dict(values)
        for key in ("candidate_json", "last_remote_json"):
            if key in serialized and serialized[key] is not None:
                serialized[key] = canonical_json(serialized[key])
        serialized["updated_at"] = now_iso()
        assignments = ",".join(f"{key}=?" for key in serialized)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE journal_sync_state SET {assignments} WHERE journal_date=?",
                (*serialized.values(), day),
            )

    def renew_journal_lease(
        self,
        day: str,
        lease_token: str,
        *,
        lease_seconds: float,
    ) -> dict[str, Any] | None:
        timestamp = now_iso()
        base = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        lease_until = (
            base + timedelta(seconds=max(1.0, lease_seconds))
        ).isoformat()
        with self.transaction() as conn:
            cursor = conn.execute(
                """UPDATE journal_sync_state SET lease_until=?,updated_at=?
                WHERE journal_date=? AND lease_token=? AND lease_until>?""",
                (lease_until, timestamp, day, lease_token, timestamp),
            )
            if cursor.rowcount != 1:
                return None
        return self.journal_sync_state(day)

    def update_claimed_journal_state(
        self,
        day: str,
        expected_lease_token: str,
        **values: Any,
    ) -> dict[str, Any] | None:
        allowed = {
            "status",
            "trigger_name",
            "source_hash",
            "candidate_hash",
            "candidate_status",
            "candidate_json",
            "remote_id",
            "last_remote_hash",
            "last_remote_json",
            "source_event_count",
            "included_event_count",
            "excluded_event_count",
            "requested_generation",
            "processed_generation",
            "attempt_count",
            "next_attempt_at",
            "lease_until",
            "lease_token",
            "last_error",
            "prompt_version",
            "privacy_version",
            "hardware_status",
            "hardware_error",
            "remote_managed",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(
                "Unsupported journal state fields: " + ", ".join(sorted(unknown))
            )
        if not values:
            return self.journal_sync_state(day)
        serialized = dict(values)
        for key in ("candidate_json", "last_remote_json"):
            if key in serialized and serialized[key] is not None:
                serialized[key] = canonical_json(serialized[key])
        timestamp = now_iso()
        serialized["updated_at"] = timestamp
        assignments = ",".join(f"{key}=?" for key in serialized)
        with self.transaction() as conn:
            cursor = conn.execute(
                f"""UPDATE journal_sync_state SET {assignments}
                WHERE journal_date=? AND lease_token=? AND lease_until>?""",
                (*serialized.values(), day, expected_lease_token, timestamp),
            )
            if cursor.rowcount != 1:
                return None
        return self.journal_sync_state(day)

    def finalize_journal_day(
        self,
        day: str,
        claimed_generation: int,
        lease_token: str,
        *,
        release_lease: bool = True,
        **values: Any,
    ) -> dict[str, Any] | None:
        """Commit a result without losing work enqueued during generation."""

        allowed = {
            "status",
            "trigger_name",
            "source_hash",
            "candidate_hash",
            "candidate_status",
            "candidate_json",
            "remote_id",
            "last_remote_hash",
            "last_remote_json",
            "source_event_count",
            "included_event_count",
            "excluded_event_count",
            "attempt_count",
            "next_attempt_at",
            "lease_until",
            "lease_token",
            "last_error",
            "prompt_version",
            "privacy_version",
            "hardware_status",
            "hardware_error",
            "remote_managed",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(
                "Unsupported journal final fields: " + ", ".join(sorted(unknown))
            )
        serialized = dict(values)
        for key in ("candidate_json", "last_remote_json"):
            if key in serialized and serialized[key] is not None:
                serialized[key] = canonical_json(serialized[key])
        with self.transaction() as conn:
            timestamp = now_iso()
            row = conn.execute(
                """SELECT requested_generation,processed_generation
                FROM journal_sync_state WHERE journal_date=?
                AND lease_token=? AND lease_until>?""",
                (day, lease_token, timestamp),
            ).fetchone()
            if row is None:
                return None
            requested = int(row["requested_generation"])
            processed = max(
                int(row["processed_generation"]),
                int(claimed_generation),
            )
            final_status = str(serialized.get("status") or "succeeded")
            reprocessable = final_status in {
                "succeeded",
                "adopted_existing",
                "skipped_no_events",
                "skipped_privacy",
            }
            dirty = requested > int(claimed_generation) and reprocessable
            if dirty:
                serialized["status"] = "pending"
                serialized["next_attempt_at"] = None
                if serialized.get("hardware_status") in {
                    "pending",
                    "retry_pending",
                }:
                    serialized["hardware_status"] = "deferred"
            serialized["processed_generation"] = processed
            if release_lease or dirty:
                serialized["lease_until"] = None
                serialized["lease_token"] = None
            serialized["updated_at"] = timestamp
            assignments = ",".join(f"{key}=?" for key in serialized)
            cursor = conn.execute(
                f"""UPDATE journal_sync_state SET {assignments}
                WHERE journal_date=? AND lease_token=? AND lease_until>?""",
                (*serialized.values(), day, lease_token, timestamp),
            )
            if cursor.rowcount != 1:
                return None
        return self.journal_sync_state(day) or {}

    def defer_journal_day(
        self,
        day: str,
        error: str,
        *,
        lease_token: str,
        retry_after_seconds: float,
        count_attempt: bool = True,
    ) -> dict[str, Any] | None:
        now = datetime.now().astimezone()
        next_attempt = (
            now + timedelta(seconds=max(0.0, retry_after_seconds))
        ).isoformat()
        timestamp = now.isoformat()
        with self.transaction() as conn:
            row = conn.execute(
                """SELECT attempt_count FROM journal_sync_state
                WHERE journal_date=? AND lease_token=? AND lease_until>?""",
                (day, lease_token, timestamp),
            ).fetchone()
            if row is None:
                return None
            attempts = int(row["attempt_count"] or 0) + int(count_attempt)
            cursor = conn.execute(
                """UPDATE journal_sync_state SET status='retry_pending',
                attempt_count=?,next_attempt_at=?,lease_until=NULL,lease_token=NULL,
                last_error=?,updated_at=? WHERE journal_date=?
                AND lease_token=? AND lease_until>?""",
                (
                    attempts,
                    next_attempt,
                    str(error)[:2000],
                    timestamp,
                    day,
                    lease_token,
                    timestamp,
                ),
            )
            if cursor.rowcount != 1:
                return None
        return self.journal_sync_state(day) or {}

    def set_event_status(self, event_id: str, status: str, error: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE ingested_events SET status=?,last_error=?,updated_at=? WHERE event_id=?",
                (status, error, now_iso(), event_id),
            )

    def soft_delete_event(self, event_id: str, status: str = "deleted") -> bool:
        timestamp = now_iso()
        with self.transaction() as conn:
            cursor = conn.execute(
                "UPDATE ingested_events SET status=?,deleted_at=?,updated_at=? WHERE event_id=? AND deleted_at IS NULL",
                (status, timestamp, timestamp, event_id),
            )
            conn.execute(
                "INSERT INTO audit_logs(created_at,action,target,detail_json) VALUES(?,?,?,?)",
                (timestamp, "event_delete", event_id, canonical_json({"status": status})),
            )
            return cursor.rowcount > 0

    def create_job(self, event_id: str | None, job_type: str, detail: dict[str, Any] | None = None) -> str:
        job_id = "job_" + uuid.uuid4().hex
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO sync_jobs
                (job_id,event_id,job_type,status,attempt_count,detail_json,created_at,updated_at)
                VALUES(?,?,?,'running',0,?,?,?)""",
                (job_id, event_id, job_type, canonical_json(detail or {}), timestamp, timestamp),
            )
        return job_id

    def finish_job(self, job_id: str, status: str, detail: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE sync_jobs SET status=?,attempt_count=attempt_count+1,detail_json=?,updated_at=? WHERE job_id=?",
                (status, canonical_json(detail), now_iso(), job_id),
            )

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = self._row(conn.execute("SELECT * FROM sync_jobs WHERE job_id=?", (job_id,)).fetchone())
        if row:
            row["detail"] = json.loads(row.pop("detail_json"))
        return row

    def jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM sync_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            row["detail"] = json.loads(row.pop("detail_json"))
            result.append(row)
        return result

    def add_attempt(
        self, job_id: str, target: str, operation: str, status: str,
        *, error: str | None = None, request: Any = None,
    ) -> None:
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO sync_attempts
                (attempt_id,job_id,target,operation,status,error,request_hash,started_at,finished_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    "try_" + uuid.uuid4().hex,
                    job_id,
                    target,
                    operation,
                    status,
                    error,
                    payload_hash(request) if request is not None else None,
                    timestamp,
                    timestamp,
                ),
            )

    def record_privacy(
        self, event_id: str, local_allowed: bool, cloud_allowed: bool,
        reason: str, redactions: list[str],
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO privacy_decisions
                (decision_id,event_id,local_allowed,cloud_allowed,reason,redactions_json,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    "privacy_" + uuid.uuid4().hex,
                    event_id,
                    int(local_allowed),
                    int(cloud_allowed),
                    reason,
                    canonical_json(redactions),
                    now_iso(),
                ),
            )

    def upsert_task_analysis(
        self,
        event_id: str,
        status: str,
        provider: str,
        model: str,
        source_hash: str,
        cloud_consent: bool,
        analysis: dict[str, Any],
        error: str | None = None,
        *,
        prompt_version: str = "task-analysis-v1",
        schema_version: str = "1.0",
    ) -> None:
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO event_task_analyses
                (event_id,status,provider,model,source_hash,cloud_consent,analysis_json,error,
                 prompt_version,schema_version,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET
                status=excluded.status,provider=excluded.provider,model=excluded.model,
                source_hash=excluded.source_hash,cloud_consent=excluded.cloud_consent,
                analysis_json=excluded.analysis_json,error=excluded.error,
                next_attempt_at=NULL,lease_until=NULL,
                prompt_version=excluded.prompt_version,schema_version=excluded.schema_version,
                updated_at=excluded.updated_at""",
                (
                    event_id,
                    status,
                    provider,
                    model,
                    source_hash,
                    int(cloud_consent),
                    canonical_json(analysis),
                    error,
                    prompt_version,
                    schema_version,
                    timestamp,
                    timestamp,
                ),
            )

    def enqueue_task_analysis(
        self,
        event_id: str,
        provider: str,
        model: str,
        source_hash: str,
        cloud_consent: bool,
        *,
        prompt_version: str = "task-analysis-v1",
        schema_version: str = "1.0",
        force: bool = False,
    ) -> bool:
        """Create one durable analysis job, or requeue it when its inputs changed."""

        timestamp = now_iso()
        with self.transaction() as conn:
            current = conn.execute(
                """SELECT provider,model,source_hash,prompt_version,schema_version
                FROM event_task_analyses WHERE event_id=?""",
                (event_id,),
            ).fetchone()
            if current is None:
                conn.execute(
                    """INSERT INTO event_task_analyses
                    (event_id,status,provider,model,source_hash,cloud_consent,analysis_json,error,
                     attempt_count,next_attempt_at,lease_until,prompt_version,schema_version,
                     created_at,updated_at)
                    VALUES(?,'pending',?,?,?,?, '{}',NULL,0,NULL,NULL,?,?,?,?)""",
                    (
                        event_id,
                        provider,
                        model,
                        source_hash,
                        int(cloud_consent),
                        prompt_version,
                        schema_version,
                        timestamp,
                        timestamp,
                    ),
                )
                return True

            signature = (
                current["provider"],
                current["model"],
                current["source_hash"],
                current["prompt_version"],
                current["schema_version"],
            )
            requested = (provider, model, source_hash, prompt_version, schema_version)
            if not force and signature == requested:
                return False
            conn.execute(
                """UPDATE event_task_analyses SET
                status='pending',provider=?,model=?,source_hash=?,cloud_consent=?,
                analysis_json='{}',error=NULL,attempt_count=0,next_attempt_at=NULL,
                lease_until=NULL,prompt_version=?,schema_version=?,updated_at=?
                WHERE event_id=?""",
                (
                    provider,
                    model,
                    source_hash,
                    int(cloud_consent),
                    prompt_version,
                    schema_version,
                    timestamp,
                    event_id,
                ),
            )
            return True

    def claim_task_analysis(
        self,
        *,
        lease_seconds: float = 120.0,
        now: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically lease the oldest ready analysis job to one worker."""

        claimed_at = now or now_iso()
        base = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
        lease_until = (base + timedelta(seconds=max(1.0, lease_seconds))).isoformat()
        with self.transaction() as conn:
            row = conn.execute(
                """SELECT event_id FROM event_task_analyses
                WHERE (
                    status IN ('pending','failed_retryable','publish_pending')
                    AND (next_attempt_at IS NULL OR next_attempt_at<=?)
                    AND (lease_until IS NULL OR lease_until<=?)
                ) OR (status='running' AND lease_until IS NOT NULL AND lease_until<=?)
                ORDER BY created_at,event_id LIMIT 1""",
                (claimed_at, claimed_at, claimed_at),
            ).fetchone()
            if row is None:
                return None
            event_id = str(row["event_id"])
            conn.execute(
                """UPDATE event_task_analyses SET status='running',
                attempt_count=attempt_count+1,next_attempt_at=NULL,lease_until=?,
                error=NULL,updated_at=? WHERE event_id=?""",
                (lease_until, claimed_at, event_id),
            )
            claimed = conn.execute(
                "SELECT * FROM event_task_analyses WHERE event_id=?", (event_id,)
            ).fetchone()
        return self._decode_task_analysis(claimed)

    def complete_task_analysis(
        self,
        event_id: str,
        analysis: dict[str, Any],
        *,
        status: str = "succeeded",
    ) -> bool:
        completed_statuses = {
            "succeeded",
            "succeeded_no_task",
            "skipped_privacy",
            "skipped_empty",
            "skipped_no_cloud_consent",
            "skipped_not_task_candidate",
            "publish_pending",
        }
        if status not in completed_statuses:
            raise ValueError(f"Unsupported completed analysis status: {status}")
        with self.transaction() as conn:
            cursor = conn.execute(
                """UPDATE event_task_analyses SET status=?,analysis_json=?,error=NULL,
                next_attempt_at=NULL,lease_until=NULL,updated_at=? WHERE event_id=?""",
                (status, canonical_json(analysis), now_iso(), event_id),
            )
            return cursor.rowcount > 0

    def fail_task_analysis(
        self,
        event_id: str,
        error: str,
        *,
        retryable: bool = True,
        next_attempt_at: str | None = None,
    ) -> bool:
        status = "failed_retryable" if retryable else "failed_terminal"
        with self.transaction() as conn:
            cursor = conn.execute(
                """UPDATE event_task_analyses SET status=?,error=?,next_attempt_at=?,
                lease_until=NULL,updated_at=? WHERE event_id=?""",
                (
                    status,
                    str(error)[:2000],
                    next_attempt_at if retryable else None,
                    now_iso(),
                    event_id,
                ),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _decode_task_analysis(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["analysis"] = json.loads(item.pop("analysis_json"))
        item["cloud_consent"] = bool(item["cloud_consent"])
        return item

    def task_analysis(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM event_task_analyses WHERE event_id=?", (event_id,)
            ).fetchone()
        return self._decode_task_analysis(row)

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM settings WHERE key=?", (str(key),)
            ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_setting(self, key: str, value: Any) -> None:
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,updated_at=excluded.updated_at""",
                (str(key), canonical_json(value), timestamp),
            )

    @staticmethod
    def _decode_canonical_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        remote_json = item.pop("last_remote_json")
        item["last_remote"] = json.loads(remote_json) if remote_json else None
        return item

    def upsert_canonical_task(
        self,
        task_id: str,
        *,
        title: str,
        description: str | None = None,
        domain: str = "uncategorized",
        project: str | None = None,
        stage: str = "unknown",
        progress_percent: int | None = None,
        priority: str = "none",
        due_at: str | None = None,
        confidence: float = 0.0,
        freetodo_todo_id: int | None = None,
        freetodo_uid: str | None = None,
        last_remote: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        record_status: str = "active",
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        task_id = str(task_id).strip()
        title = " ".join(str(title).split()).strip()
        if not task_id or not title:
            raise ValueError("task_id and title are required")
        if progress_percent is not None and not 0 <= int(progress_percent) <= 100:
            raise ValueError("progress_percent must be between 0 and 100")
        confidence = max(0.0, min(1.0, float(confidence)))
        timestamp = now_iso()
        seen_at = observed_at or timestamp
        default_uid = f"elfred-task-{task_id}"
        if len(default_uid) > 64:
            default_uid = "elfred-task-" + payload_hash(task_id)[:40]
        uid = (freetodo_uid or default_uid)[:64]
        remote_json = canonical_json(last_remote) if last_remote is not None else None
        remote_hash = payload_hash(self.remote_semantic(last_remote)) if last_remote is not None else None
        with self.transaction() as conn:
            current = conn.execute(
                "SELECT freetodo_uid,metadata_json,last_seen_at FROM canonical_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if current is not None and freetodo_uid is None:
                uid = str(current["freetodo_uid"])
            if current is not None and observed_at is None:
                seen_at = str(current["last_seen_at"])
            metadata_json = (
                str(current["metadata_json"])
                if current is not None and metadata is None
                else canonical_json(metadata or {})
            )
            conn.execute(
                """INSERT INTO canonical_tasks
                (task_id,title,description,domain,project,stage,progress_percent,priority,due_at,
                 confidence,record_status,freetodo_todo_id,freetodo_uid,last_remote_hash,
                 last_remote_json,metadata_json,first_seen_at,last_seen_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET
                title=excluded.title,description=excluded.description,domain=excluded.domain,
                project=excluded.project,stage=excluded.stage,
                progress_percent=excluded.progress_percent,priority=excluded.priority,
                due_at=excluded.due_at,confidence=excluded.confidence,
                record_status=excluded.record_status,
                freetodo_todo_id=COALESCE(excluded.freetodo_todo_id,canonical_tasks.freetodo_todo_id),
                freetodo_uid=COALESCE(excluded.freetodo_uid,canonical_tasks.freetodo_uid),
                last_remote_hash=COALESCE(excluded.last_remote_hash,canonical_tasks.last_remote_hash),
                last_remote_json=COALESCE(excluded.last_remote_json,canonical_tasks.last_remote_json),
                metadata_json=excluded.metadata_json,last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at""",
                (
                    task_id,
                    title,
                    description,
                    domain,
                    project,
                    stage,
                    int(progress_percent) if progress_percent is not None else None,
                    priority,
                    due_at,
                    confidence,
                    record_status,
                    freetodo_todo_id,
                    uid,
                    remote_hash,
                    remote_json,
                    metadata_json,
                    seen_at,
                    seen_at,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM canonical_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        decoded = self._decode_canonical_task(row)
        assert decoded is not None
        return decoded

    def canonical_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return self._decode_canonical_task(row)

    def canonical_task_by_freetodo_id(
        self, freetodo_todo_id: int
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_tasks WHERE freetodo_todo_id=?",
                (int(freetodo_todo_id),),
            ).fetchone()
        return self._decode_canonical_task(row)

    def canonical_task_candidates(
        self,
        limit: int = 50,
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM canonical_tasks"
        params: list[Any] = []
        if not include_archived:
            query += " WHERE record_status='active'"
        query += " ORDER BY last_seen_at DESC,task_id LIMIT ?"
        params.append(max(1, min(1000, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            item
            for row in rows
            if (item := self._decode_canonical_task(row)) is not None
        ]

    def upsert_task_evidence(
        self,
        task_id: str,
        event_id: str,
        observation_key: str,
        *,
        relation: str,
        confidence: float,
        evidence: dict[str, Any],
    ) -> str:
        confidence = max(0.0, min(1.0, float(confidence)))
        evidence_id = "evidence_" + payload_hash(
            [task_id, event_id, observation_key]
        )[:24]
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO task_evidence
                (evidence_id,task_id,event_id,observation_key,relation,confidence,
                 evidence_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id,event_id,observation_key) DO UPDATE SET
                relation=excluded.relation,confidence=excluded.confidence,
                evidence_json=excluded.evidence_json,updated_at=excluded.updated_at""",
                (
                    evidence_id,
                    task_id,
                    event_id,
                    observation_key,
                    relation,
                    confidence,
                    canonical_json(evidence),
                    timestamp,
                    timestamp,
                ),
            )
        return evidence_id

    def task_evidence(
        self,
        task_id: str | None = None,
        event_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM task_evidence"
        clauses: list[str] = []
        params: list[Any] = []
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(task_id)
        if event_id is not None:
            clauses.append("event_id=?")
            params.append(event_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at,evidence_id LIMIT ?"
        params.append(max(1, min(1000, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result

    def events_between(
        self, started_at: str, ended_at: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Return locally captured events in a bounded completed-task window."""

        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM ingested_events
                WHERE created_at>=? AND created_at<=? AND deleted_at IS NULL
                AND status NOT IN ('conflict','privacy_blocked')
                ORDER BY created_at,event_id LIMIT ?""",
                (
                    str(started_at),
                    str(ended_at),
                    max(1, min(2000, int(limit))),
                ),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            row["payload"] = json.loads(row.pop("payload_json"))
            result.append(row)
        return result

    def seed_topic(self, topic_id: str, display_name: str, aliases: list[str]) -> None:
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO topic_registry
                (topic_id,display_name,aliases_json,parent_topic_id,status,source_event_ids_json,created_at,updated_at)
                VALUES(?,?,?,NULL,'active','[]',?,?)""",
                (topic_id, display_name, canonical_json(aliases), timestamp, timestamp),
            )
            for alias in [display_name, *aliases]:
                normalized = self.normalize_topic(alias)
                conn.execute(
                    "INSERT OR IGNORE INTO topic_aliases(normalized_alias,alias,topic_id) VALUES(?,?,?)",
                    (normalized, alias, topic_id),
                )

    @staticmethod
    def normalize_topic(value: str) -> str:
        return "".join(ch for ch in value.casefold().strip() if ch.isalnum())

    def resolve_topic(self, name: str, event_id: str, confidence: float = 1.0) -> dict[str, Any]:
        normalized = self.normalize_topic(name)
        with self.transaction() as conn:
            alias = conn.execute(
                "SELECT topic_id FROM topic_aliases WHERE normalized_alias=?", (normalized,)
            ).fetchone()
            if alias:
                topic_id = alias["topic_id"]
            elif confidence >= 0.85 and normalized:
                topic_id = "topic_" + payload_hash(normalized)[:16]
                timestamp = now_iso()
                conn.execute(
                    """INSERT OR IGNORE INTO topic_registry
                    (topic_id,display_name,aliases_json,parent_topic_id,status,source_event_ids_json,created_at,updated_at)
                    VALUES(?,?, '[]',NULL,'active',?,?,?)""",
                    (topic_id, name.strip(), canonical_json([event_id]), timestamp, timestamp),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO topic_aliases(normalized_alias,alias,topic_id) VALUES(?,?,?)",
                    (normalized, name.strip(), topic_id),
                )
            else:
                topic_id = "topic_inbox"
            conn.execute(
                "INSERT OR REPLACE INTO event_topic_links(event_id,topic_id,confidence) VALUES(?,?,?)",
                (event_id, topic_id, confidence),
            )
            row = conn.execute("SELECT * FROM topic_registry WHERE topic_id=?", (topic_id,)).fetchone()
        result = dict(row)
        result["aliases"] = json.loads(result.pop("aliases_json"))
        result["source_event_ids"] = json.loads(result.pop("source_event_ids_json"))
        return result

    def topics_for_event(self, event_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.*,l.confidence FROM topic_registry r
                JOIN event_topic_links l ON l.topic_id=r.topic_id WHERE l.event_id=?""",
                (event_id,),
            ).fetchall()
        result = []
        for raw in rows:
            item = dict(raw)
            item["aliases"] = json.loads(item.pop("aliases_json"))
            item["source_event_ids"] = json.loads(item.pop("source_event_ids_json"))
            result.append(item)
        return result

    def upsert_remote_link(
        self, kind: str, event_id: str, local_key: str, remote_id: int | None,
        uid: str, status: str, remote: dict[str, Any] | None,
    ) -> str:
        if kind not in {"todo", "journal"}:
            raise ValueError(kind)
        table = f"freetodo_{kind}_links"
        id_column = f"freetodo_{kind}_id"
        link_id = f"{kind}_" + payload_hash([event_id, local_key])[:24]
        timestamp = now_iso()
        remote_json = canonical_json(remote) if remote is not None else None
        remote_hash = payload_hash(self.remote_semantic(remote)) if remote is not None else None
        with self.transaction() as conn:
            conn.execute(
                f"""INSERT INTO {table}
                (link_id,event_id,local_key,{id_column},freetodo_uid,status,last_remote_hash,last_remote_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(event_id,local_key) DO UPDATE SET
                {id_column}=excluded.{id_column},freetodo_uid=excluded.freetodo_uid,
                status=excluded.status,last_remote_hash=excluded.last_remote_hash,
                last_remote_json=excluded.last_remote_json,updated_at=excluded.updated_at""",
                (link_id, event_id, local_key, remote_id, uid, status, remote_hash, remote_json, timestamp, timestamp),
            )
        return link_id

    @staticmethod
    def remote_semantic(remote: dict[str, Any] | None) -> dict[str, Any]:
        if remote is None:
            return {}
        ignored = {"created_at", "updated_at", "deleted_at"}
        return {k: v for k, v in remote.items() if k not in ignored}

    def remote_links(self, event_id: str, kind: str | None = None) -> dict[str, list[dict[str, Any]]]:
        kinds = [kind] if kind else ["todo", "journal", "activity"]
        output: dict[str, list[dict[str, Any]]] = {}
        with self.connect() as conn:
            for current in kinds:
                table = f"freetodo_{current}_links"
                rows = conn.execute(f"SELECT * FROM {table} WHERE event_id=? ORDER BY created_at", (event_id,)).fetchall()
                items = []
                for raw in rows:
                    item = dict(raw)
                    for key in ("last_remote_json", "detail_json"):
                        if key in item and item[key]:
                            item[key[:-5] if key.endswith("_json") else key] = json.loads(item.pop(key))
                    items.append(item)
                output[current] = items
        return output

    def todo_link_by_remote_id(self, todo_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM freetodo_todo_links
                WHERE freetodo_todo_id=? ORDER BY updated_at DESC LIMIT 1""",
                (int(todo_id),),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        remote_json = item.pop("last_remote_json", None)
        item["last_remote"] = json.loads(remote_json) if remote_json else None
        return item

    def all_links(self, kind: str) -> list[dict[str, Any]]:
        if kind not in {"todo", "journal"}:
            raise ValueError(kind)
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM freetodo_{kind}_links WHERE status IN ('synced','manual_modified')").fetchall()
        return [dict(row) for row in rows]

    def set_link_status(self, kind: str, link_id: str, status: str) -> None:
        if kind not in {"todo", "journal", "activity"}:
            raise ValueError(kind)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE freetodo_{kind}_links SET status=?,updated_at=? WHERE link_id=?",
                (status, now_iso(), link_id),
            )

    def upsert_activity(self, event_id: str, detail: dict[str, Any]) -> str:
        local_id = "activity_" + payload_hash(event_id)[:24]
        link_id = "activity_link_" + payload_hash(event_id)[:24]
        timestamp = now_iso()
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO freetodo_activity_links
                (link_id,event_id,local_activity_id,freetodo_activity_id,status,detail_json,created_at,updated_at)
                VALUES(?,?,?,NULL,'local_only',?,?,?)
                ON CONFLICT(event_id) DO UPDATE SET detail_json=excluded.detail_json,updated_at=excluded.updated_at""",
                (link_id, event_id, local_id, canonical_json(detail), timestamp, timestamp),
            )
        return local_id

    def enqueue(self, target: str, event_id: str, payload: dict[str, Any]) -> str:
        if target not in {"memory", "personal_agent"}:
            raise ValueError(target)
        table = "memory_outbox" if target == "memory" else "personal_agent_outbox"
        digest = payload_hash(payload)
        item_id = ("mem_" if target == "memory" else "pa_") + payload_hash([event_id, digest])[:24]
        with self.transaction() as conn:
            conn.execute(
                f"""INSERT OR IGNORE INTO {table}
                (item_id,event_id,contract_version,payload_json,payload_hash,status,created_at)
                VALUES(?,?,'1.0',?,?,'pending',?)""",
                (item_id, event_id, canonical_json(payload), digest, now_iso()),
            )
        return item_id

    def outbox(self, target: str, status: str | None = "pending", limit: int = 100) -> list[dict[str, Any]]:
        if target not in {"memory", "personal_agent"}:
            raise ValueError(target)
        table = "memory_outbox" if target == "memory" else "personal_agent_outbox"
        query = f"SELECT * FROM {table}"
        params: list[Any] = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result = []
        for raw in rows:
            item = dict(raw)
            item["payload"] = json.loads(item.pop("payload_json"))
            result.append(item)
        return result

    def ack_outbox(self, item_id: str) -> bool:
        timestamp = now_iso()
        with self.transaction() as conn:
            changed = 0
            for table in ("memory_outbox", "personal_agent_outbox"):
                cursor = conn.execute(
                    f"UPDATE {table} SET status='acknowledged',acknowledged_at=? WHERE item_id=?",
                    (timestamp, item_id),
                )
                changed += cursor.rowcount
            return changed > 0

    def status(self) -> dict[str, Any]:
        tables = {
            "events": "ingested_events",
            "jobs": "sync_jobs",
            "todos": "freetodo_todo_links",
            "journals": "freetodo_journal_links",
            "activities": "freetodo_activity_links",
            "topics": "topic_registry",
            "memory_outbox": "memory_outbox",
            "personal_agent_outbox": "personal_agent_outbox",
            "task_analyses": "event_task_analyses",
            "canonical_tasks": "canonical_tasks",
            "task_evidence": "task_evidence",
            "skills": "skills",
            "skill_versions": "skill_versions",
            "skill_runs": "skill_runs",
            "skill_feedback": "skill_feedback",
            "skill_task_matches": "skill_task_matches",
        }
        with self.connect() as conn:
            counts = {name: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for name, table in tables.items()}
            states = {
                row["status"]: row["count"]
                for row in conn.execute("SELECT status,count(*) count FROM ingested_events GROUP BY status")
            }
            analysis_states = {
                row["status"]: row["count"]
                for row in conn.execute(
                    "SELECT status,count(*) count FROM event_task_analyses GROUP BY status"
                )
            }
        return {
            "database": str(self.path),
            "counts": counts,
            "event_states": states,
            "analysis_states": analysis_states,
        }

    def audit(self, action: str, target: str | None, detail: dict[str, Any]) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO audit_logs(created_at,action,target,detail_json) VALUES(?,?,?,?)",
                (now_iso(), action, target, canonical_json(detail)),
            )
