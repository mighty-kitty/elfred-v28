from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from adapter.contracts import payload_hash
from adapter.identity import (
    DATABASE_FILENAME,
    adapter_database_path,
    migrate_persisted_identity,
    resolve_adapter_database_path,
)


def _previous_product() -> str:
    return bytes.fromhex("616c66726564").decode("ascii")


def _previous_database(data_dir: Path) -> Path:
    return data_dir / f"{_previous_product()}_adapter.db"


def _create_relationship_database(path: Path) -> dict[str, object]:
    previous = _previous_product()
    event_id = f"{previous}-event"
    payload = {
        "schema_version": "1.0",
        "producer": f"{previous}_desktop_observer",
        "event": {
            "event_id": event_id,
            "source": f"{previous}_desktop_observer",
            "content": {"summary": f"{previous.title()} context"},
        },
    }
    outbox_payload = {
        "event_id": event_id,
        "product": previous.title(),
        "summary": f"{previous.title()} memory",
    }
    remote = {
        "uid": f"{previous}-todo",
        "name": f"{previous.title()} task",
        "description": f"Notes about {previous.title()}",
    }
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE ingested_events (
              event_id TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              payload_hash TEXT NOT NULL
            );
            CREATE TABLE event_refs (
              event_id TEXT NOT NULL REFERENCES ingested_events(event_id)
            );
            CREATE TABLE memory_outbox (
              item_id TEXT PRIMARY KEY,
              event_id TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              payload_hash TEXT NOT NULL
            );
            CREATE TABLE freetodo_todo_links (
              link_id TEXT PRIMARY KEY,
              event_id TEXT NOT NULL,
              local_key TEXT NOT NULL,
              freetodo_uid TEXT NOT NULL,
              last_remote_json TEXT,
              last_remote_hash TEXT
            );
            CREATE TABLE user_content (
              id INTEGER PRIMARY KEY,
              title TEXT,
              notes TEXT,
              log_body TEXT,
              summary TEXT,
              comment TEXT,
              log_json TEXT
            );
            CREATE TABLE skill_versions (
              version_id TEXT PRIMARY KEY,
              skill_markdown TEXT NOT NULL,
              workflow_json TEXT NOT NULL
            );
            CREATE TABLE migration_batches (
              batch_id TEXT PRIMARY KEY,
              imported_event_ids_json TEXT NOT NULL,
              report_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO ingested_events VALUES(?,?,?)",
            (event_id, json.dumps(payload), "stale-event-hash"),
        )
        connection.execute("INSERT INTO event_refs VALUES(?)", (event_id,))
        connection.execute(
            "INSERT INTO memory_outbox VALUES(?,?,?,?)",
            (
                "mem_stale",
                event_id,
                json.dumps(outbox_payload),
                "stale-outbox-hash",
            ),
        )
        connection.execute(
            "INSERT INTO freetodo_todo_links VALUES(?,?,?,?,?,?)",
            (
                "todo_stale",
                event_id,
                f"{previous}-local",
                f"{previous}-todo",
                json.dumps(remote),
                "stale-remote-hash",
            ),
        )
        connection.execute(
            "INSERT INTO user_content VALUES(1,?,?,?,?,?,?)",
            (
                *(
                    f"{previous.title()} {label}"
                    for label in ("title", "notes", "log", "summary", "comment")
                ),
                f"{previous.title()} malformed JSON log",
            ),
        )
        connection.execute(
            "INSERT INTO skill_versions VALUES(?,?,?)",
            (
                f"{previous}-version",
                f"# {previous.title()} skill body",
                json.dumps(
                    {
                        "taskId": f"{previous}-task",
                        "description": f"{previous.title()} workflow",
                        "variables": {
                            f"{previous.title()}Key": f"{previous.title()} value"
                        },
                        "steps": [
                            {
                                "comment": f"{previous.title()} comment",
                                "source": f"{previous.title()} manual",
                            }
                        ],
                    }
                ),
            ),
        )
        connection.execute(
            "INSERT INTO migration_batches VALUES(?,?,?)",
            (
                f"{previous}-batch",
                json.dumps([event_id, f"{previous}-second-event"]),
                json.dumps({"summary": f"{previous.title()} batch report"}),
            ),
        )
        connection.commit()
    return {
        "payload": payload,
        "outbox_payload": outbox_payload,
        "remote": remote,
    }


def test_database_filename_content_hashes_and_relationships_migrate(
    tmp_path: Path,
) -> None:
    previous_path = _previous_database(tmp_path)
    _create_relationship_database(previous_path)

    resolved = adapter_database_path(tmp_path)

    assert resolved == tmp_path / DATABASE_FILENAME
    assert resolved.is_file()
    assert not previous_path.exists()
    with closing(sqlite3.connect(resolved)) as connection:
        connection.row_factory = sqlite3.Row
        event = connection.execute("SELECT * FROM ingested_events").fetchone()
        reference = connection.execute("SELECT * FROM event_refs").fetchone()
        outbox = connection.execute("SELECT * FROM memory_outbox").fetchone()
        link = connection.execute("SELECT * FROM freetodo_todo_links").fetchone()
        user_content = connection.execute("SELECT * FROM user_content").fetchone()
        skill_version = connection.execute("SELECT * FROM skill_versions").fetchone()
        migration_batch = connection.execute(
            "SELECT * FROM migration_batches"
        ).fetchone()
        marker = connection.execute(
            "SELECT value FROM elfred_identity_metadata WHERE key='identity_version'"
        ).fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    migrated_event = json.loads(event["payload_json"])
    migrated_outbox = json.loads(outbox["payload_json"])
    migrated_remote = json.loads(link["last_remote_json"])
    migrated_workflow = json.loads(skill_version["workflow_json"])
    migrated_batch_event_ids = json.loads(migration_batch["imported_event_ids_json"])
    migrated_batch_report = json.loads(migration_batch["report_json"])
    assert event["event_id"] == "elfred-event"
    assert reference["event_id"] == "elfred-event"
    assert migrated_event["producer"] == "elfred_desktop_observer"
    assert migrated_event["event"]["event_id"] == "elfred-event"
    assert migrated_event["event"]["source"] == "elfred_desktop_observer"
    assert migrated_event["event"]["content"]["summary"] == "Alfred context"
    assert event["payload_hash"] == payload_hash(
        {
            "schema_version": migrated_event["schema_version"],
            "producer": migrated_event["producer"],
            "event": migrated_event["event"],
        }
    )
    assert outbox["payload_hash"] == payload_hash(migrated_outbox)
    assert (
        outbox["item_id"]
        == "mem_" + payload_hash(["elfred-event", outbox["payload_hash"]])[:24]
    )
    assert migrated_outbox == {
        "event_id": "elfred-event",
        "product": "Elfred",
        "summary": "Alfred memory",
    }
    assert link["freetodo_uid"] == "elfred-todo"
    assert migrated_remote == {
        "uid": "elfred-todo",
        "name": "Alfred task",
        "description": "Notes about Alfred",
    }
    assert link["last_remote_hash"] == payload_hash(migrated_remote)
    assert (
        link["link_id"] == "todo_" + payload_hash(["elfred-event", "elfred-local"])[:24]
    )
    assert tuple(user_content)[1:] == (
        *(
            f"Alfred {label}"
            for label in ("title", "notes", "log", "summary", "comment")
        ),
        "Alfred malformed JSON log",
    )
    assert skill_version["version_id"] == "elfred-version"
    assert skill_version["skill_markdown"] == "# Alfred skill body"
    assert migrated_workflow == {
        "taskId": "elfred-task",
        "description": "Alfred workflow",
        "variables": {"AlfredKey": "Alfred value"},
        "steps": [{"comment": "Alfred comment", "source": "Alfred manual"}],
    }
    assert migration_batch["batch_id"] == "elfred-batch"
    assert migrated_batch_event_ids == ["elfred-event", "elfred-second-event"]
    assert migrated_batch_report == {"summary": "Alfred batch report"}
    assert marker["value"] == "2"


def test_identity_migration_is_marked_and_idempotent(tmp_path: Path) -> None:
    database = _previous_database(tmp_path)
    _create_relationship_database(database)
    current = adapter_database_path(tmp_path)

    report = migrate_persisted_identity(current)

    assert report["already_current"] is True
    assert report["changed_rows"] == 0


def test_version_one_marker_upgrades_without_rewriting_user_content(
    tmp_path: Path,
) -> None:
    database = tmp_path / DATABASE_FILENAME
    previous = _previous_product()
    workflow = {
        "taskId": f"{previous}-task",
        "description": f"{previous.title()} workflow",
        "steps": [{"comment": f"{previous.title()} comment"}],
    }
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            """
            CREATE TABLE elfred_identity_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE skill_versions (
              version_id TEXT PRIMARY KEY,
              skill_markdown TEXT NOT NULL,
              workflow_json TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO elfred_identity_metadata VALUES('identity_version','1')"
        )
        connection.execute(
            "INSERT INTO skill_versions VALUES(?,?,?)",
            (
                "version-current",
                f"# {previous.title()} skill body",
                json.dumps(workflow),
            ),
        )
        connection.commit()

    report = migrate_persisted_identity(database)

    assert report["already_current"] is False
    assert report["changed_rows"] == 1
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        skill_version = connection.execute("SELECT * FROM skill_versions").fetchone()
        marker = connection.execute(
            "SELECT value FROM elfred_identity_metadata WHERE key='identity_version'"
        ).fetchone()
    assert skill_version["skill_markdown"] == "# Alfred skill body"
    assert json.loads(skill_version["workflow_json"]) == {
        "taskId": "elfred-task",
        "description": "Alfred workflow",
        "steps": [{"comment": "Alfred comment"}],
    }
    assert marker["value"] == "2"


def test_unique_collision_rolls_back_without_partial_rewrites(
    tmp_path: Path,
) -> None:
    database = tmp_path / DATABASE_FILENAME
    previous = _previous_product()
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE records(uid TEXT NOT NULL UNIQUE)")
        connection.executemany(
            "INSERT INTO records(uid) VALUES(?)",
            [(f"{previous}-same",), ("elfred-same",)],
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        migrate_persisted_identity(database)

    with closing(sqlite3.connect(database)) as connection:
        values = [
            row[0] for row in connection.execute("SELECT uid FROM records ORDER BY uid")
        ]
        marker_table = connection.execute(
            """SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='elfred_identity_metadata'"""
        ).fetchone()[0]
    assert values == [f"{previous}-same", "elfred-same"]
    assert marker_table == 0


def test_invalid_source_is_not_published_or_deleted(tmp_path: Path) -> None:
    previous_path = _previous_database(tmp_path)
    with closing(sqlite3.connect(previous_path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("CREATE TABLE parent(id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE child(parent_id TEXT REFERENCES parent(id))")
        connection.execute("INSERT INTO child(parent_id) VALUES('missing')")
        connection.commit()

    with pytest.raises(RuntimeError, match="foreign-key"):
        adapter_database_path(tmp_path)

    assert previous_path.is_file()
    assert not (tmp_path / DATABASE_FILENAME).exists()


def test_explicit_previous_filename_resolves_to_current_name(
    tmp_path: Path,
) -> None:
    previous_path = _previous_database(tmp_path)
    _create_relationship_database(previous_path)

    resolved = resolve_adapter_database_path(previous_path)

    assert resolved == tmp_path / DATABASE_FILENAME
    assert resolved.is_file()
    assert not previous_path.exists()
