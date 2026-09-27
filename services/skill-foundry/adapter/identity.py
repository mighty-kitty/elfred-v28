from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any

from adapter.contracts import canonical_json, payload_hash


PRODUCT_NAME = "Elfred"
SERVICE_ID = "elfred_freetodo_adapter"
DATABASE_FILENAME = "elfred_adapter.db"
ENVIRONMENT_PREFIX = "ELFRED"

_PREVIOUS_BRAND = bytes.fromhex("616c66726564").decode("ascii")
_MIGRATION_WAIT_SECONDS = 10.0
_STALE_LOCK_SECONDS = 120.0
_STALE_HASH = "identity-migration-stale"
_BRAND_PATTERN = re.compile(re.escape(_PREVIOUS_BRAND), re.IGNORECASE)
_METADATA_TABLE = "elfred_identity_metadata"
_IDENTITY_VERSION = "2"
_SYSTEM_IDENTIFIER_COLUMNS = frozenset(
    {
        "action_id",
        "attempt_id",
        "batch_id",
        "build_id",
        "decision_id",
        "event_id",
        "evidence_id",
        "feedback_id",
        "freetodo_uid",
        "group_id",
        "idempotency_key",
        "item_id",
        "job_id",
        "journal_id",
        "last_build_id",
        "last_run_id",
        "link_id",
        "local_activity_id",
        "local_key",
        "match_id",
        "parent_topic_id",
        "plan_id",
        "run_id",
        "skill_id",
        "task_id",
        "topic_id",
        "uid",
        "version_id",
    }
)
_TABLE_IDENTITY_COLUMNS = {
    "ingested_events": frozenset({"producer", "source"}),
}
_JSON_IDENTIFIER_COLUMNS = frozenset(
    {
        "blocked_action_ids_json",
        "confirmed_action_ids_json",
        "imported_event_ids_json",
        "requested_action_ids_json",
        "source_event_ids_json",
        "source_task_ids_json",
        "task_ids_json",
    }
)
_JSON_IDENTIFIER_KEYS = _SYSTEM_IDENTIFIER_COLUMNS | frozenset(
    {
        "actionId",
        "actionIds",
        "action_id",
        "action_ids",
        "attemptId",
        "attempt_id",
        "buildId",
        "build_id",
        "eventId",
        "eventIds",
        "event_id",
        "event_ids",
        "freetodoUid",
        "freetodo_uid",
        "groupId",
        "group_id",
        "itemId",
        "item_id",
        "journalId",
        "journal_id",
        "linkId",
        "link_id",
        "localActivityId",
        "localKey",
        "local_activity_id",
        "local_key",
        "matchId",
        "match_id",
        "parentTopicId",
        "parent_topic_id",
        "planId",
        "plan_id",
        "producer",
        "product",
        "runId",
        "run_id",
        "serviceId",
        "service_id",
        "skillId",
        "skill_id",
        "sourceEventIds",
        "sourceTaskIds",
        "source_event_ids",
        "source_task_ids",
        "taskId",
        "taskIds",
        "task_id",
        "task_ids",
        "topicId",
        "topic_id",
        "todoId",
        "todo_id",
        "uid",
        "versionId",
        "version_id",
    }
)


def adapter_database_path(data_dir: str | Path = "data") -> Path:
    data_path = Path(data_dir)
    target = data_path / DATABASE_FILENAME
    if target.exists():
        migrate_persisted_identity(target)
        return target

    previous = data_path / f"{_PREVIOUS_BRAND}_adapter.db"
    if previous.exists():
        _migrate_database(previous, target)
    return target


def resolve_adapter_database_path(path: str | Path) -> Path:
    requested = Path(path)
    previous_name = f"{_PREVIOUS_BRAND}_adapter.db"
    if requested.name.casefold() == previous_name.casefold():
        target = requested.with_name(DATABASE_FILENAME)
        if target.exists():
            migrate_persisted_identity(target)
        elif requested.exists():
            _migrate_database(requested, target)
        return target
    if requested.name.casefold() == DATABASE_FILENAME.casefold():
        return adapter_database_path(requested.parent)
    if requested.exists():
        migrate_persisted_identity(requested)
    return requested


def migrate_persisted_identity(database: str | Path) -> dict[str, Any]:
    path = Path(database)
    if not path.is_file():
        raise FileNotFoundError(path)
    with closing(sqlite3.connect(path, timeout=10.0)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {_quote(_METADATA_TABLE)} (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
                )"""
            )
            current = connection.execute(
                f"SELECT value FROM {_quote(_METADATA_TABLE)} WHERE key=?",
                ("identity_version",),
            ).fetchone()
            if current is not None and str(current[0]) == _IDENTITY_VERSION:
                connection.commit()
                return {
                    "database": str(path.resolve()),
                    "changed_rows": 0,
                    "changed_tables": [],
                    "row_counts": _row_counts(connection),
                    "already_current": True,
                }
            before = _row_counts(connection)
            changed = _rewrite_persisted_values(connection)
            _refresh_dependencies(connection, changed)
            _assert_no_previous_identity(connection)
            after = _row_counts(connection)
            if after != before:
                raise RuntimeError(
                    "database row counts changed during identity migration"
                )
            _assert_database_integrity(connection)
            connection.execute(
                f"""INSERT INTO {_quote(_METADATA_TABLE)}(key,value)
                VALUES(?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                ("identity_version", _IDENTITY_VERSION),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {
        "database": str(path.resolve()),
        "changed_rows": sum(len(rows) for rows in changed.values()),
        "changed_tables": sorted(changed),
        "row_counts": before,
        "already_current": False,
    }


def _migrate_database(previous: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f"{target.name}.migration.lock")
    lock_fd = _acquire_migration_lock(lock_path, target)
    if lock_fd is None:
        return

    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.migrating")
    try:
        if target.exists() or not previous.exists():
            return
        _validate_and_checkpoint(previous)
        _copy_database(previous, temporary)
        migrate_persisted_identity(temporary)
        _validate_database(temporary)
        if target.exists():
            raise RuntimeError(f"database migration target already exists: {target}")
        temporary.replace(target)
        try:
            _validate_database(target)
            previous.unlink()
        except Exception:
            target.unlink(missing_ok=True)
            raise
        for suffix in ("-wal", "-shm"):
            Path(f"{previous}{suffix}").unlink(missing_ok=True)
    finally:
        temporary.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{temporary}{suffix}").unlink(missing_ok=True)
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def _acquire_migration_lock(lock_path: Path, target: Path) -> int | None:
    deadline = time.monotonic() + _MIGRATION_WAIT_SECONDS
    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            return descriptor
        except FileExistsError:
            if target.exists():
                return None
            try:
                if time.time() - lock_path.stat().st_mtime > _STALE_LOCK_SECONDS:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"timed out waiting for database migration lock: {lock_path}"
                )
            time.sleep(0.05)


def _validate_and_checkpoint(path: Path) -> None:
    with closing(sqlite3.connect(path, timeout=10.0)) as connection:
        connection.execute("PRAGMA busy_timeout=10000")
        checkpoint = connection.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
        if checkpoint and int(checkpoint[0]) != 0:
            raise RuntimeError(f"database WAL checkpoint was busy: {path}")
        _assert_database_integrity(connection)


def _copy_database(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source, timeout=10.0)) as source_connection:
        source_connection.execute("PRAGMA busy_timeout=10000")
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)


def _validate_database(path: Path) -> None:
    with closing(sqlite3.connect(path, timeout=10.0)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _assert_database_integrity(connection)


def _assert_database_integrity(connection: sqlite3.Connection) -> None:
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            "database foreign-key check failed during identity migration"
        )
    result = connection.execute("PRAGMA quick_check").fetchall()
    if len(result) != 1 or result[0][0] != "ok":
        raise RuntimeError("database integrity check failed during identity migration")


def _normal_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """SELECT name,sql FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"""
    ).fetchall()
    return [
        str(row[0])
        for row in rows
        if str(row[0]) != _METADATA_TABLE
        and not str(row[1] or "").lstrip().upper().startswith("CREATE VIRTUAL TABLE")
    ]


def _row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        table: int(
            connection.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0]
        )
        for table in _normal_tables(connection)
    }


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_xinfo({_quote(table)})")
        if int(row[6] or 0) == 0
    }


def _migration_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    columns = _table_columns(connection, table)
    table_identity_columns = _TABLE_IDENTITY_COLUMNS.get(table, frozenset())
    return sorted(
        column
        for column in columns
        if column in _SYSTEM_IDENTIFIER_COLUMNS
        or column in table_identity_columns
        or column.endswith("_json")
    )


def _rewrite_persisted_values(
    connection: sqlite3.Connection,
) -> dict[str, dict[int, set[str]]]:
    changed: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for table in _normal_tables(connection):
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if "WITHOUT ROWID" in str(table_sql or "").upper():
            raise RuntimeError(f"unsupported WITHOUT ROWID table: {table}")
        for column in _migration_columns(connection, table):
            rows = connection.execute(
                f"SELECT rowid,{_quote(column)} FROM {_quote(table)} "
                f"WHERE typeof({_quote(column)})='text'"
            ).fetchall()
            for rowid, raw in rows:
                value = str(raw)
                replacement = (
                    _replace_json(value, column)
                    if column.endswith("_json")
                    else _replace_text(value)
                )
                if replacement == value:
                    continue
                connection.execute(
                    f"UPDATE {_quote(table)} SET {_quote(column)}=? WHERE rowid=?",
                    (replacement, rowid),
                )
                changed[table][int(rowid)].add(column)
    return {table: dict(rows) for table, rows in changed.items()}


def _replace_json(value: str, column: str = "") -> str:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return value
    migrated = (
        _replace_json_identifier(decoded)
        if column in _JSON_IDENTIFIER_COLUMNS
        else _replace_json_value(decoded)
    )
    return canonical_json(migrated) if migrated != decoded else value


def _replace_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_replace_json_value(item) for item in value]
    if isinstance(value, dict):
        event_contract = (
            "event_id" in value or "eventId" in value
        ) and "content" in value
        migrated: dict[Any, Any] = {}
        for key, item in value.items():
            is_identifier = isinstance(key, str) and (
                key in _JSON_IDENTIFIER_KEYS or (key == "source" and event_contract)
            )
            migrated[key] = (
                _replace_json_identifier(item)
                if is_identifier
                else _replace_json_value(item)
            )
        return migrated
    return value


def _replace_json_identifier(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_text(value)
    if isinstance(value, list):
        return [
            _replace_text(item) if isinstance(item, str) else _replace_json_value(item)
            for item in value
        ]
    if isinstance(value, dict):
        return _replace_json_value(value)
    return value


def _replace_text(value: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        source = match.group(0)
        if source.isupper():
            return ENVIRONMENT_PREFIX
        if source[:1].isupper():
            return PRODUCT_NAME
        return PRODUCT_NAME.casefold()

    return _BRAND_PATTERN.sub(replacement, value)


def _refresh_dependencies(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
) -> None:
    _refresh_event_hashes(connection, changed)
    _refresh_json_hash(
        connection, changed, "memory_outbox", "payload_json", "payload_hash"
    )
    _refresh_json_hash(
        connection, changed, "personal_agent_outbox", "payload_json", "payload_hash"
    )
    _refresh_remote_hash(connection, changed, "canonical_tasks")
    _refresh_remote_hash(connection, changed, "freetodo_todo_links")
    _refresh_remote_hash(connection, changed, "freetodo_journal_links")
    _refresh_json_hash(
        connection, changed, "hardware_output_plans", "journal_json", "journal_hash"
    )
    _refresh_derived_ids(connection, changed)
    _invalidate_caches(connection, changed)


def _refresh_event_hashes(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
) -> None:
    for table in ("ingested_events", "event_payload_versions"):
        columns = (
            _table_columns(connection, table)
            if table in _normal_tables(connection)
            else set()
        )
        if not {"payload_json", "payload_hash"} <= columns:
            continue
        for rowid, changed_columns in changed.get(table, {}).items():
            if "payload_json" not in changed_columns:
                continue
            raw = connection.execute(
                f"SELECT payload_json FROM {_quote(table)} WHERE rowid=?", (rowid,)
            ).fetchone()[0]
            payload = json.loads(raw)
            stable = {
                "schema_version": payload.get("schema_version"),
                "producer": payload.get("producer"),
                "event": payload.get("event"),
            }
            connection.execute(
                f"UPDATE {_quote(table)} SET payload_hash=? WHERE rowid=?",
                (payload_hash(stable), rowid),
            )


def _refresh_json_hash(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
    table: str,
    json_column: str,
    hash_column: str,
) -> None:
    if table not in changed:
        return
    columns = _table_columns(connection, table)
    if not {json_column, hash_column} <= columns:
        return
    for rowid, changed_columns in changed[table].items():
        if json_column not in changed_columns:
            continue
        raw = connection.execute(
            f"SELECT {_quote(json_column)} FROM {_quote(table)} WHERE rowid=?",
            (rowid,),
        ).fetchone()[0]
        connection.execute(
            f"UPDATE {_quote(table)} SET {_quote(hash_column)}=? WHERE rowid=?",
            (payload_hash(json.loads(raw)), rowid),
        )


def _refresh_remote_hash(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
    table: str,
) -> None:
    if table not in changed:
        return
    columns = _table_columns(connection, table)
    if not {"last_remote_json", "last_remote_hash"} <= columns:
        return
    for rowid, changed_columns in changed[table].items():
        if "last_remote_json" not in changed_columns:
            continue
        raw = connection.execute(
            f"SELECT last_remote_json FROM {_quote(table)} WHERE rowid=?", (rowid,)
        ).fetchone()[0]
        remote = json.loads(raw) if raw else None
        semantic = {
            key: value
            for key, value in (remote or {}).items()
            if key not in {"created_at", "updated_at", "deleted_at"}
        }
        digest = payload_hash(semantic) if remote is not None else None
        connection.execute(
            f"UPDATE {_quote(table)} SET last_remote_hash=? WHERE rowid=?",
            (digest, rowid),
        )


def _refresh_derived_ids(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
) -> None:
    specifications = {
        "event_payload_versions": (
            "version_id",
            lambda row: (
                "ver_" + payload_hash([row["event_id"], row["payload_hash"]])[:24]
            ),
            {"event_id", "payload_json"},
        ),
        "task_evidence": (
            "evidence_id",
            lambda row: (
                "evidence_"
                + payload_hash(
                    [row["task_id"], row["event_id"], row["observation_key"]]
                )[:24]
            ),
            {"task_id", "event_id", "observation_key"},
        ),
        "memory_outbox": (
            "item_id",
            lambda row: (
                "mem_" + payload_hash([row["event_id"], row["payload_hash"]])[:24]
            ),
            {"event_id", "payload_json"},
        ),
        "personal_agent_outbox": (
            "item_id",
            lambda row: (
                "pa_" + payload_hash([row["event_id"], row["payload_hash"]])[:24]
            ),
            {"event_id", "payload_json"},
        ),
        "freetodo_todo_links": (
            "link_id",
            lambda row: (
                "todo_" + payload_hash([row["event_id"], row["local_key"]])[:24]
            ),
            {"event_id", "local_key"},
        ),
        "freetodo_journal_links": (
            "link_id",
            lambda row: (
                "journal_" + payload_hash([row["event_id"], row["local_key"]])[:24]
            ),
            {"event_id", "local_key"},
        ),
        "freetodo_activity_links": (
            "link_id",
            lambda row: "activity_link_" + payload_hash(row["event_id"])[:24],
            {"event_id"},
        ),
    }
    for table, (id_column, factory, dependencies) in specifications.items():
        if table not in changed:
            continue
        columns = _table_columns(connection, table)
        required = (
            dependencies | {id_column, "payload_hash"}
            if "payload_json" in dependencies
            else dependencies | {id_column}
        )
        if not required <= columns:
            continue
        for rowid, changed_columns in changed[table].items():
            if not dependencies.intersection(changed_columns):
                continue
            row = connection.execute(
                f"SELECT * FROM {_quote(table)} WHERE rowid=?", (rowid,)
            ).fetchone()
            connection.execute(
                f"UPDATE {_quote(table)} SET {_quote(id_column)}=? WHERE rowid=?",
                (factory(row), rowid),
            )


def _invalidate_caches(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
) -> None:
    _update_changed_rows(
        connection,
        changed,
        "event_task_analyses",
        {
            "status": "pending",
            "source_hash": _STALE_HASH,
            "attempt_count": 0,
            "next_attempt_at": None,
            "lease_until": None,
            "error": None,
        },
    )
    _update_changed_rows(
        connection,
        changed,
        "journal_sync_state",
        {
            "status": "pending",
            "source_hash": None,
            "candidate_hash": None,
            "candidate_status": "stale",
            "next_attempt_at": None,
            "lease_until": None,
            "lease_token": None,
        },
    )
    _update_changed_rows(
        connection,
        changed,
        "skill_candidate_groups",
        {"last_build_hash": None},
    )
    _update_changed_rows(
        connection,
        changed,
        "skill_task_profiles",
        {"evidence_hash": _STALE_HASH},
    )
    _update_changed_rows(
        connection,
        changed,
        "sync_attempts",
        {"request_hash": None},
    )


def _update_changed_rows(
    connection: sqlite3.Connection,
    changed: dict[str, dict[int, set[str]]],
    table: str,
    values: dict[str, Any],
) -> None:
    if table not in changed:
        return
    columns = _table_columns(connection, table)
    applicable = {key: value for key, value in values.items() if key in columns}
    if not applicable:
        return
    assignments = ",".join(f"{_quote(key)}=?" for key in applicable)
    for rowid in changed[table]:
        connection.execute(
            f"UPDATE {_quote(table)} SET {assignments} WHERE rowid=?",
            (*applicable.values(), rowid),
        )


def _assert_no_previous_identity(connection: sqlite3.Connection) -> None:
    for table in _normal_tables(connection):
        for column in _migration_columns(connection, table):
            rows = connection.execute(
                f"SELECT {_quote(column)} FROM {_quote(table)} "
                f"WHERE typeof({_quote(column)})='text'"
            ).fetchall()
            if column.endswith("_json"):
                changed = any(
                    _replace_json(str(row[0]), column) != str(row[0]) for row in rows
                )
            else:
                changed = any(_replace_text(str(row[0])) != str(row[0]) for row in rows)
            if changed:
                raise RuntimeError(
                    f"previous product identity remains in identifier field {table}.{column}"
                )


def _quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'
