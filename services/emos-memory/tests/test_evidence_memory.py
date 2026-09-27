from src.memory_system.workflow import build_default_agent


def test_long_turn_generates_evidence_memory_entries():
    agent = build_default_agent()
    user_id = "pytest-evidence-user"
    session_id = "pytest-evidence-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text=(
            "Thanks, Melanie! This necklace is super special to me - a gift from my grandma in my home country, "
            "Sweden. She gave it to me when I was young, and it stands for love, faith and strength."
        ),
    )

    evidence_entries = [
        entry
        for entry in agent.repository.episodic
        if entry.user_id == user_id and entry.category == "evidence"
    ]
    assert evidence_entries
    assert any("Sweden" in entry.text or "love, faith and strength" in entry.text for entry in evidence_entries)


def test_evidence_memory_ignores_question_only_and_image_query_suffix():
    agent = build_default_agent()
    user_id = "pytest-evidence-clean-user"
    session_id = "pytest-evidence-clean-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text=(
            "[1:00 pm on 1 July, 2023] Melanie: What kind of books you got in your library? "
            "image: a bookshelf query: books library"
        ),
    )

    evidence_entries = [
        entry
        for entry in agent.repository.episodic
        if entry.user_id == user_id and entry.category == "evidence"
    ]
    assert not evidence_entries
