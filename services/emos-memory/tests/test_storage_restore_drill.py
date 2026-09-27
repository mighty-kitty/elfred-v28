from src.memory_system.workflow import build_default_agent


def test_storage_restore_drill_creates_verified_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "restore_drill.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "restore_drill.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="restore-user", session_id="restore-session", text="I need a backup and restore confidence check.")

    drill = agent.run_storage_restore_drill()

    assert drill["drill_version"] == "storage-restore-drill.v1"
    assert drill["status"] in {"passed", "failed"}
    assert drill["source_backup_path"]
    assert drill["restored_path"]
    assert drill["selection_strategy"] == "latest_healthy_backup"
    assert drill["attempted_candidates"]
    assert drill["agent_handoff"]["drill_status"] == drill["status"]
    assert "backup_exists" in drill["checks"]


def test_storage_restore_drill_prefers_sqlite_and_uses_ascii_safe_restore_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "restore_pref.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "restore_pref.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="restore-pref-user", session_id="restore-pref-session", text="Validate sqlite restore drill on a non-ASCII delivery path.")

    non_ascii_delivery_dir = tmp_path / "交付演练"
    non_ascii_delivery_dir.mkdir(parents=True, exist_ok=True)
    agent.config.paths.delivery_dir = non_ascii_delivery_dir
    agent.repository.config.paths.delivery_dir = non_ascii_delivery_dir

    backup = agent.create_storage_backup()
    assert backup["format"] == "sqlite3"

    drill = agent.run_storage_restore_drill()

    assert drill["status"] == "passed"
    assert drill["source_backup_format"] == "sqlite3"
    assert drill["restored_backend"] == "sqlite"
    assert "交付演练" not in drill["restored_path"]
