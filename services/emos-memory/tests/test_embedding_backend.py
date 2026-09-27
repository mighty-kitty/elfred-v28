from src.memory_system.workflow import build_default_agent


def test_embedding_rerank_backend_exposes_embedding_and_rerank_scores():
    agent = build_default_agent()
    user_id = "pytest-embedding-user"
    session_id = "pytest-embedding-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我最近一直想去看五月天的现场。")
    agent.process_turn(user_id=user_id, session_id=session_id, text="上次没抢到票我遗憾了很久。")
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="那场没看到的演出我到现在还惦记着。",
    )

    assert result.retrieval_candidates
    top_candidate = result.retrieval_candidates[0]
    assert top_candidate.backend == "embedding_rerank"
    assert top_candidate.embedding_score != 0
    assert top_candidate.rerank_bonus > 0
    assert "五月天" in top_candidate.surface_text
