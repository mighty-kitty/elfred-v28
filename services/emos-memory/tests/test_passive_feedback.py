from src.memory_system.workflow import build_default_agent


def test_passive_feedback_infers_correction_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "passive_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "passive_feedback.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "passive_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "passive_retrieval.json"))

    agent = build_default_agent()
    user_id = "passive-user"
    session_id = "passive-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="I love going to live shows.")
    agent.process_turn(user_id=user_id, session_id=session_id, text="I still feel bad about the concert I missed.")
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="That missed concert is still the memory that sticks with me.",
    )
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="Not that one, you remembered the wrong event.",
    )

    report = agent.repository.get_feedback_report(user_id=user_id, limit=10)
    assert report["summary"]["incorrect"] >= 1
    assert any(event.get("notes", "").startswith("Passive correction") for event in report["recent_events"])
    assert any(event.get("feedback_origin") == "passive" for event in report["recent_events"])
    export_payload = agent.repository.export_offline_review_dataset(limit=10, user_id=user_id)
    assert export_payload["manifest"]["languages"]["en"] >= 1


def test_passive_feedback_infers_affirmation_signal(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "passive_memory_yes.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "passive_feedback_yes.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "passive_interactions_yes.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "passive_retrieval_yes.json"))

    agent = build_default_agent()
    user_id = "passive-user-yes"
    session_id = "passive-session-yes"

    agent.process_turn(user_id=user_id, session_id=session_id, text="I want to see Mayday live one day.")
    agent.process_turn(user_id=user_id, session_id=session_id, text="Missing that concert still hurts.")
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="That missed Mayday concert still hurts to think about.",
    )
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="Exactly, that's the one I meant.",
    )

    report = agent.repository.get_feedback_report(user_id=user_id, limit=10)
    assert report["summary"]["correct"] >= 1
    assert any(event.get("feedback_origin") == "passive" for event in report["recent_events"])


def test_passive_feedback_supports_chinese_correction(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "passive_memory_zh.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "passive_feedback_zh.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "passive_interactions_zh.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "passive_retrieval_zh.json"))

    agent = build_default_agent()
    user_id = "passive-user-zh"
    session_id = "passive-session-zh"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我一直想去看五月天的现场。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="那场没看到的演出我到现在还记着。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="那场没看到的演出我真的还很遗憾。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="不是这个，你记错了。")

    report = agent.repository.get_feedback_report(user_id=user_id, limit=10)
    assert report["summary"]["incorrect"] >= 1
    assert report["summary"]["passive"] >= 1
    export_payload = agent.repository.export_offline_review_dataset(limit=10, user_id=user_id)
    assert export_payload["manifest"]["languages"]["zh"] >= 1
