import json

from src.memory_system.workflow import build_default_agent


def test_custom_semantic_alias_file_is_loaded(tmp_path, monkeypatch):
    alias_file = tmp_path / "semantic_aliases.json"
    alias_file.write_text(
        json.dumps({"五月天": ["五月天", "演唱会"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORY_SYSTEM_SEMANTIC_ALIASES_FILE", str(alias_file))

    agent = build_default_agent()
    user_id = "pytest-config-user"
    session_id = "pytest-config-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我很喜欢五月天。")
    result = agent.process_turn(
        user_id=user_id,
        session_id=session_id,
        text="我最近又想去看那场演唱会了。",
    )

    assert result.recalled_memory is not None
    assert "五月天" in result.recalled_memory.text
