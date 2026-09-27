from src.memory_system.workflow import build_default_agent


def test_snapshot_includes_profile_memories_and_dream():
    agent = build_default_agent()
    user_id = "pytest-snapshot-user"
    session_id = "pytest-snapshot-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="最近考试压力很大。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="昨天又有点失眠。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="我还是想把那次考试处理好。")

    snapshot = agent.get_user_snapshot(user_id=user_id, limit=5)

    assert snapshot["user_id"] == user_id
    assert snapshot["memory_count"] >= 3
    assert snapshot["dream"] is not None
    assert snapshot["memories"]
