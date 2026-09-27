# -*- coding: utf-8 -*-
"""WP-02: the alembic migration and the app's auto-create must agree exactly."""
import os
import sqlite3
import subprocess
import sys

from app.db import DbStore

GATEWAY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = ("profiles", "runs", "idempotency", "calibrations", "sessions", "feedback",
          "knowledge_sources", "knowledge_documents", "knowledge_chunks",
          "knowledge_jobs", "knowledge_citations")


def _schema(path: str) -> dict:
    connection = sqlite3.connect(path)
    try:
        schema = {}
        for table in TABLES:
            rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
            # column ORDER is not part of the contract: a migration adds columns with
            # ALTER (appended), while a fresh auto-create declares them inline.
            schema[table] = {row[1]: (row[2] or "").upper() for row in rows}
        return schema
    finally:
        connection.close()


def _upgrade(path) -> str:
    env = {**os.environ, "PA_GATEWAY_DB": str(path)}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=GATEWAY_DIR, env=env, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    return (result.stdout or "") + (result.stderr or "")


def test_alembic_upgrade_head_creates_the_same_schema_as_the_app(tmp_path):
    migrated = tmp_path / "migrated.db"
    output = _upgrade(migrated)
    assert "0001" in output, output
    auto = tmp_path / "auto.db"
    DbStore(path=str(auto))  # the app's own startup migration
    assert _schema(str(migrated)) == _schema(str(auto))


def test_migrated_database_is_usable_by_the_store(tmp_path):
    migrated = tmp_path / "usable.db"
    _upgrade(migrated)
    store = DbStore(path=str(migrated))
    profile = store.create_profile(user_id="migrated-user")
    run = store.create_run(profile.pa_id, "hello from a migrated database")
    # the pause flag needs its column to survive the round trip
    store.set_run_paused(run.run_id, True)
    assert store.get_run(run.run_id).paused is True
    assert store.get_profile(profile.pa_id).user_id == "migrated-user"
