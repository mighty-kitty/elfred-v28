import json

from src.memory_system.workflow import build_default_agent


def test_memory_service_write_policy_and_recall(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "service_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "service_feedback.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "service_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "service_retrieval.json"))

    agent = build_default_agent()
    user_id = "service-user"
    session_id = "service-session"

    blocked = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="Temporary status: tool output cache refreshed for this ticket.",
        task_type="tool_result",
        memory_scope="auto",
    )
    assert blocked["contract_version"] == "memory-service.v1"
    assert blocked["payload"]["memory_written"] is False
    assert blocked["payload"]["write_policy"]["policy"] == "ephemeral_filtered"
    assert blocked["payload"]["content_classification"]["kind"] == "ephemeral_tool_state"
    assert blocked["payload"]["decision_protocol"]["protocol_version"] == "agent-decision.v1"
    assert blocked["payload"]["decision_protocol"]["recommended_action"] == "skip_long_term_write"
    assert blocked["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "skip_long_term_write"

    written = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I always want to see Mayday live one day.",
        task_type="chat",
        memory_scope="auto",
        task_goal="build a personal preference profile",
        context_summary="The agent is learning stable user preferences.",
        working_memory=["user asked about long-term likes"],
    )
    assert written["payload"]["memory_written"] is True
    assert written["payload"]["write_policy"]["should_write"] is True
    assert written["payload"]["memory_resolution"]["action"] == "new_memory"
    assert written["payload"]["decision_protocol"]["safe_to_execute"] is True
    assert written["payload"]["task_goal"] == "build a personal preference profile"
    assert written["payload"]["working_memory"] == ["user asked about long-term likes"]
    assert written["payload"]["agent_handoff"]["can_execute_now"] is True
    assert written["payload"]["agent_handoff"]["block_update_label"] == written["payload"]["block_plan"]["label"]
    assert written["payload"]["execution_policy"]["policy_version"] == "memory-write-execution-policy.v1"
    assert written["payload"]["policy_input"]["service_operation"] == "write_memory"
    assert written["payload"]["policy_input"]["next_action"] == written["payload"]["next_action"]
    assert written["payload"]["recommended_action"] == written["payload"]["decision_protocol"]["recommended_action"]
    assert written["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert written["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert written["payload"]["execution_surface"]["policy_input"] == written["payload"]["policy_input"]
    assert written["payload"]["execution_surface"]["action_surface"] == written["payload"]["action_surface"]
    memory_id = written["payload"]["memory_id"]
    memory_count_after_initial_write = len(agent.repository.list_memories(user_id, limit=20))

    auto_update_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="I always want to see Mayday live someday after work slows down.",
        task_type="chat",
        memory_scope="auto",
    )
    assert auto_update_plan["payload"]["memory_resolution"]["action"] == "suggest_update"
    assert auto_update_plan["payload"]["suggested_action"] == "auto_update_existing_memory"
    assert auto_update_plan["payload"]["consistency_plan"]["governance_mode"] == "auto_safe"
    assert auto_update_plan["payload"]["consistency_plan"]["action_buckets"]["manual_review"] == []

    auto_updated = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I always want to see Mayday live someday after work slows down.",
        task_type="chat",
        memory_scope="auto",
    )
    assert auto_updated["payload"]["memory_written"] is True
    assert auto_updated["payload"]["next_action"] == "memory_updated"
    assert auto_updated["payload"]["memory_id"] == memory_id
    assert len(agent.repository.list_memories(user_id, limit=20)) == memory_count_after_initial_write
    auto_updated_entry = agent.repository.get_memory(user_id, memory_id, include_inactive=True)
    assert auto_updated_entry is not None
    assert auto_updated_entry.text == "I always want to see Mayday live someday after work slows down."

    duplicate = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I always want to see Mayday live someday after work slows down.",
        task_type="chat",
        memory_scope="auto",
    )
    assert duplicate["payload"]["memory_written"] is False
    assert duplicate["payload"]["write_policy"]["policy"] == "deduplicated"
    assert duplicate["payload"]["memory_resolution"]["action"] == "deduplicate"

    duplicate_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="I always want to see Mayday live someday after work slows down.",
        task_type="chat",
        memory_scope="auto",
    )
    assert duplicate_plan["payload"]["memory_resolution"]["action"] == "deduplicate"
    assert duplicate_plan["payload"]["suggested_action"] == "skip_duplicate_write"
    assert duplicate_plan["payload"]["decision_protocol"]["conflict_summary"]["has_conflict"] is True
    assert duplicate_plan["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "skip_duplicate_write"
    assert duplicate_plan["payload"]["consistency_plan"]["plan_version"] == "consistency-plan.v2"
    assert "ambiguous_overlap" in duplicate_plan["payload"]["consistency_plan"]["issue_types"]
    assert "get_memory_history" in duplicate_plan["payload"]["consistency_plan"]["action_buckets"]["manual_review"]
    assert "write_memory" in duplicate_plan["payload"]["execution_guardrails"]["blocked_operations"]
    assert duplicate_plan["payload"]["agent_handoff"]["recommended_operation"] == "skip_duplicate_write"
    assert duplicate_plan["payload"]["agent_handoff"]["memory_resolution_action"] == "deduplicate"
    assert duplicate_plan["payload"]["execution_policy"]["policy_version"] == "memory-write-execution-policy.v1"
    assert duplicate_plan["payload"]["policy_input"]["service_operation"] == "plan_memory_write"
    assert duplicate_plan["payload"]["policy_input"]["next_action"] == duplicate_plan["payload"]["next_action"]
    assert duplicate_plan["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert duplicate_plan["payload"]["action_surface"]["recommended_action"] == duplicate_plan["payload"]["decision_protocol"]["recommended_action"]
    assert duplicate_plan["payload"]["execution_surface"]["action_surface"] == duplicate_plan["payload"]["action_surface"]

    conflict_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="I do not want to see Mayday live someday after work slows down anymore.",
        task_type="chat",
        memory_scope="auto",
    )
    assert conflict_plan["payload"]["memory_resolution"]["action"] == "suggest_update"
    assert conflict_plan["payload"]["active_conflict_scan"]["has_conflict"] is True
    assert any(
        item["conflict_type"] == "textual_contradiction"
        for item in conflict_plan["payload"]["active_conflict_scan"]["conflicts"]
    )
    assert "disputed_fact" in conflict_plan["payload"]["consistency_plan"]["issue_types"]
    assert conflict_plan["payload"]["consistency_plan"]["governance_mode"] in {"manual_review", "confirm_required"}
    assert "write_memory" in conflict_plan["payload"]["execution_guardrails"]["blocked_operations"]
    assert "update_memory" in conflict_plan["payload"]["execution_guardrails"]["confirmation_required_for"]
    aged_entry = agent.repository.get_memory(user_id, memory_id, include_inactive=True)
    assert aged_entry is not None
    aged_entry.created_at = "2023-01-01T00:00:00+00:00"
    stale_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="These days I still want to see Mayday live first.",
        task_type="chat",
        memory_scope="auto",
    )
    assert stale_plan["payload"]["active_conflict_scan"]["has_conflict"] is True
    assert any(
        item["conflict_type"] == "temporal_staleness"
        for item in stale_plan["payload"]["active_conflict_scan"]["conflicts"]
    )
    stale_recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What band do I currently want to see live first?",
        top_k=3,
        include_profile=True,
    )
    assert stale_recall["payload"]["memory_context"]["freshness_guard"]["query_requires_currentness"] is True
    assert stale_recall["payload"]["memory_context"]["freshness_guard"]["risk_level"] in {"medium", "high"}
    assert stale_recall["payload"]["memory_context"]["freshness_guard"]["safe_to_answer_current_state"] is False
    assert "state_current_status_as_verified" in stale_recall["payload"]["response_contract"]["blocked_behaviors"]
    assert stale_recall["payload"]["user_experience_guidance"]["freshness_hint"] == "confirm whether the remembered detail is still current"
    assert stale_recall["payload"]["agent_response_plan"]["freshness_strategy"] == "confirm_current_state_before_answering"
    assert stale_recall["payload"]["agent_handoff"]["can_answer_now"] is False
    assert stale_recall["payload"]["agent_handoff"]["should_confirm"] is True
    assert stale_recall["payload"]["memory_context"]["conflict_profile"]["recommended_resolution"] == "confirm_current_state_before_answer"
    assert stale_recall["payload"]["response_contract"]["conflict_profile"]["freshness_safe"] is False
    assert "stale_fact" in stale_recall["payload"]["consistency_plan"]["issue_types"]
    assert stale_recall["payload"]["consistency_plan"]["issue_summary"]["stale_fact"]["present"] is True
    assert "ask_user_confirmation" in stale_recall["payload"]["consistency_plan"]["action_buckets"]["confirm_required"]
    assert stale_recall["payload"]["consistency_plan"]["action_buckets"]["manual_review"] == []
    assert stale_recall["payload"]["consistency_plan"]["governance_mode"] == "confirm_required"
    stale_ux_report = agent.build_user_experience_report(user_id=user_id, session_id=session_id, limit=50)
    assert stale_ux_report["runtime_scope"]["readiness"] == "acceptable"
    assert stale_ux_report["readiness"] == "acceptable"
    assert stale_ux_report["readiness_basis"] == "runtime_observation"
    assert stale_ux_report["protective_confirmation_count"] >= 1
    assert stale_ux_report["friction_confirmation_count"] == 0
    chinese_recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="我现在最想看的乐队还是五月天吗？",
        top_k=3,
        include_profile=True,
    )
    assert chinese_recall["payload"]["agent_response_plan"]["response_language"] == "zh"
    assert chinese_recall["payload"]["agent_response_plan"]["answer_opening"] in {"根据我记得的，", "按我目前能确认的，", "按我目前记得的，先谨慎说，"}
    assert chinese_recall["payload"]["decision_protocol"]["recommended_action"] == chinese_recall["payload"]["memory_context"]["decision_protocol"]["recommended_action"]

    identity_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="I am a product designer who cares a lot about emotionally meaningful music experiences.",
        task_type="chat",
        memory_scope="auto",
    )
    assert identity_plan["payload"]["content_classification"]["kind"] == "stable_identity"
    assert identity_plan["payload"]["block_plan"]["should_update_block"] is True
    assert "persona_anchor" in identity_plan["payload"]["decision_protocol"]["target_block_labels"]
    assert any(
        item["operation"] == "set_memory_block"
        for item in identity_plan["payload"]["consistency_plan"]["recommended_operations"]
    )

    block = agent.set_memory_block(
        user_id=user_id,
        session_id=session_id,
        label="persona_anchor",
        value="The user has stable music-related preferences and likes emotionally meaningful live events.",
        description="Pinned block for upper-layer response grounding.",
        read_only=False,
        source="agent",
    )
    assert block["payload"]["block"]["label"] == "persona_anchor"
    assert block["payload"]["agent_handoff"]["block_label"] == "persona_anchor"
    assert block["payload"]["agent_handoff"]["recommended_operation"] == "use_block_in_personal_agent_context"
    assert block["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert block["payload"]["action_surface"]["next_action"] == block["payload"]["next_action"]

    recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What live band do I really want to see?",
        top_k=3,
        include_profile=True,
        task_goal="answer from memory",
        context_summary="Need a concise preference-grounded answer.",
        working_memory=["answer should cite memory"],
    )
    assert recall["payload"]["retrieval_candidates"] or recall["payload"]["fallback_memories"]
    assert recall["payload"]["confidence"] > 0
    assert recall["payload"]["retrieval_pipeline"]["supports_rerank"] is True
    assert recall["payload"]["memory_context"]["usage_mode"] in {
        "answer_with_evidence",
        "soft_memory_reference",
        "fallback_memory",
    }
    assert recall["payload"]["memory_context"]["task_goal"] == "answer from memory"
    assert recall["payload"]["memory_context"]["working_memory"] == ["answer should cite memory"]
    assert "facts" in recall["payload"]["memory_context"]
    assert recall["payload"]["decision_protocol"]["protocol_version"] == "agent-decision.v1"
    assert recall["payload"]["memory_context"]["decision_protocol"]["protocol_version"] == "agent-decision.v1"
    assert recall["payload"]["decision_protocol"]["recommended_action"] == recall["payload"]["memory_context"]["decision_protocol"]["recommended_action"]
    assert recall["payload"]["consistency_plan"]["status"] in {"review", "clear", "conflicted"}
    assert recall["payload"]["memory_context"]["consistency_plan"]["recommended_operations"]
    assert recall["payload"]["response_contract"]["citation_required"] is True
    assert recall["payload"]["preferred_surface"] == "agent_bundle"
    assert "invent_missing_details" in recall["payload"]["response_contract"]["blocked_behaviors"]
    assert recall["payload"]["response_guardrails"]["mode"] in {"auto", "restricted", "confirmation_required"}
    assert recall["payload"]["execution_policy"]["policy_version"] == "memory-recall-execution-policy.v1"
    assert recall["payload"]["policy_input"]["resolution_flow"] in {
        "grounded_answer_flow",
        "confirm_then_answer_flow",
        "fallback_memory_flow",
        "no_grounded_answer_flow",
    }
    assert recall["payload"]["policy_input"]["citation_required"] is True
    assert recall["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert recall["payload"]["execution_surface"]["policy_input"] == recall["payload"]["policy_input"]
    assert recall["payload"]["execution_surface"]["agent_handoff"] == recall["payload"]["agent_handoff"]
    assert recall["payload"]["execution_surface"]["response_contract"] == recall["payload"]["response_contract"]
    assert recall["payload"]["execution_surface"]["response_guardrails"] == recall["payload"]["response_guardrails"]
    assert recall["payload"]["user_experience_guidance"]["feedback_strategy"] == "passive_first"
    assert recall["payload"]["memory_context"]["user_experience_guidance"]["should_avoid_internal_details"] is True
    assert recall["payload"]["agent_response_plan"]["mode"] in {"answer", "confirm_then_answer", "no_grounded_answer"}
    assert recall["payload"]["agent_response_plan"]["response_language"] == "en"
    assert recall["payload"]["agent_handoff"]["response_preview"] == recall["payload"]["agent_response_plan"]["answer_skeleton"]
    assert recall["payload"]["agent_handoff"]["can_answer_now"] == recall["payload"]["response_contract"]["ready_for_agent_answer"]
    assert recall["payload"]["agent_handoff"]["should_confirm"] == recall["payload"]["memory_context"]["requires_user_confirmation"]
    assert recall["payload"]["agent_handoff"]["version_status"] in {"stable", "disputed", "inactive"}
    assert recall["payload"]["memory_context"]["agent_handoff"]["primary_operation"] == recall["payload"]["memory_context"]["consistency_plan"]["recommended_operations"][0]["operation"]
    assert recall["payload"]["memory_context"]["agent_response_plan"]["answer_skeleton"]
    assert recall["payload"]["memory_context"]["execution_policy"]["policy_version"] == "memory-recall-execution-policy.v1"
    assert recall["payload"]["memory_context"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert recall["payload"]["memory_context"]["recommended_usage"] in {
        "answer_directly",
        "answer_with_evidence",
        "answer_cautiously",
        "ask_user_confirmation",
    }
    block_labels = [item["label"] for item in recall["payload"]["core_memory_blocks"]]
    assert "persona_anchor" in block_labels
    assert "derived_profile" in block_labels

    thin_recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What live band do I really want to see?",
        top_k=3,
        include_profile=True,
        response_mode="execution_surface",
    )
    assert thin_recall["payload"]["preferred_surface"] == "execution_surface"
    assert thin_recall["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    updated = agent.update_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        text="I always want to see Mayday and Coldplay live one day.",
        source="agent",
        task_goal="refresh stable music preferences",
        context_summary="The user clarified another long-term concert preference.",
        working_memory=["merge with prior preference memory"],
    )
    assert updated["payload"]["updated"] is True
    assert updated["payload"]["memory"]["text"] == "I always want to see Mayday and Coldplay live one day."
    assert updated["payload"]["history"]
    assert updated["payload"]["history"][-1]["action"] == "update"
    assert updated["payload"]["decision_protocol"]["recommended_action"] == "memory_updated"
    assert updated["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
    assert updated["payload"]["agent_handoff"]["recommended_operation"] == "get_memory_history"
    assert updated["payload"]["agent_handoff"]["target_memory_ids"] == [memory_id]
    assert updated["payload"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
    assert updated["payload"]["consistency_maintenance"]["primary_memory_id"] == memory_id
    assert updated["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert updated["payload"]["recommended_action"] == updated["payload"]["decision_protocol"]["recommended_action"]
    assert updated["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert updated["payload"]["action_surface"]["next_action"] == updated["payload"]["next_action"]
    assert updated["payload"]["policy_input"]["lifecycle_operation"] == "update_memory"
    assert updated["payload"]["policy_input"]["service_operation"] == "update_memory"
    assert updated["payload"]["policy_input"]["next_action"] == updated["payload"]["next_action"]
    assert updated["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert updated["payload"]["execution_surface"]["policy_input"] == updated["payload"]["policy_input"]
    assert updated["payload"]["execution_surface"]["agent_handoff"] == updated["payload"]["agent_handoff"]
    assert updated["payload"]["execution_surface"]["action_surface"] == updated["payload"]["action_surface"]

    related = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I still want to see Coldplay live too.",
        task_type="chat",
        memory_scope="auto",
    )
    assert related["payload"]["memory_resolution"]["action"] in {"suggest_update", "new_memory"}

    related_plan = agent.plan_memory_write(
        user_id=user_id,
        session_id=session_id,
        text="I still want to see Coldplay live too.",
        task_type="chat",
        memory_scope="auto",
    )
    assert related_plan["payload"]["memory_resolution"]["action"] in {"suggest_update", "new_memory"}

    updated_recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="Which bands do I want to see live?",
        top_k=3,
        include_profile=True,
    )
    top_text = (updated_recall["payload"]["recalled_memory"] or {}).get("text", "")
    assert "Coldplay" in top_text

    forgotten = agent.forget_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason="user said this preference is outdated",
        source="agent",
    )
    assert forgotten["payload"]["forgotten"] is True
    assert forgotten["payload"]["history"][-1]["action"] == "forget"
    assert forgotten["payload"]["memory_state"]["status"] == "forgotten"
    assert forgotten["payload"]["decision_protocol"]["target_memory_ids"] == [memory_id]
    assert forgotten["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
    assert forgotten["payload"]["agent_handoff"]["state_status"] == "forgotten"
    assert forgotten["payload"]["agent_handoff"]["target_memory_ids"] == [memory_id]
    assert forgotten["payload"]["consistency_maintenance"]["next_bucket"] in {"manual_review", "confirm_required", "auto_safe"}
    assert forgotten["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert forgotten["payload"]["policy_input"]["lifecycle_operation"] == "forget_memory"
    assert forgotten["payload"]["policy_input"]["service_operation"] == "forget_memory"
    assert forgotten["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert forgotten["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert forgotten["payload"]["execution_surface"]["action_surface"] == forgotten["payload"]["action_surface"]

    snapshot = agent.get_user_snapshot(user_id=user_id, limit=10)
    assert all(item["memory_id"] != memory_id for item in snapshot["memories"])

    history_view = agent.get_memory_history(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
    )
    assert history_view["payload"]["history_count"] >= 2
    assert any(item["action"] == "update" for item in history_view["payload"]["history"])
    assert any(item["action"] == "forget" for item in history_view["payload"]["history"])
    assert history_view["payload"]["decision_protocol"]["recommended_action"] == "inspect_memory_history"
    assert history_view["payload"]["consistency_plan"]["recommended_operations"]
    assert history_view["payload"]["agent_handoff"]["recommended_operation"] == history_view["payload"]["consistency_plan"]["recommended_operations"][0]["operation"]
    assert history_view["payload"]["consistency_maintenance"]["action_buckets"]["manual_review"]
    assert history_view["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert history_view["payload"]["policy_input"]["lifecycle_operation"] == "get_memory_history"
    assert history_view["payload"]["policy_input"]["service_operation"] == "get_memory_history"
    assert history_view["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert history_view["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert history_view["payload"]["execution_surface"]["action_surface"] == history_view["payload"]["action_surface"]

    restored = agent.restore_memory(
        user_id=user_id,
        session_id=session_id,
        memory_id=memory_id,
        reason="the preference is still valid",
        source="agent",
    )
    assert restored["payload"]["restored"] is True
    assert restored["payload"]["memory_state"]["status"] == "active"
    assert restored["payload"]["decision_protocol"]["recommended_action"] == "memory_restored"
    assert restored["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
    assert restored["payload"]["agent_handoff"]["state_status"] == "active"
    assert restored["payload"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
    assert restored["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert restored["payload"]["policy_input"]["lifecycle_operation"] == "restore_memory"
    assert restored["payload"]["policy_input"]["service_operation"] == "restore_memory"
    assert restored["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert restored["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert restored["payload"]["execution_surface"]["action_surface"] == restored["payload"]["action_surface"]

    replacement = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="I prefer to see Coldplay live before other bands now.",
        task_type="chat",
        memory_scope="auto",
    )
    replacement_id = replacement["payload"]["memory_id"]
    superseded = agent.supersede_memory(
        user_id=user_id,
        session_id=session_id,
        source_memory_id=memory_id,
        replacement_memory_id=replacement_id,
        reason="newer preference statement is more specific",
        source="agent",
    )
    assert superseded["payload"]["superseded"] is True
    assert superseded["payload"]["source_state"]["status"] == "superseded"
    assert superseded["payload"]["decision_protocol"]["conflict_summary"]["has_conflict"] is True
    assert superseded["payload"]["consistency_plan"]["risk_level"] in {"medium", "high"}
    assert superseded["payload"]["agent_handoff"]["target_memory_ids"] == [memory_id, replacement_id]
    assert superseded["payload"]["consistency_maintenance"]["related_memory_ids"] == [replacement_id]
    assert superseded["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert superseded["payload"]["policy_input"]["lifecycle_operation"] == "supersede_memory"
    assert superseded["payload"]["policy_input"]["service_operation"] == "supersede_memory"
    assert superseded["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert superseded["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert superseded["payload"]["execution_surface"]["action_surface"] == superseded["payload"]["action_surface"]

    superseded_recall = agent.recall_memory(
        user_id=user_id,
        session_id=session_id,
        query_text="What was my earlier live-show preference?",
        top_k=3,
        include_profile=True,
    )
    assert "recommended_usage" in superseded_recall["payload"]["memory_context"]
    assert superseded_recall["payload"]["memory_context"]["decision_protocol"]["operation"] == "recall_memory"
    assert superseded_recall["payload"]["memory_context"]["conflict_profile"]["version_status"] in {"inactive", "disputed", "stable"}
    assert "conflict_profile" in superseded_recall["payload"]["response_contract"]

    duplicate_memory = agent.write_memory(
        user_id=user_id,
        session_id=session_id,
        text="Coldplay is my main live-show target now.",
        task_type="chat",
        memory_scope="auto",
        force_write=True,
    )
    duplicate_id = duplicate_memory["payload"]["memory_id"]
    merged = agent.merge_memories(
        user_id=user_id,
        session_id=session_id,
        source_memory_id=duplicate_id,
        target_memory_id=replacement_id,
        reason="duplicate preference memory",
        source="agent",
    )
    assert merged["payload"]["merged"] is True
    assert merged["payload"]["source_state"]["status"] == "merged"
    assert replacement_id in [replacement_id, merged["payload"]["target_state"]["memory_id"]]
    assert merged["payload"]["decision_protocol"]["target_memory_ids"] == [duplicate_id, replacement_id]
    assert merged["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "get_memory_history"
    assert merged["payload"]["agent_handoff"]["target_memory_ids"] == [duplicate_id, replacement_id]
    assert merged["payload"]["consistency_maintenance"]["related_memory_ids"] == [replacement_id]
    assert merged["payload"]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert merged["payload"]["policy_input"]["lifecycle_operation"] == "merge_memories"
    assert merged["payload"]["policy_input"]["service_operation"] == "merge_memories"
    assert merged["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert merged["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert merged["payload"]["execution_surface"]["action_surface"] == merged["payload"]["action_surface"]

    deleted_block = agent.delete_memory_block(
        user_id=user_id,
        session_id=session_id,
        label="persona_anchor",
    )
    assert deleted_block["payload"]["deleted"] is True
    assert deleted_block["payload"]["decision_protocol"]["target_block_labels"] == ["persona_anchor"]
    assert deleted_block["payload"]["consistency_plan"]["recommended_operations"][0]["operation"] == "refresh_core_block_cache"
    assert deleted_block["payload"]["agent_handoff"]["deleted"] is True
    assert deleted_block["payload"]["agent_handoff"]["recommended_operation"] == "refresh_core_block_cache"
    assert deleted_block["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"

    reflection = agent.reflect_memory(
        user_id=user_id,
        session_id=session_id,
        persist=False,
    )
    assert "reflection" in reflection["payload"]
    assert reflection["payload"]["agent_handoff"]["reflection_available"] in {True, False}
    assert reflection["payload"]["agent_handoff"]["recommended_operation"] == "use_reflection_summary"
    assert reflection["payload"]["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert reflection["payload"]["execution_policy"]["policy_version"] == "memory-reflection-execution-policy.v1"
    assert reflection["payload"]["policy_input"]["service_operation"] == "reflect_memory"
    assert reflection["payload"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert reflection["payload"]["execution_surface"]["policy_input"] == reflection["payload"]["policy_input"]
    assert reflection["payload"]["execution_surface"]["execution_policy"] == reflection["payload"]["execution_policy"]
    assert reflection["payload"]["execution_surface"]["action_surface"] == reflection["payload"]["action_surface"]
    assert reflection["payload"]["execution_surface"]["agent_handoff"] == reflection["payload"]["agent_handoff"]

    storage_report = agent.get_storage_report()
    assert storage_report["integrity_ok"] is True
    assert "integrity_checks" in storage_report
    assert "migration" in storage_report
    assert "recovery" in storage_report
    assert "backup_inventory" in storage_report
    assert "observability" in storage_report
    assert "operator_checklist" in storage_report
    assert storage_report["operator_decision_path"]["decision_path_version"] == "storage-operator-decision-path.v1"
    assert storage_report["operator_acceptance_note"]["note_version"] == "storage-acceptance-note.v1"
    assert storage_report["remediation_checklist"]["checklist_version"] == "storage-remediation-checklist.v1"
    assert "deployment_guidance" in storage_report
    assert "persistence_confidence" in storage_report
    assert storage_report["preferred_primary_backend"] in {"json", "sqlite"}
    assert storage_report["primary_mode_status"] in {"healthy_primary", "degraded_fallback", "blocked"}
    assert storage_report["primary_storage"]["contract_version"] == "storage-primary-path.v1"
    assert storage_report["policy_input"]["resolution_flow"] in {
        "storage_recovery_flow",
        "storage_primary_path_hardening_flow",
        "storage_backup_refresh_flow",
        "storage_health_maintenance_flow",
    }
    assert storage_report["execution_policy"]["policy_version"] == "storage-execution-policy.v1"
    assert storage_report["execution_policy"]["primary_path"]["mode_status"] == storage_report["primary_mode_status"]
    assert storage_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert storage_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert storage_report["operator_decision_path"]["primary_storage_mode"] == storage_report["primary_mode_status"]
    assert storage_report["operator_acceptance_note"]["primary_storage_mode"] == storage_report["primary_mode_status"]
    assert storage_report["remediation_checklist"]["mode"] == storage_report["primary_mode_status"]
    assert storage_report["migration"]["schema_status"] in {"aligned", "unknown", "drifted"}
    assert storage_report["migration"]["policy_version"] == "storage-migration-policy.v1"
    assert storage_report["migration"]["preflight"]["status"] in {"ready", "review", "blocked"}
    assert storage_report["migration"]["rollback"]["strategy"] == "restore_latest_verified_backup"
    assert "rollback_evidence" in storage_report["migration"]["rollback"]
    assert storage_report["migration"]["latest_attempt"]["status"] in {"not_run", "ready", "review", "blocked", "unknown"}
    assert storage_report["migration"]["migration_acceptance"]["contract_version"] == "migration-acceptance.v1"
    assert "latest_restore_drill" in storage_report["recovery"]
    assert "last_restore_drill_at" in storage_report["recovery"]
    assert "last_restore_drill_age_hours" in storage_report["recovery"]
    assert storage_report["recovery"]["restore_drill_freshness"]["contract_version"] == "restore-drill-freshness.v1"
    assert storage_report["recovery"]["last_restore_drill_status"] in {"missing", "passed", "failed", "unknown"}
    assert storage_report["recovery"]["restore_confidence"] in {"low", "medium", "high"}
    assert storage_report["recovery"]["recovery_confidence"] in {"low", "medium", "high"}
    assert "restore_drill_acceptance" in storage_report["operator_decision_path"]
    assert storage_report["agent_handoff"]["report_type"] == "storage"

    backup_payload = agent.create_storage_backup()
    assert backup_payload["execution_policy"]["policy_version"] == "report-execution-policy.v1"
    assert backup_payload["policy_input"]["artifact_type"] == "storage_backup"
    assert backup_payload["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert backup_payload["execution_surface"]["action_surface"] == backup_payload["action_surface"]

    restore_drill_payload = agent.run_storage_restore_drill()
    assert restore_drill_payload["execution_policy"]["policy_version"] == "report-execution-policy.v1"
    assert restore_drill_payload["policy_input"]["artifact_type"] == "storage_restore_drill"
    assert restore_drill_payload["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert restore_drill_payload["execution_surface"]["action_surface"] == restore_drill_payload["action_surface"]

    migration_preflight_payload = agent.run_storage_migration_preflight()
    assert migration_preflight_payload["execution_policy"]["policy_version"] == "report-execution-policy.v1"
    assert migration_preflight_payload["policy_input"]["artifact_type"] == "storage_migration_preflight"
    assert migration_preflight_payload["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert migration_preflight_payload["execution_surface"]["action_surface"] == migration_preflight_payload["action_surface"]

    integration_report = agent.build_integration_flow_report(user_id=user_id, session_id=session_id, limit=50)
    assert integration_report["required_capabilities"]["memory_recall"] is True
    assert integration_report["coverage"]["decision_protocol_records"] >= 1
    assert integration_report["coverage"]["response_plan_records"] >= 1
    assert integration_report["agent_handoff"]["report_type"] == "integration_flow"
    assert integration_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert integration_report["execution_policy"]["policy_version"] == "report-execution-policy.v1"
    assert integration_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert "scenario_checks" in integration_report
    assert "scenario_status" in integration_report
    assert "chat_loop" in integration_report["scenario_checks"]
    assert "consistency_loop" in integration_report["scenario_checks"]
    assert "execution_surface" in integration_report
    assert "recommended_call_flows" in integration_report
    assert "anti_patterns" in integration_report

    training_report = agent.build_training_protocol_report(user_id=user_id, limit=50)
    assert training_report["training_sample_count"] >= 1
    assert training_report["labeled_sample_count"] >= 1
    assert training_report["protocol_labeled_sample_count"] >= 1
    assert training_report["response_contract_record_count"] >= 1
    assert training_report["response_plan_record_count"] >= 1
    assert training_report["labeling_mode"] in {"protocol_labeled", "hybrid", "feedback_attached"}
    assert training_report["agent_handoff"]["report_type"] == "training_protocol"
    assert training_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert training_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    ux_report = agent.build_user_experience_report(user_id=user_id, session_id=session_id, limit=50)
    assert ux_report["report_type"] == "user_experience"
    assert ux_report["comfort_score"] >= 0
    assert ux_report["ready_answer_ratio"] >= 0
    assert ux_report["readiness_basis"] in {"runtime_observation", "thin_runtime_scope_normalized"}
    assert "runtime_scope" in ux_report
    assert "recommendations" in ux_report
    assert ux_report["agent_handoff"]["report_type"] == "user_experience"
    assert ux_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert ux_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    consistency_report = agent.build_consistency_audit_report(user_id=user_id, limit=50)
    assert consistency_report["report_type"] == "consistency_audit"
    assert "revised_fact_count" in consistency_report
    assert consistency_report["old_fact_count"] + consistency_report["inactive_version_count"] >= 1
    assert "disputed_fact_count" in consistency_report
    assert "lifecycle_state" in consistency_report["consistency_type_counts"]
    assert consistency_report["governance_mode"] in {"auto_safe", "confirm_required", "manual_review"}
    assert set(consistency_report["action_buckets"]) == {"auto_safe", "confirm_required", "manual_review"}
    assert consistency_report["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
    assert consistency_report["consistency_maintenance"]["governance_mode"] == consistency_report["governance_mode"]
    assert "operator_action_buckets" in consistency_report
    assert "agent_action_buckets" in consistency_report
    assert consistency_report["maintenance_jobs"]
    assert consistency_report["lifecycle_execution_paths"]
    assert consistency_report["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
    assert consistency_report["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
    assert consistency_report["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
    assert consistency_report["operator_review_order"]["surface_version"] == "operator-review-order.v1"
    assert consistency_report["recommended_operations"]
    assert "recommendations" in consistency_report
    assert consistency_report["agent_handoff"]["report_type"] == "consistency_audit"
    assert consistency_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert consistency_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    hygiene_report = agent.build_memory_hygiene_report(user_id=user_id, limit=50)
    assert hygiene_report["report_type"] == "memory_hygiene"
    assert hygiene_report["memory_count"] >= 1
    assert hygiene_report["recommended_operations"]
    assert "recommendations" in hygiene_report
    assert hygiene_report["agent_handoff"]["report_type"] == "memory_hygiene"
    assert hygiene_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert hygiene_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    release_report = agent.build_release_readiness_report(user_id=user_id, session_id=session_id, limit=50)
    assert release_report["report_type"] == "release_readiness"
    assert release_report["readiness"] in {"market_pilot_ready", "limited_pilot", "internal_only"}
    assert "memory_hygiene" in release_report
    assert "consistency" in release_report
    assert release_report["consistency"]["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
    assert release_report["consistency"]["maintenance_jobs"]
    assert release_report["consistency"]["lifecycle_execution_paths"]
    assert release_report["consistency"]["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
    assert release_report["consistency"]["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
    assert release_report["consistency"]["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
    assert release_report["consistency"]["operator_review_order"]["surface_version"] == "operator-review-order.v1"
    assert release_report["recommended_lifecycle_execution"]["surface_version"] == "agent-execution-surface.v1"
    assert release_report["consistency"]["lifecycle_execution_paths"][0]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert release_report["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
    assert release_report["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
    assert release_report["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
    assert release_report["operator_review_order"]["surface_version"] == "operator-review-order.v1"
    assert release_report["readiness_source_map"]["integration_flow_blocked"]["source_report"] == "integration_flow"
    assert release_report["readiness_source_map"]["user_experience_risky"]["recommended_action"] == "reduce_user_friction"
    assert release_report["baseline_summary"]["contract_version"] == "readiness-baseline-summary.v1"
    assert isinstance(release_report["active_readiness_sources"], list)
    assert "next_focus" in release_report
    assert release_report["agent_handoff"]["report_type"] == "release_readiness"
    assert release_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert release_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    readiness_summary = agent.build_agent_readiness_summary(user_id=user_id, session_id=session_id, limit=50)
    assert readiness_summary["report_type"] == "agent_readiness_summary"
    assert "surface_status" in readiness_summary
    assert readiness_summary["surface_status"]["retrieval"] in {"ready", "review"}
    assert readiness_summary["execution_policy"]["policy_version"] == "agent-execution-policy.v1"
    assert readiness_summary["policy_input"]["resolution_flow"] in {
        "standard_chat_flow",
        "guarded_recall_flow",
        "plan_then_write_flow",
        "consistency_resolution_flow",
        "storage_recovery_flow",
    }
    assert isinstance(readiness_summary["policy_input"]["can_answer_now"], bool)
    assert isinstance(readiness_summary["policy_input"]["can_write_now"], bool)
    assert isinstance(readiness_summary["policy_input"]["should_confirm"], bool)
    assert readiness_summary["retrieval_runtime_advice"]["advice_version"] == "retrieval-runtime-advice.v1"
    assert readiness_summary["agent_handoff"]["report_type"] == "agent_readiness_summary"
    assert readiness_summary["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert readiness_summary["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert readiness_summary["execution_surface"]["policy_input"] == readiness_summary["policy_input"]
    assert readiness_summary["execution_surface"]["execution_policy"] == readiness_summary["execution_policy"]
    assert readiness_summary["execution_surface"]["agent_handoff"] == readiness_summary["agent_handoff"]
    assert readiness_summary["storage_handoff"]["report_type"] == "storage"
    assert readiness_summary["consistency_handoff"]["report_type"] == "consistency_audit"
    assert readiness_summary["consistency_maintenance"]["surface_version"] == "consistency-maintenance-surface.v1"
    assert readiness_summary["consistency_agent_action_buckets"]
    assert readiness_summary["consistency_maintenance_jobs"]
    assert readiness_summary["consistency_lifecycle_execution_paths"]
    assert readiness_summary["recommended_lifecycle_execution"]["surface_version"] == "agent-execution-surface.v1"
    assert readiness_summary["consistency_lifecycle_execution_paths"][0]["execution_policy"]["policy_version"] == "memory-lifecycle-execution-policy.v1"
    assert readiness_summary["ops_metric_surface"]["surface_version"] == "ops-metric-surface.v1"
    assert readiness_summary["audit_signal_surface"]["surface_version"] == "ops-audit-surface.v1"
    assert readiness_summary["error_taxonomy"]["surface_version"] == "ops-error-taxonomy.v1"
    assert readiness_summary["operator_review_order"]["surface_version"] == "operator-review-order.v1"
    assert readiness_summary["readiness_source_map"]["training_protocol_partial"]["source_report"] == "training_protocol"
    assert isinstance(readiness_summary["active_readiness_sources"], list)
    assert readiness_summary["baseline_summary"]["contract_version"] == "readiness-baseline-summary.v1"

    readiness_baseline = agent.build_readiness_baseline_report(user_id=user_id, session_id=session_id, limit=50)
    assert readiness_baseline["report_type"] == "readiness_baseline"
    assert readiness_baseline["baseline_version"] == "readiness-baseline.v1"
    assert readiness_baseline["scope"]["scope_mode"] == "scoped"
    assert readiness_baseline["source_map"]["integration_flow_blocked"]["next_phase"] == "Phase B"
    assert readiness_baseline["source_map"]["user_experience_risky"]["resolution_flow"] == "user_experience_review"
    assert isinstance(readiness_baseline["active_sources"], list)
    assert readiness_baseline["phase_targets"][0]["phase"] == "Phase B"
    assert "agent_execution" in readiness_baseline["evidence_snapshot"]
    assert readiness_baseline["agent_handoff"]["report_type"] == "readiness_baseline"
    assert readiness_baseline["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert readiness_baseline["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    retrieval_report = agent.build_retrieval_backend_report()
    assert "control_plane" in retrieval_report["pipeline_profile"]
    assert retrieval_report["pipeline_profile"]["control_plane"]["recall"]["stages"]
    assert "validation_notes" in retrieval_report
    assert retrieval_report["control_plane_status"]["readiness"] in {"ready", "review"}
    assert "task_fit" in retrieval_report
    assert retrieval_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert retrieval_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert retrieval_report["runtime_advice"]["response_policy"]["mode"] in {
        "grounded_answer",
        "confirm_on_ambiguity",
        "avoid_strong_answer_on_thin_candidate_pool",
    }

    export_payload = agent.repository.export_offline_review_dataset(limit=20, user_id=user_id)
    assert export_payload["count"] >= 2
    dataset = json.loads(open(export_payload["path"], "r", encoding="utf-8").read())
    assert dataset["samples"][0]["candidate_training_rows"] is not None
    assert "operations" in dataset["manifest"]
    assert "ux_guided_samples" in dataset["manifest"]
    assert "response_plan_samples" in dataset["manifest"]

    long_horizon = agent.run_long_horizon_validation(
        user_id=f"{user_id}-long",
        session_id=f"{session_id}-long",
        limit=50,
    )
    assert long_horizon["report_type"] == "long_horizon_validation"
    assert long_horizon["validation_version"] == "long-horizon-validation.v1"
    assert long_horizon["workload_profile"]["profile_count"] == 3
    assert long_horizon["workload_profile"]["day_count"] == 3
    assert long_horizon["workload_profile"]["aggregate_day_count"] == 9
    assert len(long_horizon["workload_profiles"]) == 3
    assert long_horizon["metrics"]["recall_stability_rate"] >= 0
    assert long_horizon["metrics"]["lifecycle_resolution_rate"] >= 0
    assert long_horizon["metrics"]["task_switch_stability_rate"] >= 0
    assert long_horizon["metrics"]["conflict_detection_rate"] >= 0
    assert long_horizon["counts"]["recall_count"] >= 12
    assert long_horizon["counts"]["task_switch_count"] == 3
    assert long_horizon["counts"]["conflict_check_count"] == 3
    assert long_horizon["artifacts"]["artifact_path"].endswith(".json")
    assert long_horizon["supporting_reports"]["consistency"]["governance_mode"] in {"auto_safe", "confirm_required", "manual_review"}
    assert "storage" in long_horizon["supporting_reports"]
    assert long_horizon["supporting_reports"]["storage"]["primary_mode_status"] in {"healthy_primary", "degraded_fallback", "blocked"}
    assert long_horizon["supporting_reports"]["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
    assert long_horizon["supporting_reports"]["phase_e_stability"]["stability_posture"] in {"stable", "watch", "investigate"}
    assert long_horizon["evidence_boundary"]["contract_version"] == "long-horizon-evidence-boundary.v1"
    assert long_horizon["evidence_boundary"]["benchmark_evidence_family"] == "benchmark_evaluation"
    assert long_horizon["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert long_horizon["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    long_horizon_multi_run = agent.build_long_horizon_multi_run_summary(limit=5)
    assert long_horizon_multi_run["report_type"] == "long_horizon_validation_multi_run_summary"
    assert long_horizon_multi_run["contract_version"] == "long-horizon-multi-run-summary.v1"
    assert long_horizon_multi_run["run_count"] >= 1
    assert long_horizon_multi_run["aggregate_metrics"]["recall_stability_rate"]["latest"] >= 0
    assert len(long_horizon_multi_run["profile_summaries"]) == 3
    assert long_horizon_multi_run["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
    assert (
        long_horizon_multi_run["phase_e_stability"]["stable_run_count"]
        + long_horizon_multi_run["phase_e_stability"]["watch_run_count"]
        + long_horizon_multi_run["phase_e_stability"]["investigate_run_count"]
    ) == long_horizon_multi_run["run_count"]
    assert long_horizon_multi_run["benchmark_boundary"]["contract_version"] == "long-horizon-evidence-boundary.v1"
    assert long_horizon_multi_run["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert long_horizon_multi_run["execution_surface"]["surface_version"] == "agent-execution-surface.v1"

    system_report = agent.build_system_report()
    assert system_report["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert system_report["action_surface"]["surface_version"] == "agent-action-surface.v1"
    assert system_report["retrieval_backend_report"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert system_report["long_horizon_validation_summary"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert system_report["long_horizon_multi_run_summary"]["execution_surface"]["surface_version"] == "agent-execution-surface.v1"
    assert system_report["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"
    assert system_report["evidence_surfaces"]["phase_e_stability"]["surface_version"] == "phase-e-stability.v1"


def test_integration_flow_demo_generates_readiness_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "integration_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_FEEDBACK_STORE_FILE", str(tmp_path / "integration_feedback.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_INTERACTION_LOG_FILE", str(tmp_path / "integration_interactions.jsonl"))
    monkeypatch.setenv("MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE", str(tmp_path / "integration_retrieval.json"))

    agent = build_default_agent()
    payload = agent.run_integration_flow_demo(
        user_id="integration-user",
        session_id="integration-session",
        limit=100,
    )

    integration_report = payload["reports"]["integration_flow"]
    assert integration_report["readiness"] == "ready"
    assert all(integration_report["required_capabilities"].values())
    assert all(integration_report["scenario_status"].values())
    assert payload["artifacts"]["integration_flow_artifact_path"].endswith(".json")

    training_report = payload["reports"]["training_protocol"]
    assert training_report["readiness"] == "ready"
    assert training_report["labeled_sample_count"] >= 1

    readiness_summary = payload["reports"]["agent_readiness_summary"]
    assert readiness_summary["readiness"] in {"limited_pilot", "market_pilot_ready"}
    assert readiness_summary["surface_status"]["integration"] == "ready"
    assert readiness_summary["policy_input"]["resolution_flow"] in {
        "standard_chat_flow",
        "guarded_recall_flow",
        "plan_then_write_flow",
        "consistency_resolution_flow",
        "storage_recovery_flow",
    }

    bridged_report = agent.build_integration_flow_report(
        user_id="thin-scope-user",
        session_id="thin-scope-session",
        limit=50,
    )
    assert bridged_report["runtime_scope"]["readiness"] == "blocked"
    assert bridged_report["integration_evidence"]["readiness"] == "ready"
    assert bridged_report["evidence_bridge"]["applied"] is True
    assert bridged_report["evidence_bridge"]["readiness_basis"] == "validated_integration_evidence"
    assert bridged_report["readiness"] == "ready"
    assert bridged_report["missing_capabilities"] == []
    assert all(bridged_report["required_capabilities"].values())
