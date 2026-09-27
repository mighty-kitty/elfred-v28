from pathlib import Path

from src.memory_system import storage_backends
from src.memory_system.workflow import build_default_agent


def test_auto_storage_repairs_zero_byte_sqlite_and_bootstraps_json(tmp_path, monkeypatch):
    json_path = tmp_path / "primary_repair.json"
    sqlite_path = tmp_path / "primary_repair.sqlite3"
    journal_path = Path(f"{sqlite_path}-journal")

    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(json_path))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(sqlite_path))
    monkeypatch.setenv("MEMORY_SYSTEM_STORAGE_BACKEND", "json")

    json_agent = build_default_agent()
    json_agent.process_turn(
        user_id="sqlite-repair-user",
        session_id="sqlite-repair-session",
        text="User prefers black coffee without sugar and no coffee reminders after 9 AM.",
    )
    json_agent.set_memory_block(
        user_id="sqlite-repair-user",
        session_id="sqlite-repair-session",
        label="stable_preferences",
        value="black coffee, no sugar; no coffee reminders after 9 AM",
    )

    sqlite_path.write_bytes(b"")
    journal_path.write_bytes(b"stale-journal")

    storage_backends._SQLITE_AUTO_DISABLED = False
    monkeypatch.setenv("MEMORY_SYSTEM_STORAGE_BACKEND", "auto")

    sqlite_agent = build_default_agent()
    report = sqlite_agent.get_storage_report()

    assert report["resolved_backend"] == "sqlite"
    assert report["primary_mode_status"] == "healthy_primary"
    assert report["primary_storage"]["fallback_active"] is False

    memories = sqlite_agent.repository.list_memories("sqlite-repair-user", limit=10)
    assert any("black coffee" in item.text for item in memories)

    blocks = sqlite_agent.repository.list_memory_blocks("sqlite-repair-user")
    assert any(block.label == "stable_preferences" for block in blocks)


def test_sqlite_backend_persists_memory_blocks(tmp_path, monkeypatch):
    json_path = tmp_path / "sqlite_blocks.json"
    sqlite_path = tmp_path / "sqlite_blocks.sqlite3"

    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(json_path))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(sqlite_path))
    monkeypatch.setenv("MEMORY_SYSTEM_STORAGE_BACKEND", "sqlite")

    agent = build_default_agent()
    agent.set_memory_block(
        user_id="sqlite-block-user",
        session_id="sqlite-block-session",
        label="stable_preferences",
        value="black coffee, no sugar",
    )

    reloaded_agent = build_default_agent()
    report = reloaded_agent.get_storage_report()
    blocks = reloaded_agent.repository.list_memory_blocks("sqlite-block-user")

    assert report["resolved_backend"] == "sqlite"
    assert report["primary_mode_status"] == "healthy_primary"
    assert any(block.label == "stable_preferences" and block.value == "black coffee, no sugar" for block in blocks)
