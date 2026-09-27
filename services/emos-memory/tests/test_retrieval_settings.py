import json

from src.memory_system.retrieval_assets import normalize_retrieval_settings
from src.memory_system.workflow import build_default_agent


def test_custom_retrieval_settings_file_is_loaded(tmp_path, monkeypatch):
    settings_file = tmp_path / "retrieval_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "backend": "lexical",
                "weights": {
                    "lexical": 1.0,
                    "fuzzy": 0.0,
                    "concept": 0.5,
                    "tag": 0.2,
                    "emotion": 0.1,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(settings_file))

    agent = build_default_agent()
    user_id = "pytest-retrieval-settings-user"
    session_id = "pytest-retrieval-settings-session"

    agent.process_turn(user_id=user_id, session_id=session_id, text="我总会听五月天。")
    result = agent.process_turn(user_id=user_id, session_id=session_id, text="我又想听那支乐队了。")

    assert result.recalled_memory is not None
    assert "五月天" in result.recalled_memory.text


def test_prefilter_settings_are_normalized():
    settings = normalize_retrieval_settings(
        {
            "backend": "hybrid",
            "prefilter": {
                "enabled": True,
                "min_records": 20,
                "candidate_pool": 64,
                "recency_pool": 7,
            },
        }
    )

    assert settings["prefilter"] == {
        "enabled": True,
        "min_records": 20,
        "candidate_pool": 64,
        "recency_pool": 7,
    }
