from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_memory_system_runtime(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "memory_runtime"
    logs_dir = runtime_dir / "logs"
    delivery_dir = logs_dir / "delivery"

    monkeypatch.setenv("MEMORY_SYSTEM_LOGS_DIR", str(logs_dir))
    monkeypatch.setenv("MEMORY_SYSTEM_DELIVERY_DIR", str(delivery_dir))
    data_dir = runtime_dir / "data"
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(data_dir / "memory_store.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(data_dir / "memory_store.sqlite3"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(data_dir / "feedback_store.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(logs_dir / "memory_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_OFFLINE_EVAL_DIR", str(logs_dir / "offline_eval"))

    try:
        from src.memory_system import storage_backends

        storage_backends._SQLITE_AUTO_DISABLED_PATHS.clear()
    except Exception:
        pass
