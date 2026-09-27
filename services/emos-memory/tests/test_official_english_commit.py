from src.memory_system.workflow import build_default_agent


def test_content_rich_english_turns_are_committed_and_recalled():
    agent = build_default_agent()
    user_id = "pytest-official-english-user"
    session_id = "pytest-official-english-session"

    first = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="I went to a LGBTQ support group yesterday and it was so powerful.",
    )
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="When did I go to the LGBTQ support group?",
    )

    assert first.memory_committed is True
    assert result.recalled_memory is not None
    assert "LGBTQ support group" in result.recalled_memory.text

