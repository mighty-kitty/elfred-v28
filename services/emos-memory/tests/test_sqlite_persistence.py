from src.memory_system.workflow import build_default_agent


def test_sqlite_backend_persists_state_across_agent_instances(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "memory_store.sqlite3"
    monkeypatch.setenv("MEMORY_SYSTEM_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(sqlite_path))

    first_agent = build_default_agent()
    first_agent.process_turn(
        user_id="sqlite-user",
        session_id="sqlite-session",
        text="我最近考试压力有点大。",
    )

    second_agent = build_default_agent()
    snapshot = second_agent.get_user_snapshot(user_id="sqlite-user", limit=10)

    assert snapshot["memory_count"] >= 1
    assert snapshot["memories"]
