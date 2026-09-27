from src.memory_system.config import AppConfig
from src.memory_system.workflow import build_default_agent


def test_unsupported_direct_fact_query_requires_confirmation(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"

    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "unsupported-direct-fact-user"
    session_id = "unsupported-direct-fact-session"
    agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I enjoy ceramic glazing classes on rainy weekends.",
        task_goal="seed unrelated memory",
        force_write=True,
    )

    recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What is my passport number?",
        task_goal="answer only if the memory service has the requested fact",
        context_summary="The only stored memory is unrelated to the requested sensitive identifier.",
        working_memory=["do not treat unrelated memory as the requested fact"],
    )
    payload = recall["payload"]

    assert payload["agent_handoff"]["can_answer_now"] is False
    assert payload["agent_handoff"]["should_confirm"] is True
    assert "retrieved memory may not support the requested fact" in payload["response_contract"]["unsafe_to_assume"]
    assert payload["memory_context"]["query_memory_alignment"]["unsupported_direct_fact_query"] is True


def test_low_anchor_answer_support_risk_requires_confirmation(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"

    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "answer-support-risk-user"
    session_id = "answer-support-risk-session"
    agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="Jolene's mom attended yoga classes with her and helped her feel calm.",
        task_goal="seed nearby but wrong-person memory",
        force_write=True,
    )

    recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What was Deborah's mom passionate about?",
        task_goal="answer only when the recalled evidence anchors the requested person and attribute",
        context_summary="The memory is near the topic but may not support the requested Deborah fact.",
        working_memory=["avoid substituting a nearby person's attribute"],
    )
    payload = recall["payload"]

    guard = payload["memory_context"]["answer_support_risk_guard"]
    assert guard["detected"] is True
    assert "low_query_memory_anchor_overlap" in guard["reason_codes"]
    assert payload["agent_handoff"]["can_answer_now"] is False
    assert payload["agent_handoff"]["should_confirm"] is True
    assert "answer_support_risk_detected" in payload["response_guardrails"]["reason_codes"]
    assert "answer_with_low_anchor_support" in payload["response_contract"]["blocked_behaviors"]
    assert (
        "retrieved memory may not support a direct answer with enough anchors"
        in payload["response_contract"]["unsafe_to_assume"]
    )


def test_relative_temporal_answer_support_risk_requires_confirmation(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"

    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "temporal-answer-support-risk-user"
    session_id = "temporal-answer-support-risk-session"
    agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="Yesterday, James and his family started a road trip with their dogs.",
        task_goal="seed relative temporal memory",
        force_write=True,
    )

    recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="When did James and his family start a road trip?",
        task_goal="answer only when temporal evidence is calibrated enough",
        context_summary="Relative temporal wording should not be treated as a stable date without confirmation.",
        working_memory=["avoid converting relative time into an unsupported absolute date"],
    )
    payload = recall["payload"]

    guard = payload["memory_context"]["answer_support_risk_guard"]
    assert guard["detected"] is True
    assert "relative_temporal_evidence_without_date_anchor" in guard["reason_codes"]
    assert payload["agent_handoff"]["can_answer_now"] is False
    assert payload["agent_handoff"]["should_confirm"] is True
    assert "withhold_or_confirm_low_support_answer" in payload["response_contract"]["required_steps"]


def test_grounded_direct_fact_answer_support_guard_allows_answer(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"

    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "grounded-answer-support-user"
    session_id = "grounded-answer-support-session"
    agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I really want to see The National play live.",
        task_goal="seed grounded preference memory",
        force_write=True,
    )

    recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What live band do I really want to see?",
        task_goal="answer from grounded memory",
        context_summary="Need the preference with memory support.",
        working_memory=["answer should cite memory"],
    )
    payload = recall["payload"]

    guard = payload["memory_context"]["answer_support_risk_guard"]
    assert guard["detected"] is False
    assert guard["recommended_action"] == "allow_grounded_answer"
    assert payload["agent_handoff"]["can_answer_now"] is True
