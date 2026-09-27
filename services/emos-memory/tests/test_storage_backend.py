from sqlite3 import OperationalError

from src.memory_system.storage_backends import JsonStateStore, build_state_store


def test_auto_storage_backend_falls_back_to_json(monkeypatch, tmp_path):
    def raise_sqlite_error(*args, **kwargs):
        raise OperationalError("disk I/O error")

    monkeypatch.setattr("src.memory_system.storage_backends.sqlite3.connect", raise_sqlite_error)
    store = build_state_store(
        storage_backend="auto",
        json_path=tmp_path / "memory_store.json",
        sqlite_path=tmp_path / "memory_store.sqlite3",
    )

    assert isinstance(store, JsonStateStore)
    status = store.get_status()
    assert status["resolved_backend"] == "json"
    assert status["fallback_reason"]
