from src.memory_system.workflow import build_default_agent
import json


def test_feedback_maturity_export_and_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "feedback_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "feedback_store.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "memory_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "retrieval_settings.json"))

    agent = build_default_agent()
    user_id = "feedback-user"
    session_id = "feedback-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="I have been thinking about seeing Mayday live.")
    result_before = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="That concert I missed still bothers me a lot.",
    )

    assert result_before.retrieval_candidates
    top_candidate = result_before.retrieval_candidates[0]
    feedback_event = agent.repository.record_feedback(
        user_id=user_id,
        session_id=session_id,
        memory_id=top_candidate.memory_id,
        feedback_type="correct",
        query_text="That concert I missed still bothers me a lot.",
        signal_weight=1.4,
    )

    assert feedback_event["event_id"].startswith("fb_")
    assert feedback_event["signal_weight"] == 1.4
    assert feedback_event["feedback_origin"] == "explicit"

    report = agent.repository.get_feedback_report(user_id=user_id, limit=5)
    assert report["summary"]["correct"] == 1
    assert report["profile_insights"]["top_memories"]

    result_after = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="I still really want to see Mayday one day.",
    )
    assert result_after.retrieval_candidates[0].feedback_bonus > 0

    export_payload = agent.repository.export_offline_review_dataset(limit=10, user_id=user_id)
    assert export_payload["count"] >= 1
    assert export_payload["manifest"]["labeled_samples"] >= 1
    assert export_payload["manifest"]["languages"]["en"] >= 1
    dataset = json.loads(open(export_payload["path"], "r", encoding="utf-8").read())
    assert "record_types" in dataset["manifest"]
    assert "operations" in dataset["manifest"]
    assert "decision_protocol_versions" in dataset["manifest"]
    assert "guardrailed_samples" in dataset["manifest"]
    assert "ux_guided_samples" in dataset["manifest"]
    assert "response_plan_samples" in dataset["manifest"]
    sample_with_candidates = next(
        sample for sample in dataset["samples"] if sample.get("candidate_training_rows")
    )
    assert sample_with_candidates["candidate_training_rows"][0]["features"]["lexical_score"] >= 0
