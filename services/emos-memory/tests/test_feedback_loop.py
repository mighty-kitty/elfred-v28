from src.memory_system.workflow import build_default_agent


def test_feedback_updates_report_and_candidate_bonus(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "feedback_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "feedback_store.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "memory_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "retrieval_settings.json"))

    agent = build_default_agent()
    user_id = "feedback-user"
    session_id = "feedback-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我一直很想看五月天的现场演唱会。")
    result_before = agent.process_turn(user_id=user_id, session_id=session_id, text="那场一直没看到的演出我到现在还惦记着。")

    assert result_before.retrieval_candidates
    top_candidate = result_before.retrieval_candidates[0]
    feedback_event = agent.repository.record_feedback(
        user_id=user_id,
        session_id=session_id,
        memory_id=top_candidate.memory_id,
        feedback_type="correct",
        query_text="那场一直没看到的演出我到现在还惦记着。",
    )

    assert feedback_event["feedback_type"] == "correct"

    report = agent.repository.get_feedback_report(user_id=user_id, limit=5)
    assert report["summary"]["correct"] == 1

    result_after = agent.process_turn(user_id=user_id, session_id=session_id, text="我还是很想去看五月天。")
    assert result_after.retrieval_candidates
    assert result_after.retrieval_candidates[0].feedback_bonus > 0
