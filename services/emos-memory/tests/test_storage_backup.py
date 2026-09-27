from src.memory_system.workflow import build_default_agent


def test_storage_backup_creates_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "storage_backup.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "storage_backup.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="backup-user", session_id="backup-session", text="我最近考试压力有点大。")

    backup = agent.create_storage_backup()

    assert backup["backend"] in {"json", "sqlite"}
    assert backup["backup_mode"] in {"native_backup", "json_fallback", "json_fallback_after_failed_native_verification"}
    assert backup["path"]
    assert backup["format"] in {"json", "sqlite3"}
    assert backup["sha256"]
    assert backup["verification"]["status"] == "verified"
    assert backup["agent_handoff"]["verification_status"] == "verified"
