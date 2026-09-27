from src.memory_system.workflow import build_default_agent


def test_recall_can_use_evidence_span_for_detail_question():
    agent = build_default_agent()
    user_id = "pytest-evidence-recall-user"
    session_id = "pytest-evidence-recall-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text=(
            "Thanks, Melanie! This necklace is super special to me - a gift from my grandma in my home country, "
            "Sweden. She gave it to me when I was young, and it stands for love, faith and strength."
        ),
    )
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What does the necklace stand for?",
    )

    assert result.recalled_memory is not None
    assert (
        "love, faith and strength" in result.recalled_memory.text
        or any("love, faith and strength" in candidate.text for candidate in result.retrieval_candidates)
    )
