from src.memory_system.workflow import build_default_agent


def test_system_report_contains_runtime_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "system_report_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "system_report_memory.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="system-user", session_id="system-session", text="我最近有点压力。")

    report = agent.build_system_report()

    assert report["project"] == "AI Memory System"
    assert report["memory_count"] >= 1
    assert report["user_count"] >= 1
    assert report["retrieval_backend"]
