from src.memory_system.workflow import build_default_agent


def test_process_result_contains_ranked_retrieval_trace():
    agent = build_default_agent()
    user_id = "pytest-trace-user"
    session_id = "pytest-trace-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我孤独的时候总会听五月天。")
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="今天心情一般，我又想去听那支我最常提的乐队。",
    )

    assert result.retrieval_candidates
    top_candidate = result.retrieval_candidates[0]
    assert top_candidate.backend == "embedding_rerank"
    assert "五月天" in top_candidate.text
    assert top_candidate.score > 0
    assert top_candidate.semantic_score >= 0
    assert top_candidate.embedding_score >= 0
    assert top_candidate.recency_bonus >= 0
