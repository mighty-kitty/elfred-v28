from src.memory_system.workflow import build_default_agent


def test_session_consolidation_creates_retrievable_summary_memory():
    agent = build_default_agent()
    user_id = "pytest-summary-user"
    session_id = "pytest-summary-session"

    agent.ingest_history_turn(user_id=user_id, session_id=session_id, text="我最近考试压力很大。")
    agent.ingest_history_turn(user_id=user_id, session_id=session_id, text="昨天又加班到凌晨，整个人很疲惫。")
    agent.ingest_history_turn(user_id=user_id, session_id=session_id, text="我总觉得这段时间都在高压里。")

    summary = agent.consolidate_session(user_id=user_id, session_id=session_id, persist=False)

    assert summary is not None
    summaries = [
        entry
        for entry in agent.repository.episodic
        if entry.user_id == user_id and entry.category == "summary"
    ]
    assert summaries
    top_summary = summaries[-1]
    assert top_summary.metadata.get("summary_kind") == "session_chunk"
    assert top_summary.metadata.get("evidence_quotes")
