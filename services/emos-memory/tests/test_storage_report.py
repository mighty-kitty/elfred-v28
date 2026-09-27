from src.memory_system.workflow import build_default_agent


def test_storage_report_exposes_backend_health(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "storage_report.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "storage_report.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="storage-user", session_id="storage-session", text="我最近工作压力很大。")

    report = agent.get_storage_report()

    assert report["resolved_backend"] in {"json", "sqlite"}
    assert "path" in report
    assert "exists" in report
    assert report["readiness"] in {"ready", "review", "risky"}
    assert report["preferred_primary_backend"] in {"json", "sqlite"}
    assert report["primary_mode_status"] in {"healthy_primary", "degraded_fallback", "blocked"}
    assert report["primary_storage"]["contract_version"] == "storage-primary-path.v1"
    assert "migration" in report
    assert "recovery" in report
    assert "backup_inventory" in report
    assert "observability" in report
    assert "operator_checklist" in report
    assert report["operator_decision_path"]["decision_path_version"] == "storage-operator-decision-path.v1"
    assert report["operator_acceptance_note"]["note_version"] == "storage-acceptance-note.v1"
    assert report["remediation_checklist"]["checklist_version"] == "storage-remediation-checklist.v1"
    assert "deployment_guidance" in report
    assert "persistence_confidence" in report
    assert report["policy_input"]["resolution_flow"] in {
        "storage_recovery_flow",
        "storage_primary_path_hardening_flow",
        "storage_backup_refresh_flow",
        "storage_health_maintenance_flow",
    }
    assert report["execution_policy"]["policy_version"] == "storage-execution-policy.v1"
    assert report["execution_policy"]["primary_path"]["mode_status"] == report["primary_mode_status"]
    assert report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert report["operator_decision_path"]["primary_storage_mode"] == report["primary_mode_status"]
    assert report["operator_acceptance_note"]["primary_storage_mode"] == report["primary_mode_status"]
    assert report["remediation_checklist"]["mode"] == report["primary_mode_status"]
    assert report["migration"]["schema_status"] in {"aligned", "unknown", "drifted"}
    assert report["migration"]["policy_version"] == "storage-migration-policy.v1"
    assert report["migration"]["preflight"]["status"] in {"ready", "review", "blocked"}
    assert report["migration"]["rollback"]["strategy"] == "restore_latest_verified_backup"
    assert "rollback_evidence" in report["migration"]["rollback"]
    assert report["migration"]["latest_attempt"]["status"] in {"not_run", "ready", "review", "blocked", "unknown"}
    assert report["migration"]["migration_acceptance"]["contract_version"] == "migration-acceptance.v1"
    assert report["migration"]["migration_acceptance"]["decision"] in {"execute_now", "preflight_only", "refresh_rollback_evidence", "block"}
    assert report["operator_decision_path"]["migration_acceptance"]["decision"] == report["migration"]["migration_acceptance"]["decision"]
    assert "latest_backup" in report["recovery"]
    assert "latest_restore_drill" in report["recovery"]
    assert "last_restore_drill_at" in report["recovery"]
    assert "last_restore_drill_age_hours" in report["recovery"]
    assert report["recovery"]["restore_drill_freshness"]["contract_version"] == "restore-drill-freshness.v1"
    assert report["recovery"]["restore_drill_freshness"]["status"] in {"fresh", "stale", "missing", "failed"}
    assert report["recovery"]["last_restore_drill_status"] in {"missing", "passed", "failed", "unknown"}
    assert report["recovery"]["restore_confidence"] in {"low", "medium", "high"}
    assert report["recovery"]["recovery_confidence"] in {"low", "medium", "high"}
    assert "restore_drill_acceptance" in report["operator_decision_path"]
    assert "recommended_operations" in report
    assert report["agent_handoff"]["report_type"] == "storage"
