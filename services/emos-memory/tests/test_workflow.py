from src.memory_system.workflow import build_default_agent


def test_memory_commit_and_reflection():
    agent = build_default_agent()
    user_id = "pytest-user"
    session_id = "pytest-session"

    first = agent.process_turn(user_id=user_id, session_id=session_id, text="我最近考试压力很大。")
    second = agent.process_turn(user_id=user_id, session_id=session_id, text="昨天加班到凌晨，我有点烦。")
    third = agent.process_turn(user_id=user_id, session_id=session_id, text="还是喜欢五月天，听歌会好一点。")

    assert first.memory_committed is True
    assert second.episodic_memory_count >= 2
    assert third.reflection is not None


def test_adjacent_turn_metadata_is_linked_for_session_memories():
    agent = build_default_agent()
    user_id = "pytest-link-user"
    session_id = "pytest-link-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="[9:00 am on 1 Jan, 2026] Caroline: I visited the LGBTQ center before the art show.",
    )
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="[9:01 am on 1 Jan, 2026] Melanie: What inspired you?",
    )

    episodic = [
        entry
        for entry in agent.repository.episodic
        if entry.user_id == user_id and entry.category == "episodic"
    ]

    assert len(episodic) >= 2
    assert episodic[0].metadata.get("next_memory_id") == episodic[1].memory_id
    assert episodic[1].metadata.get("prev_memory_id") == episodic[0].memory_id


def test_question_followup_recall_prefers_adjacent_answer_turn():
    agent = build_default_agent()
    user_id = "pytest-followup-user"
    session_id = "pytest-followup-session"

    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:14 pm on 13 Oct, 2023] Caroline: I went to a poetry reading last Friday. It was really powerful.",
    )
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:15 pm on 13 Oct, 2023] Melanie: What was it about? What made it so special?",
    )
    agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="[7:16 pm on 13 Oct, 2023] Caroline: It was a transgender poetry reading where people shared their stories through poetry.",
    )
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="What was the poetry reading about?",
    )

    assert result.recalled_memory is not None
    assert "transgender poetry reading" in result.recalled_memory.text.lower()
