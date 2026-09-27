from __future__ import annotations

import sqlite3

from adapter.storage.store import SQLiteStore


def test_legacy_analysis_database_gains_queue_and_skill_foundry_schema(tmp_path):
    database = tmp_path / "legacy-adapter.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE event_task_analyses (
                event_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                cloud_consent INTEGER NOT NULL,
                analysis_json TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    store = SQLiteStore(database)
    with store.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        analysis_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(event_task_analyses)"
            )
        }
        skill_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(skills)"
            )
        }

    assert {
        "skill_builds",
        "skills",
        "skill_versions",
        "skill_source_tasks",
        "skill_runs",
        "skill_feedback",
        "skill_candidate_groups",
        "skill_task_profiles",
        "skill_task_matches",
        "journal_sync_state",
    } <= tables
    assert {
        "attempt_count",
        "next_attempt_at",
        "lease_until",
        "prompt_version",
        "schema_version",
    } <= analysis_columns
    assert "published_version_id" in skill_columns
    assert "auto_execute_enabled" in skill_columns

    with store.connect() as connection:
        journal_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(journal_sync_state)"
            )
        }
    assert {
        "source_hash",
        "candidate_json",
        "last_remote_hash",
        "attempt_count",
        "next_attempt_at",
        "lease_until",
        "lease_token",
        "hardware_status",
        "remote_managed",
    } <= journal_columns


def test_preview_journal_state_gains_fencing_and_ownership_columns(tmp_path):
    database = tmp_path / "legacy-journal-state.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE journal_sync_state (
            journal_date TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            next_attempt_at TEXT,
            lease_until TEXT
            )"""
        )

    store = SQLiteStore(database)
    with store.connect() as connection:
        columns = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(journal_sync_state)")
        }

    assert {
        "requested_generation",
        "processed_generation",
        "lease_token",
        "remote_managed",
    } <= columns.keys()
    assert columns["remote_managed"]["dflt_value"] == "0"


def test_legacy_candidate_status_check_is_expanded_without_losing_rows(
    tmp_path,
):
    database = tmp_path / "legacy-candidate-status.db"
    store = SQLiteStore(database)
    with store.connect() as connection:
        connection.execute("DROP TABLE skill_candidate_groups")
        connection.execute(
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
                'observing','ready','building','draft_ready','failed','ignored'
              ))
            )"""
        )
        connection.execute(
            """INSERT INTO skill_candidate_groups
            (group_id,group_key,label,status,task_ids_json,profile_json,
             created_at,updated_at)
            VALUES('legacy-group','type:document_summary','文档摘要',
            'observing','[1,2]','{}','2026-07-01','2026-07-01')"""
        )
        connection.commit()

    migrated = SQLiteStore(database)
    with migrated.connect() as connection:
        row = connection.execute(
            """SELECT group_id,status FROM skill_candidate_groups
            WHERE group_id='legacy-group'"""
        ).fetchone()
        connection.execute(
            """UPDATE skill_candidate_groups SET status='pattern_forming'
            WHERE group_id='legacy-group'"""
        )
        updated = connection.execute(
            """SELECT status FROM skill_candidate_groups
            WHERE group_id='legacy-group'"""
        ).fetchone()

    assert dict(row) == {
        "group_id": "legacy-group",
        "status": "observing",
    }
    assert updated["status"] == "pattern_forming"
