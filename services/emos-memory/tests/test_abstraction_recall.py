from src.memory_system.workflow import build_default_agent


def test_recall_supports_future_intent_and_regret_queries():
    agent = build_default_agent()
    user_id = "pytest-intent-user"
    session_id = "pytest-intent-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我最近一直想去看五月天的现场。")
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="那场没看到的演出我到现在还惦记着。",
    )

    assert result.recalled_memory is not None
    assert "五月天" in result.recalled_memory.text
    assert result.retrieval_candidates[0].abstraction_bonus > 0


def test_recall_supports_failure_generalization_queries():
    agent = build_default_agent()
    user_id = "pytest-generalization-user"
    session_id = "pytest-generalization-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="那次考试没发挥好之后，我总担心之后也会失手。",
    )
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="我现在一碰到类似测试，就会想到之前那次失手。",
    )

    assert result.recalled_memory is not None
    assert "考试" in result.recalled_memory.text
    assert result.retrieval_candidates[0].abstraction_hits

