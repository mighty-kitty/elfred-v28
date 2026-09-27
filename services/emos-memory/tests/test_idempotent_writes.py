from src.memory_system.config import AppConfig
from src.memory_system.api.server import _agent_hints_with_operation_ids
from src.memory_system.workflow import build_default_agent


def _config(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"
    return config


def test_write_idempotency_key_replays_same_result_without_duplicate_write(tmp_path):
    config = _config(tmp_path)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "idempotency-user"
    session_id = "idempotency-session"
    hints = {"idempotency_key": "write-op-001"}

    first = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My preferred deployment window is Friday morning.",
        force_write=True,
        agent_hints=hints,
    )["payload"]
    second = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My preferred deployment window is Friday morning.",
        force_write=True,
        agent_hints=hints,
    )["payload"]

    assert first["memory_written"] is True
    assert second["memory_written"] is True
    assert second["memory_id"] == first["memory_id"]
    assert second["next_action"] == first["next_action"]
    assert second["decision_type"] == first["decision_type"]
    assert second["idempotency"]["status"] == "replayed"
    assert second["idempotency"]["replayed"] is True
    assert second["idempotency"]["side_effect_replayed"] is False
    assert len(agent.repository.list_memories(user_id, limit=10)) == 1


def test_write_idempotency_key_replay_survives_repository_reload(tmp_path):
    config = _config(tmp_path)
    first_agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "idempotency-persist-user"
    session_id = "idempotency-persist-session"
    hints = {"operation_id": "write-op-persist-001"}

    first = first_agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My recurring architecture review is every Tuesday.",
        force_write=True,
        agent_hints=hints,
    )["payload"]

    second_agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    replay = second_agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My recurring architecture review is every Tuesday.",
        force_write=True,
        agent_hints=hints,
    )["payload"]

    assert replay["idempotency"]["status"] == "replayed"
    assert replay["memory_id"] == first["memory_id"]
    assert len(second_agent.repository.list_memories(user_id, limit=10)) == 1


def test_write_idempotency_key_rejects_payload_mismatch(tmp_path):
    config = _config(tmp_path)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "idempotency-conflict-user"
    session_id = "idempotency-conflict-session"
    hints = {"idempotency_key": "write-op-conflict-001"}

    first = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My preferred incident channel is #ops-red.",
        force_write=True,
        agent_hints=hints,
    )["payload"]
    conflict = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My preferred incident channel is #ops-blue.",
        force_write=True,
        agent_hints=hints,
    )["payload"]

    assert first["memory_written"] is True
    assert conflict["memory_written"] is False
    assert conflict["next_action"] == "idempotency_key_conflict"
    assert conflict["write_policy"]["policy"] == "idempotency_key_conflict"
    assert conflict["idempotency"]["status"] == "conflict"
    assert "write_memory" in conflict["execution_guardrails"]["blocked_operations"]
    assert len(agent.repository.list_memories(user_id, limit=10)) == 1


def test_api_request_idempotency_fields_merge_into_agent_hints():
    hints = _agent_hints_with_operation_ids(
        {"source_adapter": "test-client"},
        operation_id="api-operation-001",
        idempotency_key="api-idempotency-001",
    )

    assert hints["source_adapter"] == "test-client"
    assert hints["operation_id"] == "api-operation-001"
    assert hints["idempotency_key"] == "api-idempotency-001"

    preserved = _agent_hints_with_operation_ids(
        {"operation_id": "existing-operation", "idempotency_key": "existing-idempotency"},
        operation_id="new-operation",
        idempotency_key="new-idempotency",
    )

    assert preserved["operation_id"] == "existing-operation"
    assert preserved["idempotency_key"] == "existing-idempotency"
