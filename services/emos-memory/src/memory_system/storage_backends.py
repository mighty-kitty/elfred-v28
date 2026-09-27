from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .emotion_engine import CALM_EMOTION
from .models import utc_now
from .utils.io import read_json, write_json


_SQLITE_AUTO_DISABLED_PATHS: set[str] = set()
_SCHEMA_VERSION = "2"


def _empty_state_payload() -> dict[str, Any]:
    return {
        "episodic": [],
        "emotional": [],
        "semantic": {},
        "dreams": {},
        "memory_blocks": {},
        "idempotency_records": {},
    }


def _payload_has_state(payload: dict[str, Any]) -> bool:
    return any(
        bool(payload.get(key))
        for key in ("episodic", "semantic", "dreams", "memory_blocks")
    )


class BaseStateStore:
    backend_name = "base"

    def __init__(self, path: Path, requested_backend: str, fallback_reason: str | None = None):
        self.path = path
        self.requested_backend = requested_backend
        self.fallback_reason = fallback_reason

    @property
    def resolved_backend_name(self) -> str:
        return self.backend_name

    def load(self, default: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def save(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    def create_backup(self, payload: dict[str, Any], backup_dir: Path) -> Path:
        raise NotImplementedError

    def get_status(self) -> dict[str, object]:
        return {
            "requested_backend": self.requested_backend,
            "resolved_backend": self.resolved_backend_name,
            "path": str(self.path),
            "exists": self.path.exists(),
            "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "fallback_reason": self.fallback_reason,
        }


class JsonStateStore(BaseStateStore):
    backend_name = "json"

    def __init__(self, path: Path, requested_backend: str = "json", fallback_reason: str | None = None):
        super().__init__(path=path, requested_backend=requested_backend, fallback_reason=fallback_reason)

    def load(self, default: dict[str, Any]) -> dict[str, Any]:
        return read_json(self.path, default=default)

    def save(self, payload: dict[str, Any]) -> None:
        write_json(self.path, payload)

    def create_backup(self, payload: dict[str, Any], backup_dir: Path) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"memory_backup_{utc_now().replace(':', '').replace('-', '').replace('.', '')}.json"
        write_json(backup_path, payload)
        return backup_path

    def get_status(self) -> dict[str, object]:
        status = super().get_status()
        status.update({"format": "json"})
        return status


class SQLiteStateStore(BaseStateStore):
    backend_name = "sqlite"

    def __init__(self, path: Path, requested_backend: str = "sqlite", fallback_reason: str | None = None):
        super().__init__(path=path, requested_backend=requested_backend, fallback_reason=fallback_reason)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prepare_storage_path()
        self._initialize()

    def _prepare_storage_path(self) -> None:
        sidecars = [Path(f"{self.path}{suffix}") for suffix in ("-journal", "-wal", "-shm")]
        if self.path.exists() and self.path.stat().st_size == 0:
            for artifact in sidecars:
                try:
                    artifact.unlink(missing_ok=True)
                except PermissionError:
                    continue
            return
        if not self.path.exists():
            for artifact in sidecars:
                try:
                    artifact.unlink(missing_ok=True)
                except PermissionError:
                    continue

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    score REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    emotion TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_user_created ON memories(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_session_created ON memories(session_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS semantic_profiles (
                    user_id TEXT PRIMARY KEY,
                    facts_json TEXT NOT NULL,
                    keywords_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dreams (
                    user_id TEXT PRIMARY KEY,
                    dream_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_blocks (
                    user_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    read_only INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (user_id, label)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_blocks_user_priority
                ON memory_blocks(user_id, priority DESC, updated_at DESC);

                CREATE TABLE IF NOT EXISTS storage_metadata (
                    meta_key TEXT PRIMARY KEY,
                    meta_value_json TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO storage_metadata(meta_key, meta_value_json) VALUES (?, ?)",
                ("schema", json.dumps({"schema_version": _SCHEMA_VERSION, "initialized_at": utc_now()}, ensure_ascii=False)),
            )

    def load(self, default: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            memory_rows = connection.execute(
                """
                SELECT memory_id, text, category, score, user_id, session_id, emotion, tags_json, created_at, metadata_json
                FROM memories
                ORDER BY created_at ASC
                """
            ).fetchall()
            semantic_rows = connection.execute(
                "SELECT user_id, facts_json, keywords_json, updated_at FROM semantic_profiles"
            ).fetchall()
            dream_rows = connection.execute("SELECT user_id, dream_json FROM dreams").fetchall()
            memory_block_rows = connection.execute(
                """
                SELECT user_id, label, value, description, tier, priority, read_only, updated_at, source
                FROM memory_blocks
                ORDER BY user_id ASC, priority DESC, updated_at DESC
                """
            ).fetchall()
            idempotency_row = connection.execute(
                "SELECT meta_value_json FROM storage_metadata WHERE meta_key = ?",
                ("idempotency_records",),
            ).fetchone()

        if not memory_rows and not semantic_rows and not dream_rows and not memory_block_rows:
            return default

        episodic = []
        emotional = []
        for row in memory_rows:
            entry = {
                "memory_id": row["memory_id"],
                "text": row["text"],
                "category": row["category"],
                "score": row["score"],
                "user_id": row["user_id"],
                "session_id": row["session_id"],
                "emotion": row["emotion"],
                "tags": json.loads(row["tags_json"]),
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
            episodic.append(entry)
            if row["emotion"] != CALM_EMOTION:
                emotional.append(entry)

        semantic = {
            row["user_id"]: {
                "user_id": row["user_id"],
                "facts": json.loads(row["facts_json"]),
                "keywords": json.loads(row["keywords_json"]),
                "updated_at": row["updated_at"],
            }
            for row in semantic_rows
        }
        dreams = {row["user_id"]: json.loads(row["dream_json"]) for row in dream_rows}
        memory_blocks: dict[str, list[dict[str, Any]]] = {}
        for row in memory_block_rows:
            memory_blocks.setdefault(row["user_id"], []).append(
                {
                    "user_id": row["user_id"],
                    "label": row["label"],
                    "value": row["value"],
                    "description": row["description"],
                    "tier": row["tier"],
                    "priority": int(row["priority"]),
                    "read_only": bool(row["read_only"]),
                    "updated_at": row["updated_at"],
                    "source": row["source"],
                }
            )
        return {
            "episodic": episodic,
            "emotional": emotional,
            "semantic": semantic,
            "dreams": dreams,
            "memory_blocks": memory_blocks,
            "idempotency_records": json.loads(idempotency_row["meta_value_json"]) if idempotency_row is not None else {},
        }

    def save(self, payload: dict[str, Any]) -> None:
        episodic = payload.get("episodic", [])
        semantic = payload.get("semantic", {})
        dreams = payload.get("dreams", {})
        memory_blocks = payload.get("memory_blocks", {})
        idempotency_records = payload.get("idempotency_records", {})
        metadata_payload = {
            "schema_version": _SCHEMA_VERSION,
            "last_saved_at": utc_now(),
            "memory_count": len(episodic),
            "semantic_profile_count": len(semantic),
            "dream_count": len(dreams),
            "memory_block_count": sum(len(items) for items in memory_blocks.values() if isinstance(items, list)),
            "idempotency_record_count": len(idempotency_records) if isinstance(idempotency_records, dict) else 0,
        }

        with self._connect() as connection:
            connection.execute("BEGIN")
            connection.execute("DELETE FROM memories")
            connection.execute("DELETE FROM semantic_profiles")
            connection.execute("DELETE FROM dreams")
            connection.execute("DELETE FROM memory_blocks")

            connection.executemany(
                """
                INSERT INTO memories (
                    memory_id, text, category, score, user_id, session_id, emotion, tags_json, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["memory_id"],
                        item["text"],
                        item["category"],
                        item["score"],
                        item["user_id"],
                        item["session_id"],
                        item["emotion"],
                        json.dumps(item.get("tags", []), ensure_ascii=False),
                        item["created_at"],
                        json.dumps(item.get("metadata", {}), ensure_ascii=False),
                    )
                    for item in episodic
                ],
            )

            connection.executemany(
                """
                INSERT INTO semantic_profiles (user_id, facts_json, keywords_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        json.dumps(item.get("facts", {}), ensure_ascii=False),
                        json.dumps(item.get("keywords", {}), ensure_ascii=False),
                        item["updated_at"],
                    )
                    for user_id, item in semantic.items()
                ],
            )

            connection.executemany(
                "INSERT INTO dreams (user_id, dream_json) VALUES (?, ?)",
                [
                    (user_id, json.dumps(item, ensure_ascii=False))
                    for user_id, item in dreams.items()
                ],
            )
            connection.executemany(
                """
                INSERT INTO memory_blocks (
                    user_id, label, value, description, tier, priority, read_only, updated_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        item["label"],
                        item["value"],
                        item.get("description", ""),
                        item.get("tier", "custom"),
                        int(item.get("priority", 0)),
                        1 if item.get("read_only", False) else 0,
                        item["updated_at"],
                        item.get("source", "agent"),
                    )
                    for user_id, items in memory_blocks.items()
                    if isinstance(items, list)
                    for item in items
                ],
            )
            connection.execute(
                "INSERT OR REPLACE INTO storage_metadata(meta_key, meta_value_json) VALUES (?, ?)",
                ("state", json.dumps(metadata_payload, ensure_ascii=False)),
            )
            connection.execute(
                "INSERT OR REPLACE INTO storage_metadata(meta_key, meta_value_json) VALUES (?, ?)",
                ("idempotency_records", json.dumps(idempotency_records if isinstance(idempotency_records, dict) else {}, ensure_ascii=False)),
            )
            connection.commit()

    def create_backup(self, payload: dict[str, Any], backup_dir: Path) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"memory_backup_{utc_now().replace(':', '').replace('-', '').replace('.', '')}.sqlite3"
        self.save(payload)
        temp_runtime_dir = Path(tempfile.gettempdir()) / "EMOS" / "runtime"
        temp_runtime_dir.mkdir(parents=True, exist_ok=True)
        temp_backup_path = temp_runtime_dir / backup_path.name
        temp_backup_path.unlink(missing_ok=True)
        with self._connect() as source_connection:
            with sqlite3.connect(str(temp_backup_path)) as backup_connection:
                source_connection.backup(backup_connection)
        shutil.copy2(temp_backup_path, backup_path)
        return backup_path

    def get_status(self) -> dict[str, object]:
        status = super().get_status()
        metadata_payload: dict[str, object] = {}
        journal_mode = "unknown"
        if self.path.exists():
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT meta_value_json FROM storage_metadata WHERE meta_key = ?",
                    ("state",),
                ).fetchone()
                if row is not None:
                    metadata_payload = json.loads(row["meta_value_json"])
                journal_row = connection.execute("PRAGMA journal_mode").fetchone()
                if journal_row is not None:
                    journal_mode = journal_row[0]
        status.update(
            {
                "format": "sqlite",
                "journal_mode": journal_mode,
                "schema_version": metadata_payload.get("schema_version", _SCHEMA_VERSION),
                "last_saved_at": metadata_payload.get("last_saved_at"),
                "memory_count": metadata_payload.get("memory_count", 0),
                "semantic_profile_count": metadata_payload.get("semantic_profile_count", 0),
                "dream_count": metadata_payload.get("dream_count", 0),
                "memory_block_count": metadata_payload.get("memory_block_count", 0),
                "idempotency_record_count": metadata_payload.get("idempotency_record_count", 0),
            }
        )
        return status


def _bootstrap_sqlite_from_json_if_needed(store: SQLiteStateStore, json_path: Path) -> None:
    if not json_path.exists():
        return
    sqlite_payload = store.load(default=_empty_state_payload())
    if _payload_has_state(sqlite_payload):
        return
    json_payload = read_json(json_path, default=_empty_state_payload())
    if not _payload_has_state(json_payload):
        return
    store.save(json_payload)


def build_state_store(storage_backend: str, json_path: Path, sqlite_path: Path):
    backend = storage_backend.lower()
    if backend == "auto":
        try:
            sqlite_key = str(sqlite_path.resolve())
        except Exception:
            sqlite_key = str(sqlite_path)
        if sqlite_key in _SQLITE_AUTO_DISABLED_PATHS:
            return JsonStateStore(json_path, requested_backend="auto", fallback_reason="sqlite auto disabled after previous error for this path")
        try:
            store = SQLiteStateStore(sqlite_path, requested_backend="auto")
            _bootstrap_sqlite_from_json_if_needed(store, json_path)
            return store
        except sqlite3.Error as exc:
            _SQLITE_AUTO_DISABLED_PATHS.add(sqlite_key)
            return JsonStateStore(json_path, requested_backend="auto", fallback_reason=str(exc))
    if backend == "json":
        return JsonStateStore(json_path, requested_backend="json")
    if backend == "sqlite":
        store = SQLiteStateStore(sqlite_path, requested_backend="sqlite")
        _bootstrap_sqlite_from_json_if_needed(store, json_path)
        return store
    raise ValueError(f"Unsupported storage backend: {storage_backend}")
