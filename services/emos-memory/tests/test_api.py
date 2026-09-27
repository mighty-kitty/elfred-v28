import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from src.memory_system.api.server import create_handler


def test_api_process_and_profile_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "api_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "feedback_store.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "memory_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "retrieval_settings.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        root_response = urllib.request.urlopen(base_url, timeout=3)
        root_body = json.loads(root_response.read().decode("utf-8"))
        assert root_body["service"] == "EMOS Agent API"
        assert root_body["openapi"] == "/openapi.json"
        assert root_body["agent_api_manifest"] == "/system/agent-api-manifest"

        manifest_response = urllib.request.urlopen(f"{base_url}/system/agent-api-manifest", timeout=3)
        manifest_body = json.loads(manifest_response.read().decode("utf-8"))
        assert manifest_body["contract_version"] == "agent-api-manifest.v1"
        assert manifest_body["openapi_path"] == "/openapi.json"
        assert manifest_body["agent_entrypoints"][0]["path"] == "/memory/write-plan"

        openapi_response = urllib.request.urlopen(f"{base_url}/openapi.json", timeout=3)
        openapi_body = json.loads(openapi_response.read().decode("utf-8"))
        assert openapi_body["openapi"] == "3.1.0"
        assert "/memory/recall" in openapi_body["paths"]
        assert "/system/agent-api-manifest" in openapi_body["paths"]
        assert "MemoryRecallRequest" in openapi_body["components"]["schemas"]

        payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "text": "我最近考试压力有点大。",
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            url=f"{base_url}/memory/process",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=3)
        body = json.loads(response.read().decode("utf-8"))
        assert body["memory_committed"] is True

        recall_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "text": "刚才那种考试压力我最近一直有点缓不过来。",
            }
        ).encode("utf-8")
        recall_request = urllib.request.Request(
            url=f"{base_url}/memory/process",
            data=recall_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        recall_response = urllib.request.urlopen(recall_request, timeout=3)
        recall_body = json.loads(recall_response.read().decode("utf-8"))
        assert recall_body["retrieval_candidates"]
        memory_id = recall_body["retrieval_candidates"][0]["memory_id"]

        profile_response = urllib.request.urlopen(
            f"{base_url}/memory/profile?user_id=api-user&limit=5",
            timeout=3,
        )
        profile_body = json.loads(profile_response.read().decode("utf-8"))
        assert profile_body["user_id"] == "api-user"
        assert profile_body["memory_count"] >= 1

        report_response = urllib.request.urlopen(
            f"{base_url}/memory/report?user_id=api-user&limit=5",
            timeout=3,
        )
        report_body = json.loads(report_response.read().decode("utf-8"))
        assert report_body["user_id"] == "api-user"
        assert report_body["recent_memories"]

        export_response = urllib.request.urlopen(
            f"{base_url}/memory/export?user_id=api-user&limit=5",
            timeout=3,
        )
        export_body = json.loads(export_response.read().decode("utf-8"))
        assert export_body["user_id"] == "api-user"
        assert export_body["snapshot"]["memory_count"] >= 1

        system_response = urllib.request.urlopen(f"{base_url}/system/report", timeout=3)
        system_body = json.loads(system_response.read().decode("utf-8"))
        assert system_body["project"] == "AI Memory System"
        assert system_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert system_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert system_body["long_horizon_validation_summary"]["report_type"] == "long_horizon_validation_summary"
        assert system_body["long_horizon_multi_run_summary"]["report_type"] == "long_horizon_validation_multi_run_summary"
        assert system_body["evidence_surfaces"]["contract_version"] == "evidence-surfaces.v1"
        assert system_body["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
        assert system_body["evidence_surfaces"]["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
        assert system_body["retrieval_backend_report"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        storage_response = urllib.request.urlopen(f"{base_url}/system/storage", timeout=3)
        storage_body = json.loads(storage_response.read().decode("utf-8"))
        assert storage_body["resolved_backend"] in {"json", "sqlite"}
        assert storage_body["feedback_store_path"]
        assert "integrity_checks" in storage_body
        assert storage_body["preferred_primary_backend"] in {"json", "sqlite"}
        assert storage_body["primary_mode_status"] in {"healthy_primary", "degraded_fallback", "blocked"}
        assert storage_body["primary_storage"]["contract_version"] == "storage-primary-path.v1"
        assert "migration" in storage_body
        assert "recovery" in storage_body
        assert "backup_inventory" in storage_body
        assert "operator_checklist" in storage_body
        assert storage_body["operator_decision_path"]["decision_path_version"] == "storage-operator-decision-path.v1"
        assert storage_body["operator_acceptance_note"]["note_version"] == "storage-acceptance-note.v1"
        assert storage_body["remediation_checklist"]["checklist_version"] == "storage-remediation-checklist.v1"
        assert "deployment_guidance" in storage_body
        assert "persistence_confidence" in storage_body
        assert storage_body["policy_input"]["resolution_flow"] in {
            "storage_recovery_flow",
            "storage_primary_path_hardening_flow",
            "storage_backup_refresh_flow",
            "storage_health_maintenance_flow",
        }
        assert storage_body["execution_policy"]["policy_version"] == "storage-execution-policy.v1"
        assert storage_body["execution_policy"]["primary_path"]["mode_status"] == storage_body["primary_mode_status"]
        assert storage_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert storage_body["operator_decision_path"]["primary_storage_mode"] == storage_body["primary_mode_status"]
        assert storage_body["operator_acceptance_note"]["primary_storage_mode"] == storage_body["primary_mode_status"]
        assert storage_body["remediation_checklist"]["mode"] == storage_body["primary_mode_status"]
        assert storage_body["migration"]["schema_status"] in {"aligned", "unknown", "drifted"}
        assert storage_body["migration"]["policy_version"] == "storage-migration-policy.v1"
        assert storage_body["migration"]["preflight"]["status"] in {"ready", "review", "blocked"}
        assert storage_body["migration"]["rollback"]["strategy"] == "restore_latest_verified_backup"
        assert "rollback_evidence" in storage_body["migration"]["rollback"]
        assert storage_body["migration"]["latest_attempt"]["status"] in {"not_run", "ready", "review", "blocked", "unknown"}
        assert storage_body["migration"]["migration_acceptance"]["contract_version"] == "migration-acceptance.v1"
        assert "latest_restore_drill" in storage_body["recovery"]
        assert "last_restore_drill_at" in storage_body["recovery"]
        assert "last_restore_drill_age_hours" in storage_body["recovery"]
        assert storage_body["recovery"]["restore_drill_freshness"]["contract_version"] == "restore-drill-freshness.v1"
        assert storage_body["recovery"]["last_restore_drill_status"] in {"missing", "passed", "failed", "unknown"}
        assert storage_body["recovery"]["restore_confidence"] in {"low", "medium", "high"}
        assert storage_body["recovery"]["recovery_confidence"] in {"low", "medium", "high"}
        assert "restore_drill_acceptance" in storage_body["operator_decision_path"]
        assert storage_body["agent_handoff"]["report_type"] == "storage"

        backup_response = urllib.request.urlopen(f"{base_url}/system/storage-backup", timeout=3)
        backup_body = json.loads(backup_response.read().decode("utf-8"))
        assert backup_body["path"]
        assert backup_body["exists"] is True
        assert backup_body["verification"]["status"] == "verified"
        assert backup_body["agent_handoff"]["verification_status"] == "verified"
        assert backup_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert backup_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        feedback_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "memory_id": memory_id,
                "feedback_type": "correct",
                "query_text": "我最近考试压力有点大。",
            }
        ).encode("utf-8")
        feedback_request = urllib.request.Request(
            url=f"{base_url}/memory/feedback",
            data=feedback_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        feedback_response = urllib.request.urlopen(feedback_request, timeout=3)
        feedback_body = json.loads(feedback_response.read().decode("utf-8"))
        assert feedback_body["feedback_type"] == "correct"
        assert feedback_body["event_id"].startswith("fb_")

        feedback_report_response = urllib.request.urlopen(
            f"{base_url}/memory/feedback?user_id=api-user&limit=5",
            timeout=3,
        )
        feedback_report_body = json.loads(feedback_report_response.read().decode("utf-8"))
        assert feedback_report_body["summary"]["correct"] >= 1
        assert feedback_report_body["profile_insights"]["top_memories"]

        write_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "text": "Temporary status: tool output cache refreshed for this ticket.",
                "task_type": "tool_result",
                "memory_scope": "auto",
                "source": "agent",
                "task_goal": "track durable user facts only",
                "context_summary": "This turn is just tool state and should not become a long-term memory.",
                "working_memory": ["ephemeral tool state"],
            }
        ).encode("utf-8")
        write_request = urllib.request.Request(
            url=f"{base_url}/memory/write",
            data=write_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        write_response = urllib.request.urlopen(write_request, timeout=3)
        write_body = json.loads(write_response.read().decode("utf-8"))
        assert write_body["contract_version"] == "memory-service.v1"
        assert write_body["payload"]["memory_written"] is False
        assert write_body["payload"]["decision_protocol"]["protocol_version"] == "agent-decision.v1"
        assert write_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "skip_long_term_write"
        assert "write_memory" in write_body["payload"]["execution_guardrails"]["blocked_operations"]
        assert write_body["payload"]["agent_handoff"]["mode"] == "skip_long_term_write"

        write_plan_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "text": "I always want to visit Tokyo again for car culture and music.",
                "task_type": "chat",
                "memory_scope": "auto",
                "source": "agent",
            }
        ).encode("utf-8")
        write_plan_request = urllib.request.Request(
            url=f"{base_url}/memory/write-plan",
            data=write_plan_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        write_plan_response = urllib.request.urlopen(write_plan_request, timeout=3)
        write_plan_body = json.loads(write_plan_response.read().decode("utf-8"))
        assert write_plan_body["payload"]["memory_resolution"]["action"] in {"new_memory", "deduplicate", "suggest_update"}
        assert write_plan_body["payload"]["decision_protocol"]["operation"] == "plan_memory_write"
        assert write_plan_body["payload"]["consistency_plan"]["recommended_operations"]
        assert write_plan_body["payload"]["consistency_plan"]["plan_version"] == "consistency-plan.v2"
        assert "action_buckets" in write_plan_body["payload"]["consistency_plan"]
        assert write_plan_body["payload"]["execution_guardrails"]["mode"] in {"auto", "restricted", "confirmation_required"}
        assert write_plan_body["payload"]["agent_handoff"]["recommended_operation"] == write_plan_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"]
        assert write_plan_body["payload"]["execution_policy"]["policy_version"] == "memory-write-execution-policy.v1"
        assert write_plan_body["payload"]["policy_input"]["service_operation"] == "plan_memory_write"
        assert write_plan_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert write_plan_body["payload"]["execution_surface"]["action_surface"] == write_plan_body["payload"]["action_surface"]

        durable_write_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "text": "I always want to visit Tokyo again for car culture and music.",
                "task_type": "chat",
                "memory_scope": "auto",
                "source": "agent",
            }
        ).encode("utf-8")
        durable_write_request = urllib.request.Request(
            url=f"{base_url}/memory/write",
            data=durable_write_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        durable_write_response = urllib.request.urlopen(durable_write_request, timeout=3)
        durable_write_body = json.loads(durable_write_response.read().decode("utf-8"))
        durable_memory_id = durable_write_body["payload"]["memory_id"]
        assert durable_write_body["payload"]["memory_written"] is True
        assert durable_memory_id in durable_write_body["payload"]["decision_protocol"]["target_memory_ids"]
        assert durable_write_body["payload"]["consistency_plan"]["recommended_operations"]
        assert durable_write_body["payload"]["execution_guardrails"]["mode"] in {"auto", "restricted", "confirmation_required"}
        assert durable_memory_id in durable_write_body["payload"]["agent_handoff"]["target_memory_ids"]
        assert durable_write_body["payload"]["execution_policy"]["policy_version"] == "memory-write-execution-policy.v1"
        assert durable_write_body["payload"]["policy_input"]["service_operation"] == "write_memory"
        assert durable_write_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert durable_write_body["payload"]["execution_surface"]["action_surface"] == durable_write_body["payload"]["action_surface"]

        recall_contract_payload = json.dumps(
            {
                "user_id": "api-user",
                "query_text": "What pressure have I been under recently?",
                "session_id": "api-session",
                "top_k": 3,
                "include_profile": True,
                "task_goal": "answer from long-term memory",
                "context_summary": "Need a concise grounded answer for the personal agent.",
                "working_memory": ["respond concisely", "cite evidence"],
                "response_mode": "agent_bundle",
            }
        ).encode("utf-8")
        recall_contract_request = urllib.request.Request(
            url=f"{base_url}/memory/recall",
            data=recall_contract_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        recall_contract_response = urllib.request.urlopen(recall_contract_request, timeout=3)
        recall_contract_body = json.loads(recall_contract_response.read().decode("utf-8"))
        assert recall_contract_body["payload"]["retrieval_candidates"] or recall_contract_body["payload"]["fallback_memories"]
        assert recall_contract_body["payload"]["confidence"] >= 0
        assert recall_contract_body["payload"]["memory_context"]["task_goal"] == "answer from long-term memory"
        assert recall_contract_body["payload"]["memory_context"]["working_memory"] == ["respond concisely", "cite evidence"]
        assert "facts" in recall_contract_body["payload"]["memory_context"]
        assert recall_contract_body["payload"]["decision_protocol"]["protocol_version"] == "agent-decision.v1"
        assert recall_contract_body["payload"]["memory_context"]["decision_protocol"]["operation"] == "recall_memory"
        assert recall_contract_body["payload"]["decision_protocol"]["recommended_action"] == recall_contract_body["payload"]["memory_context"]["decision_protocol"]["recommended_action"]
        assert recall_contract_body["payload"]["consistency_plan"]["recommended_operations"]
        assert recall_contract_body["payload"]["consistency_plan"]["plan_version"] == "consistency-plan.v2"
        assert "issue_summary" in recall_contract_body["payload"]["consistency_plan"]
        assert "action_buckets" in recall_contract_body["payload"]["consistency_plan"]
        assert recall_contract_body["payload"]["memory_context"]["consistency_plan"]["recommended_operations"]
        assert recall_contract_body["payload"]["response_contract"]["citation_required"] is True
        assert recall_contract_body["payload"]["preferred_surface"] == "agent_bundle"
        assert "freshness_guard" in recall_contract_body["payload"]["response_contract"]
        assert "conflict_profile" in recall_contract_body["payload"]["response_contract"]
        assert "freshness_guard" in recall_contract_body["payload"]["memory_context"]
        assert "conflict_profile" in recall_contract_body["payload"]["memory_context"]
        assert recall_contract_body["payload"]["response_guardrails"]["mode"] in {"auto", "restricted", "confirmation_required"}
        assert recall_contract_body["payload"]["execution_policy"]["policy_version"] == "memory-recall-execution-policy.v1"
        assert recall_contract_body["payload"]["policy_input"]["resolution_flow"] in {
            "grounded_answer_flow",
            "confirm_then_answer_flow",
            "fallback_memory_flow",
            "no_grounded_answer_flow",
        }
        assert recall_contract_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert recall_contract_body["payload"]["execution_surface"]["agent_handoff"] == recall_contract_body["payload"]["agent_handoff"]
        assert recall_contract_body["payload"]["user_experience_guidance"]["feedback_strategy"] == "passive_first"
        assert "freshness_hint" in recall_contract_body["payload"]["user_experience_guidance"]
        assert recall_contract_body["payload"]["agent_response_plan"]["answer_skeleton"]
        assert recall_contract_body["payload"]["agent_response_plan"]["response_language"] == "en"
        assert recall_contract_body["payload"]["agent_handoff"]["response_preview"] == recall_contract_body["payload"]["agent_response_plan"]["answer_skeleton"]
        assert recall_contract_body["payload"]["agent_handoff"]["version_status"] in {"stable", "disputed", "inactive"}
        assert recall_contract_body["payload"]["memory_context"]["agent_handoff"]["primary_operation"] == recall_contract_body["payload"]["memory_context"]["consistency_plan"]["recommended_operations"][0]["operation"]
        assert recall_contract_body["payload"]["memory_context"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert "freshness_strategy" in recall_contract_body["payload"]["agent_response_plan"]

        thin_recall_payload = json.dumps(
            {
                "user_id": "api-user",
                "query_text": "What pressure have I been under recently?",
                "session_id": "api-session",
                "top_k": 3,
                "include_profile": True,
                "response_mode": "execution_surface",
            }
        ).encode("utf-8")
        thin_recall_request = urllib.request.Request(
            url=f"{base_url}/memory/recall",
            data=thin_recall_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        thin_recall_response = urllib.request.urlopen(thin_recall_request, timeout=3)
        thin_recall_body = json.loads(thin_recall_response.read().decode("utf-8"))
        assert thin_recall_body["payload"]["preferred_surface"] == "execution_surface"
        assert thin_recall_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        reflect_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "persist": False,
            }
        ).encode("utf-8")
        reflect_request = urllib.request.Request(
            url=f"{base_url}/memory/reflect",
            data=reflect_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        reflect_response = urllib.request.urlopen(reflect_request, timeout=3)
        reflect_body = json.loads(reflect_response.read().decode("utf-8"))
        assert "reflection" in reflect_body["payload"]
        assert reflect_body["payload"]["agent_handoff"]["recommended_operation"] == "use_reflection_summary"
        assert reflect_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"

        update_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "memory_id": durable_memory_id,
                "text": "I always want to visit Tokyo and Osaka again for car culture and music.",
                "source": "agent",
                "task_goal": "refresh travel preference memory",
                "context_summary": "The user refined a durable travel preference.",
                "working_memory": ["merge Osaka into existing preference"],
            }
        ).encode("utf-8")
        update_request = urllib.request.Request(
            url=f"{base_url}/memory/update",
            data=update_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        update_response = urllib.request.urlopen(update_request, timeout=3)
        update_body = json.loads(update_response.read().decode("utf-8"))
        assert update_body["payload"]["updated"] is True
        assert "Osaka" in update_body["payload"]["memory"]["text"]
        assert update_body["payload"]["decision_protocol"]["recommended_action"] == "memory_updated"
        assert update_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
        assert update_body["payload"]["agent_handoff"]["recommended_operation"] == "get_memory_history"
        assert update_body["payload"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
        assert update_body["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
        assert update_body["payload"]["policy_input"]["lifecycle_operation"] == "update_memory"
        assert update_body["payload"]["policy_input"]["service_operation"] == "update_memory"
        assert update_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert update_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert update_body["payload"]["execution_surface"]["action_surface"] == update_body["payload"]["action_surface"]

        block_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "label": "persona_anchor",
                "value": "User cares about emotionally meaningful travel and music experiences.",
                "description": "Pinned core block for upper-layer personalization.",
                "read_only": False,
                "source": "agent",
            }
        ).encode("utf-8")
        block_request = urllib.request.Request(
            url=f"{base_url}/memory/block",
            data=block_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        block_response = urllib.request.urlopen(block_request, timeout=3)
        block_body = json.loads(block_response.read().decode("utf-8"))
        assert block_body["payload"]["block"]["label"] == "persona_anchor"
        assert block_body["payload"]["decision_protocol"]["target_block_labels"] == ["persona_anchor"]
        assert block_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "use_block_in_personal_agent_context"
        assert block_body["payload"]["agent_handoff"]["block_label"] == "persona_anchor"
        assert block_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"

        blocks_response = urllib.request.urlopen(
            f"{base_url}/memory/blocks?user_id=api-user",
            timeout=3,
        )
        blocks_body = json.loads(blocks_response.read().decode("utf-8"))
        assert any(item["label"] == "persona_anchor" for item in blocks_body["blocks"])

        forget_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "memory_id": durable_memory_id,
                "reason": "outdated preference",
                "source": "agent",
            }
        ).encode("utf-8")
        forget_request = urllib.request.Request(
            url=f"{base_url}/memory/forget",
            data=forget_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        forget_response = urllib.request.urlopen(forget_request, timeout=3)
        forget_body = json.loads(forget_response.read().decode("utf-8"))
        assert forget_body["payload"]["forgotten"] is True
        assert forget_body["payload"]["decision_protocol"]["target_memory_ids"] == [durable_memory_id]
        assert forget_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
        assert forget_body["payload"]["agent_handoff"]["state_status"] == "forgotten"
        assert "consistency_maintenance" in forget_body["payload"]
        assert forget_body["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
        assert forget_body["payload"]["policy_input"]["lifecycle_operation"] == "forget_memory"
        assert forget_body["payload"]["policy_input"]["service_operation"] == "forget_memory"
        assert forget_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert forget_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert forget_body["payload"]["execution_surface"]["action_surface"] == forget_body["payload"]["action_surface"]

        restore_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "memory_id": durable_memory_id,
                "reason": "preference still valid",
                "source": "agent",
            }
        ).encode("utf-8")
        restore_request = urllib.request.Request(
            url=f"{base_url}/memory/restore",
            data=restore_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        restore_response = urllib.request.urlopen(restore_request, timeout=3)
        restore_body = json.loads(restore_response.read().decode("utf-8"))
        assert restore_body["payload"]["restored"] is True
        assert restore_body["payload"]["decision_protocol"]["recommended_action"] == "memory_restored"
        assert restore_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
        assert restore_body["payload"]["agent_handoff"]["state_status"] == "active"
        assert restore_body["payload"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
        assert restore_body["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
        assert restore_body["payload"]["policy_input"]["lifecycle_operation"] == "restore_memory"
        assert restore_body["payload"]["policy_input"]["service_operation"] == "restore_memory"
        assert restore_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert restore_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert restore_body["payload"]["execution_surface"]["action_surface"] == restore_body["payload"]["action_surface"]

        history_response = urllib.request.urlopen(
            f"{base_url}/memory/history?user_id=api-user&memory_id={durable_memory_id}&session_id=api-session",
            timeout=3,
        )
        history_body = json.loads(history_response.read().decode("utf-8"))
        assert history_body["payload"]["history_count"] >= 1
        assert history_body["payload"]["decision_protocol"]["operation"] == "get_memory_history"
        assert history_body["payload"]["consistency_plan"]["status"] in {"review", "clear", "conflicted"}
        assert history_body["payload"]["agent_handoff"]["recommended_operation"] == history_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"]
        assert history_body["payload"]["consistency_maintenance"]["action_buckets"]["manual_review"]
        assert history_body["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
        assert history_body["payload"]["policy_input"]["lifecycle_operation"] == "get_memory_history"
        assert history_body["payload"]["policy_input"]["service_operation"] == "get_memory_history"
        assert history_body["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert history_body["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert history_body["payload"]["execution_surface"]["action_surface"] == history_body["payload"]["action_surface"]

        integration_response = urllib.request.urlopen(
            f"{base_url}/system/integration-flow?user_id=api-user&session_id=api-session&limit=50",
            timeout=3,
        )
        integration_body = json.loads(integration_response.read().decode("utf-8"))
        assert integration_body["report_type"] == "personal_agent_integration_flow"
        assert integration_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert "required_capabilities" in integration_body
        assert integration_body["coverage"]["response_plan_records"] >= 1
        assert "scenario_checks" in integration_body
        assert "scenario_status" in integration_body
        assert "consistency_loop" in integration_body["scenario_checks"]
        assert "execution_surface" in integration_body
        assert "recommended_call_flows" in integration_body
        assert "anti_patterns" in integration_body
        assert "runtime_scope" in integration_body
        assert "integration_evidence" in integration_body
        assert integration_body["evidence_bridge"]["bridge_version"] == "integration-evidence-bridge.v1"

        training_response = urllib.request.urlopen(
            f"{base_url}/system/training-protocol?user_id=api-user&limit=50",
            timeout=3,
        )
        training_body = json.loads(training_response.read().decode("utf-8"))
        assert training_body["report_type"] == "training_protocol"
        assert training_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert training_body["training_sample_count"] >= 1
        assert training_body["labeled_sample_count"] >= 1
        assert training_body["protocol_labeled_sample_count"] >= 1
        assert training_body["response_plan_record_count"] >= 1
        assert training_body["labeling_mode"] in {"protocol_labeled", "hybrid", "feedback_attached"}

        ux_response = urllib.request.urlopen(
            f"{base_url}/system/user-experience?user_id=api-user&session_id=api-session&limit=50",
            timeout=3,
        )
        ux_body = json.loads(ux_response.read().decode("utf-8"))
        assert ux_body["report_type"] == "user_experience"
        assert ux_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert ux_body["comfort_score"] >= 0
        assert ux_body["ready_answer_ratio"] >= 0
        assert ux_body["readiness_basis"] in {"runtime_observation", "thin_runtime_scope_normalized"}
        assert "runtime_scope" in ux_body

        consistency_response = urllib.request.urlopen(
            f"{base_url}/system/consistency-audit?user_id=api-user&limit=50",
            timeout=3,
        )
        consistency_body = json.loads(consistency_response.read().decode("utf-8"))
        assert consistency_body["report_type"] == "consistency_audit"
        assert consistency_body["revised_fact_count"] >= 1
        assert "old_fact_count" in consistency_body
        assert "disputed_fact_count" in consistency_body
        assert "consistency_type_counts" in consistency_body
        assert consistency_body["governance_mode"] in {"auto_safe", "confirm_required", "manual_review"}
        assert "action_buckets" in consistency_body
        assert consistency_body["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
        assert "operator_action_buckets" in consistency_body
        assert "agent_action_buckets" in consistency_body
        assert consistency_body["maintenance_jobs"]
        assert consistency_body["lifecycle_execution_paths"]
        assert consistency_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert consistency_body["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
        assert consistency_body["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
        assert consistency_body["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
        assert consistency_body["operator_review_order"]["surface_version"] == "operator-review-order.v1"
        assert consistency_body["recommended_operations"]

        hygiene_response = urllib.request.urlopen(
            f"{base_url}/system/memory-hygiene?user_id=api-user&limit=50",
            timeout=3,
        )
        hygiene_body = json.loads(hygiene_response.read().decode("utf-8"))
        assert hygiene_body["report_type"] == "memory_hygiene"
        assert hygiene_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert hygiene_body["memory_count"] >= 1

        release_response = urllib.request.urlopen(
            f"{base_url}/system/release-readiness?user_id=api-user&session_id=api-session&limit=50",
            timeout=3,
        )
        release_body = json.loads(release_response.read().decode("utf-8"))
        assert release_body["report_type"] == "release_readiness"
        assert release_body["readiness"] in {"market_pilot_ready", "limited_pilot", "internal_only"}
        assert "memory_hygiene" in release_body
        assert "consistency" in release_body
        assert release_body["consistency"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
        assert release_body["consistency"]["maintenance_jobs"]
        assert release_body["consistency"]["lifecycle_execution_paths"]
        assert release_body["consistency"]["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
        assert release_body["consistency"]["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
        assert release_body["consistency"]["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
        assert release_body["consistency"]["operator_review_order"]["surface_version"] == "operator-review-order.v1"
        assert release_body["recommended_lifecycle_execution"]["surface_version"] == "agent-execution-surface.v1"
        assert release_body["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
        assert release_body["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
        assert release_body["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
        assert release_body["operator_review_order"]["surface_version"] == "operator-review-order.v1"
        assert release_body["readiness_source_map"]["integration_flow_blocked"]["source_report"] == "integration_flow"
        assert release_body["baseline_summary"]["contract_version"] == "readiness-baseline-summary.v1"
        assert release_body["agent_handoff"]["report_type"] == "release_readiness"
        assert release_body["action_surface"]["surface_version"] == "agent-action-surface.v1"

        baseline_response = urllib.request.urlopen(
            f"{base_url}/system/readiness-baseline?user_id=api-user&session_id=api-session&limit=50",
            timeout=3,
        )
        baseline_body = json.loads(baseline_response.read().decode("utf-8"))
        assert baseline_body["report_type"] == "readiness_baseline"
        assert baseline_body["baseline_version"] == "readiness-baseline.v1"
        assert baseline_body["scope"]["scope_mode"] == "scoped"
        assert baseline_body["source_map"]["user_experience_risky"]["resolution_flow"] == "user_experience_review"
        assert isinstance(baseline_body["active_sources"], list)
        assert baseline_body["phase_targets"][0]["phase"] == "Phase B"
        assert "agent_execution" in baseline_body["evidence_snapshot"]
        assert baseline_body["agent_handoff"]["report_type"] == "readiness_baseline"
        assert baseline_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        readiness_response = urllib.request.urlopen(
            f"{base_url}/system/agent-readiness-summary?user_id=api-user&session_id=api-session&limit=50",
            timeout=3,
        )
        readiness_body = json.loads(readiness_response.read().decode("utf-8"))
        assert readiness_body["report_type"] == "agent_readiness_summary"
        assert readiness_body["agent_handoff"]["report_type"] == "agent_readiness_summary"
        assert readiness_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert "surface_status" in readiness_body
        assert readiness_body["surface_status"]["retrieval"] in {"ready", "review"}
        assert readiness_body["execution_policy"]["policy_version"] == "agent-execution-policy.v1"
        assert readiness_body["policy_input"]["resolution_flow"] in {
            "standard_chat_flow",
            "guarded_recall_flow",
            "plan_then_write_flow",
            "consistency_resolution_flow",
            "storage_recovery_flow",
        }
        assert readiness_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
        assert readiness_body["execution_surface"]["policy_input"] == readiness_body["policy_input"]
        assert readiness_body["retrieval_runtime_advice"]["advice_version"] == "retrieval-runtime-advice.v1"
        assert readiness_body["consistency_handoff"]["report_type"] == "consistency_audit"
        assert readiness_body["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
        assert readiness_body["consistency_agent_action_buckets"]
        assert readiness_body["consistency_maintenance_jobs"]
        assert readiness_body["consistency_lifecycle_execution_paths"]
        assert readiness_body["recommended_lifecycle_execution"]["surface_version"] == "agent-execution-surface.v1"
        assert readiness_body["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
        assert readiness_body["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
        assert readiness_body["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
        assert readiness_body["operator_review_order"]["surface_version"] == "operator-review-order.v1"
        assert readiness_body["readiness_source_map"]["training_protocol_partial"]["source_report"] == "training_protocol"
        assert readiness_body["baseline_summary"]["contract_version"] == "readiness-baseline-summary.v1"

        long_horizon_response = urllib.request.urlopen(
            f"{base_url}/system/long-horizon-validation?user_id=api-user-long&session_id=api-session-long&limit=50",
            timeout=15,
        )
        long_horizon_body = json.loads(long_horizon_response.read().decode("utf-8"))
        assert long_horizon_body["report_type"] == "long_horizon_validation"
        assert long_horizon_body["validation_version"] == "long-horizon-validation.v1"
        assert long_horizon_body["workload_profile"]["profile_count"] == 3
        assert long_horizon_body["workload_profile"]["day_count"] == 3
        assert len(long_horizon_body["workload_profiles"]) == 3
        assert long_horizon_body["counts"]["recall_count"] >= 12
        assert long_horizon_body["counts"]["task_switch_count"] == 3
        assert long_horizon_body["counts"]["conflict_check_count"] == 3
        assert long_horizon_body["evidence_boundary"]["contract_version"] == "long-horizon-evidence-boundary.v1"
        assert long_horizon_body["artifacts"]["artifact_path"].endswith(".json")
        assert long_horizon_body["supporting_reports"]["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
        assert long_horizon_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert long_horizon_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        long_horizon_summary_response = urllib.request.urlopen(
            f"{base_url}/system/long-horizon-summary?limit=5",
            timeout=15,
        )
        long_horizon_summary_body = json.loads(long_horizon_summary_response.read().decode("utf-8"))
        assert long_horizon_summary_body["report_type"] == "long_horizon_validation_multi_run_summary"
        assert long_horizon_summary_body["contract_version"] == "long-horizon-multi-run-summary.v1"
        assert long_horizon_summary_body["run_count"] >= 1
        assert len(long_horizon_summary_body["profile_summaries"]) == 3
        assert long_horizon_summary_body["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
        assert long_horizon_summary_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert long_horizon_summary_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        delete_block_payload = json.dumps(
            {
                "user_id": "api-user",
                "session_id": "api-session",
                "label": "persona_anchor",
            }
        ).encode("utf-8")
        delete_block_request = urllib.request.Request(
            url=f"{base_url}/memory/block/delete",
            data=delete_block_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        delete_block_response = urllib.request.urlopen(delete_block_request, timeout=3)
        delete_block_body = json.loads(delete_block_response.read().decode("utf-8"))
        assert delete_block_body["payload"]["deleted"] is True
        assert delete_block_body["payload"]["decision_protocol"]["target_block_labels"] == ["persona_anchor"]
        assert delete_block_body["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "refresh_core_block_cache"
        assert delete_block_body["payload"]["agent_handoff"]["deleted"] is True

        backends_response = urllib.request.urlopen(
            f"{base_url}/system/retrieval-backends",
            timeout=3,
        )
        backends_body = json.loads(backends_response.read().decode("utf-8"))
        assert "embedding_rerank" in backends_body["available_backends"]
        assert backends_body["pipeline_profile"]["supports_rerank"] is True
        assert backends_body["runtime_advice"]["advice_version"] == "retrieval-runtime-advice.v1"
        assert backends_body["runtime_advice"]["response_policy"]["mode"] in {
            "grounded_answer",
            "confirm_on_ambiguity",
            "avoid_strong_answer_on_thin_candidate_pool",
        }
        assert "control_plane" in backends_body["pipeline_profile"]
        assert "agent_contract" in backends_body["pipeline_profile"]
        assert backends_body["control_plane_status"]["readiness"] in {"ready", "review"}
        assert "task_fit" in backends_body
        assert "agent_recommendations" in backends_body
        assert backends_body["action_surface"]["surface_version"] == "agent-action-surface.v1"
        assert backends_body["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

        backend_payload = json.dumps(
            {
                "backend_name": "lexical",
                "embedding_dimensions": 64,
                "embedding_candidate_pool": 6,
            }
        ).encode("utf-8")
        backend_request = urllib.request.Request(
            url=f"{base_url}/system/retrieval-backend",
            data=backend_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        backend_response = urllib.request.urlopen(backend_request, timeout=3)
        backend_body = json.loads(backend_response.read().decode("utf-8"))
        assert backend_body["active_backend"] == "lexical"
        assert backend_body["backend_descriptor"]["name"] == "lexical"
        assert backend_body["pipeline_profile"]["fusion_strategy"] == "none"
        assert "validation_notes" in backend_body
        assert backend_body["switch_history"]
        assert backend_body["control_plane_status"]["readiness"] in {"ready", "review"}

        offline_response = urllib.request.urlopen(
            f"{base_url}/system/offline-review-export?limit=20",
            timeout=3,
        )
        offline_body = json.loads(offline_response.read().decode("utf-8"))
        assert offline_body["count"] >= 1
        assert offline_body["path"]
        assert "labeled_samples" in offline_body["manifest"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
