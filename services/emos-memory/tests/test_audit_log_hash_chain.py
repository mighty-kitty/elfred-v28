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


def test_interaction_log_records_local_hash_chain(tmp_path):
    config = _config(tmp_path)
    agent = build_default_agent(config=config, retrieval_settings_override={"backend": "embedding_rerank"})

    agent.write_memory(
        user_id="audit-chain-user",
        session_id="audit-chain-session",
        text="My preferred audit window is Friday afternoon.",
        force_write=True,
    )
    agent.recall_memory(
        user_id="audit-chain-user",
        session_id="audit-chain-session",
        query_text="What is my preferred audit window?",
    )

    records = [
        json.loads(line)
        for line in config.paths.interaction_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(records) >= 2
    first_chain = records[0]["audit_log_chain"]
    second_chain = records[1]["audit_log_chain"]
    assert first_chain["surface_version"] == "audit-log-hash-chain.v1"
    assert first_chain["previous_record_hash"] == "GENESIS"
    assert len(first_chain["record_hash"]) == 64
    assert second_chain["previous_record_hash"] == first_chain["record_hash"]
    assert len(second_chain["record_hash"]) == 64
    assert second_chain["tamper_evidence_scope"] == "local_hash_chain_not_external_attestation"
