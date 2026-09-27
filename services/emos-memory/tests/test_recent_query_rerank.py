from src.memory_system.workflow import build_default_agent


def test_recent_query_returns_painting_memory_for_same_subject():
    agent = build_default_agent()
    user_id = "pytest-recent-user"
    session_id = "pytest-recent-session"

    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[1:33 pm on 25 August, 2023] Melanie: Here's a painting I did recently. image: a photo of a painting of a sunflower on a canvas",
    )
    agent.ingest_history_turn(
        user_id=user_id,
        session_id=session_id,
        text="[10:31 am on 13 October, 2023] Melanie: Yeah, here's one I did last week. It's inspired by the sunsets. image: a photo of a painting of a sunset with a pink sky",
    )

    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What did Melanie paint recently?",
        persist=False,
    )

    assert result.recalled_memory is not None
    assert "melanie:" in result.recalled_memory.text.lower()
    assert "paint" in result.recalled_memory.text.lower()
