import json

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
    return config


def test_soft_forget_returns_operator_auditable_deletion_receipt(tmp_path):
    agent = build_default_agent(config=_config(tmp_path), retrieval_settings_override={"backend": "embedding_rerank"})
    user_id = "deletion-receipt-user"
    session_id = "deletion-receipt-session"

    written = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="My emergency locker code is ORCHID-77.",
        force_write=True,
        source="trusted_adapter",
    )["payload"]
    memory_id = written["memory_id"]

    forgotten = agent.forget_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason="user requested local memory deletion",
        source="trusted_adapter",
    )["payload"]

    receipt = forgotten["deletion_receipt"]
    assert forgotten["forgotten"] is True
    assert receipt["surface_version"] == "deletion-receipt.v1"
    assert receipt["verification_scope"] == "operator_auditable_service_receipt"
    assert receipt["deletion_mode"] == "soft_forget_tombstone"
    assert receipt["tombstone_status"] == "forgotten"
    assert receipt["memory_id"] == memory_id
    assert receipt["deleted_by"] == "trusted_adapter"
    assert len(receipt["receipt_hash"]) == 64
    assert "memory_excluded_from_active_repository_reads" in receipt["guarantees"]
    assert "cryptographic_erasure_proof" in receipt["non_guarantees"]
    assert "physical_storage_erasure" in receipt["non_guarantees"]
    assert "ORCHID-77" not in json.dumps(receipt, sort_keys=True)

    assert agent.repository.get_memory(user_id, memory_id) is None
    inactive_entry = agent.repository.get_memory(user_id, memory_id, include_inactive=True)
    assert inactive_entry is not None
    assert inactive_entry.metadata["deletion_receipt"]["receipt_id"] == receipt["receipt_id"]
    assert forgotten["memory_state"]["deletion_receipt_available"] is True
    assert forgotten["memory_state"]["deletion_receipt"]["receipt_id"] == receipt["receipt_id"]

    history = agent.get_memory_history(user_id=user_id, session_id=session_id, memory_id=memory_id)["payload"]["history"]
    assert history[-1]["action"] == "forget"
    assert history[-1]["deletion_receipt"]["receipt_id"] == receipt["receipt_id"]

    restored = agent.restore_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason="rollback test",
        source="trusted_adapter",
    )["payload"]
    assert restored["restored"] is True
    assert restored["memory_state"]["status"] == "active"
    assert restored["memory_state"]["deletion_receipt_available"] is False
    restored_entry = agent.repository.get_memory(user_id, memory_id, include_inactive=True)
    assert restored_entry is not None
    assert restored_entry.metadata["deletion_receipt_history"][-1]["receipt_id"] == receipt["receipt_id"]
