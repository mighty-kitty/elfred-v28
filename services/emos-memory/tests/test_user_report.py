from src.memory_system.workflow import build_default_agent


def test_user_report_contains_summary_fields():
    agent = build_default_agent()
    user_id = "pytest-report-user"
    session_id = "pytest-report-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="最近考试压力很大。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="昨晚又有点失眠。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="我有时候也会听五月天。")

    report = agent.generate_user_report(user_id=user_id, limit=5)

    assert report["user_id"] == user_id
    assert report["memory_count"] >= 3
    assert report["top_emotions"]
    assert report["recent_memories"]
    assert report["retrieval_backend"]
