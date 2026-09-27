from pathlib import Path

from src.memory_system.workflow import build_default_agent


def test_storage_migration_preflight_creates_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "migration_preflight.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "migration_preflight.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="migration-user", session_id="migration-session", text="I need storage upgrade readiness evidence.")

    payload = agent.run_storage_migration_preflight()

    assert payload["preflight_version"] == "storage-migration-preflight.v1"
    assert payload["migration"]["policy_version"] == "storage-migration-policy.v1"
    assert payload["migration"]["preflight"]["status"] in {"ready", "review", "blocked"}
    assert payload["migration"]["rollback"]["strategy"] == "restore_latest_verified_backup"
    assert payload["migration"]["migration_acceptance"]["contract_version"] == "migration-acceptance.v1"
    assert payload["migration"]["migration_acceptance"]["decision"] in {
        "execute_now",
        "preflight_only",
        "refresh_rollback_evidence",
        "block",
    }
    assert payload["attempt_type"] == "migration_preflight"
    assert payload["result_status"] == payload["migration"]["preflight"]["status"]
    assert payload["artifact_path"]
    assert Path(payload["artifact_path"]).exists()
    assert payload["agent_handoff"]["preflight_status"] == payload["migration"]["preflight"]["status"]
