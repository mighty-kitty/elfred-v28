import hashlib
import hmac
import time

from src.memory_system.config import AppConfig
from src.memory_system.workflow import build_default_agent


def _config(tmp_path):
    config = AppConfig()
    config.storage_backend = "json"
    config.log_level = "WARNING"
    config.paths.memory_file = tmp_path / "memory.json"
    config.paths.feedback_store_file = tmp_path / "feedback.json"
    config.paths.interaction_log_file = tmp_path / "interactions.jsonl"
    config.paths.retrieval_settings_file = tmp_path / "retrieval.json"
    config.security.require_write_auth = True
    config.security.write_auth_secret = "unit-test-secret"
    config.security.write_auth_max_age_seconds = 300
    return config


def _signed_hints(*, secret: str, user_id: str, session_id: str, source: str, text: str):
    timestamp = str(time.time())
    canonical = "\n".join([user_id, session_id, source, text, timestamp])
    signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "write_auth_timestamp": timestamp,
        "write_auth_signature": signature,
        "write_auth_principal": source,
    }


def test_write_auth_blocks_unsigned_write_and_plan(tmp_path):
    config = _config(tmp_path)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "auth-user"
    session_id = "auth-session"
    text = "My preferred deployment approver is Casey."

    plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text=text,
        source="untrusted_webhook",
    )["payload"]
    assert plan["next_action"] == "write_authentication_required"
    assert plan["write_authentication"]["authenticated"] is False
    assert plan["write_policy"]["policy"] == "write_authentication_required"
    assert "write_memory" in plan["execution_guardrails"]["blocked_operations"]

    write = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text=text,
        source="untrusted_webhook",
    )["payload"]
    assert write["memory_written"] is False
    assert write["next_action"] == "write_authentication_required"
    assert write["write_authentication"]["authenticated"] is False
    assert "write_memory" in write["execution_guardrails"]["blocked_operations"]
    assert agent.repository.list_memories(user_id, limit=10) == []


def test_write_auth_accepts_signed_write_without_persisting_signature(tmp_path):
    config = _config(tmp_path)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "signed-auth-user"
    session_id = "signed-auth-session"
    source = "trusted_adapter"
    text = "My preferred deployment approver is Morgan."
    hints = _signed_hints(
        secret=config.security.write_auth_secret,
        user_id=user_id,
        session_id=session_id,
        source=source,
        text=text,
    )

    write = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text=text,
        source=source,
        agent_hints=hints,
        force_write=True,
    )["payload"]

    assert write["memory_written"] is True
    assert write["write_authentication"]["authenticated"] is True
    assert "write_auth_signature" not in write["agent_hints"]
    memory = agent.repository.get_memory(user_id, write["memory_id"], include_inactive=True)
    assert memory is not None
    assert memory.metadata["source"] == source
    assert memory.metadata["write_authentication"]["authenticated"] is True
    assert "write_auth_signature" not in memory.metadata["agent_hints"]


def test_write_auth_accepts_previous_rotation_key_without_persisting_signature(tmp_path):
    config = _config(tmp_path)
    config.security.write_auth_secret = "current-unit-test-secret"
    config.security.write_auth_previous_secrets = ("previous-unit-test-secret",)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "rotation-auth-user"
    session_id = "rotation-auth-session"
    source = "trusted_adapter"
    text = "My preferred incident escalation reviewer is Avery."
    hints = _signed_hints(
        secret=config.security.write_auth_previous_secrets[0],
        user_id=user_id,
        session_id=session_id,
        source=source,
        text=text,
    )
    hints["write_auth_key_id"] = "previous-2026-q1"

    write = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text=text,
        source=source,
        agent_hints=hints,
        force_write=True,
    )["payload"]

    assert write["memory_written"] is True
    assert write["write_authentication"]["authenticated"] is True
    assert write["write_authentication"]["key_slot"] == "previous"
    assert write["write_authentication"]["accepted_previous_key"] is True
    assert write["write_authentication"]["key_rotation_supported"] is True
    assert write["write_authentication"]["reason"] == "write_auth_signature_valid_previous_key"
    assert "write_auth_signature" not in write["agent_hints"]
    memory = agent.repository.get_memory(user_id, write["memory_id"], include_inactive=True)
    assert memory is not None
    assert memory.metadata["write_authentication"]["key_slot"] == "previous"
    assert "write_auth_signature" not in memory.metadata["agent_hints"]


def test_write_auth_rejects_retired_rotation_key(tmp_path):
    config = _config(tmp_path)
    config.security.write_auth_secret = "current-unit-test-secret"
    config.security.write_auth_previous_secrets = ("previous-unit-test-secret",)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "retired-key-user"
    session_id = "retired-key-session"
    source = "trusted_adapter"
    text = "My preferred release checklist owner is Jules."
    hints = _signed_hints(
        secret="retired-unit-test-secret",
        user_id=user_id,
        session_id=session_id,
        source=source,
        text=text,
    )
    hints["write_auth_key_id"] = "retired-2025-q4"

    write = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text=text,
        source=source,
        agent_hints=hints,
        force_write=True,
    )["payload"]

    assert write["memory_written"] is False
    assert write["next_action"] == "write_authentication_required"
    assert write["write_authentication"]["authenticated"] is False
    assert write["write_authentication"]["key_slot"] == "unknown"
    assert write["write_authentication"]["key_rotation_supported"] is True
    assert write["write_authentication"]["reason"] == "write_auth_signature_invalid"
    assert agent.repository.list_memories(user_id, limit=10) == []
