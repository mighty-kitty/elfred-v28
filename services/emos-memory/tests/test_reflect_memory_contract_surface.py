from src.memory_system.config import AppConfig
from src.memory_system.workflow import build_default_agent


def test_reflect_memory_execution_surface_contract(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"

    agent = build_default_agent(config=config)
    user_id = "reflect-contract-user"
    session_id = "reflect-contract-session"
    agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I prefer afternoon focus blocks for deep writing work.",
        task_goal="maintain stable user preferences",
    )

    reflection = agent.reflect_memory(user_id=user_id, session_id=session_id, persist=False)
    payload = reflection["payload"]

    assert payload["execution_policy"]["policy_version"] == "memory-reflection-execution-policy.v1"
    assert payload["policy_input"]["service_operation"] == "reflect_memory"
    assert payload["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert payload["execution_surface"]["policy_input"] == payload["policy_input"]
    assert payload["execution_surface"]["execution_policy"] == payload["execution_policy"]
    assert payload["execution_surface"]["action_surface"] == payload["action_surface"]
    assert payload["execution_surface"]["agent_handoff"] == payload["agent_handoff"]
