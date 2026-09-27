from src.memory_system.workflow import build_default_agent


def test_recall_supports_paraphrase_queries():
    agent = build_default_agent()
    user_id = "pytest-recall-user"
    session_id = "pytest-recall-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我孤独的时候总会听五月天。")
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="今天心情一般，我又想去听那支我最常提的乐队。",
    )

    assert result.recalled_memory is not None
    assert "五月天" in result.recalled_memory.text
