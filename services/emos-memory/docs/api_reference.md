# API Reference

## Delivery Position

- EMOS is delivered as an independent memory engine / memory service.
- The upper-layer personal agent is expected to call EMOS through stable API contracts rather than reimplementing memory policy itself.
- The default delivery mode for the current sprint is local/private deployment first.
- The sprint scope is tracked in [delivery_sprint_plan_20260425_20260502.md](docs/delivery_sprint_plan_20260425_20260502.md).

## Integration Contract Summary

- Preferred integration style: upper-layer agent calls EMOS through narrow memory-service contracts instead of reconstructing memory policy from generic endpoints.
- Preferred discovery/onboarding path for a new agent team:
  - `GET /`
  - `GET /openapi.json`
  - `GET /system/agent-api-manifest`
  - [agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md)
  - [agent_api_endpoint_catalog.md](docs/agent_api_endpoint_catalog.md)
  - [agent_api_quickstart.md](docs/agent_api_quickstart.md)
  - [agent_api_client.py](examples/agent_api_client.py)
  - [agent_api_requests.http](examples/agent_api_requests.http)
- Preferred recall consumption path:
  - `payload.execution_surface.policy_input`
  - `payload.execution_surface.execution_policy`
  - `payload.execution_surface.agent_handoff`
  - `payload.execution_surface.response_contract`
  - `payload.execution_surface.response_guardrails`
- Preferred system-readiness consumption path:
  - `execution_surface.policy_input`
  - `execution_surface.execution_policy`
  - `execution_surface.agent_handoff`
- Preferred storage/operator consumption path:
  - `storage_report.execution_surface`
  - `storage_report.operator_checklist`
  - `storage_report.deployment_guidance`
  - `storage_backup.verification`
  - `delivery_pack.storage_report`
- SQLite runtime path note:
  - if `MEMORY_SYSTEM_SQLITE_FILE` is explicitly set, EMOS uses that path directly
  - otherwise, EMOS prefers the configured SQLite sibling path when it is ASCII-safe
  - when the workspace path is not SQLite-safe, EMOS automatically shifts the live SQLite runtime to an ASCII-safe local runtime path and bootstraps JSON state into SQLite
- Preferred handoff-facing migration and rollback review sequence:
  - `migration.preflight`
  - `migration.latest_attempt`
  - `migration.rollback`
  - `migration.migration_acceptance`

## Agent API Discovery

### `GET /`

Returns the API landing surface for external agent teams.

Highlights:

- `service`
- `status`
- `health`
- `openapi`
- `agent_api_manifest`

Recommended use:

- use as the first probe when an upper-layer agent team receives a fresh EMOS deployment
- confirm that the runtime exposes the OpenAPI document and the agent manifest before wiring memory calls
- pair it with [agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md) when the receiver needs to deploy EMOS on their own laptop/workstation

### `GET /openapi.json`

Returns the machine-readable OpenAPI 3.1 contract for the main agent-facing HTTP JSON endpoints.

Highlights:

- `openapi`
- `info`
- `servers`
- `paths`
- `components.schemas`

Recommended use:

- generate or validate client bindings
- inspect request models for `write-plan / write / recall / lifecycle`
- use together with `GET /system/agent-api-manifest` rather than inferring integration order from raw paths alone

### `GET /system/agent-api-manifest`

Returns the preferred agent-facing API contract summary for upper-layer personal-agent teams.

Highlights:

- `contract_version`
- `service_name`
- `agent_entrypoints`
- `supporting_entrypoints`
- `preferred_read_order`
- `recommended_call_flows`

Recommended use:

- treat this as the canonical EMOS integration manifest
- read it before implementing orchestration logic
- pair it with [agent_api_quickstart.md](docs/agent_api_quickstart.md), [agent_api_client.py](examples/agent_api_client.py), and [agent_api_requests.http](examples/agent_api_requests.http) for a minimal first integration

## Local Deployment Notes

- Default API bind address:
  - host: `127.0.0.1`
  - port: `8000`
- API bind overrides:
  - `MEMORY_SYSTEM_API_HOST`
  - `MEMORY_SYSTEM_API_PORT`
- Default startup path:
  - `.\scripts\run_api.ps1`
- Preferred receiver-facing deployment docs:
  - [agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md)
  - [agent_api_endpoint_catalog.md](docs/agent_api_endpoint_catalog.md)

## Delivery Artifact Surfaces

The current delivery package is expected to expose three direct artifact families:

- integration artifacts:
  - recall, write, lifecycle, and readiness contracts for the upper-layer personal agent
- operator artifacts:
  - storage report, storage backup, and storage runbook for private deployment
- delivery artifacts:
  - delivery-pack JSON/Markdown outputs for review and handoff
  - demo-run summaries and raw outputs for acceptance walkthrough replay
- long-horizon validation artifacts:
  - scenario-based accumulated-memory evidence with profile-specific recall, lifecycle, task-switch, and conflict metrics
  - kept explicitly separate from benchmark hit-rate evidence
  - recent-run drift summaries that compare baseline vs latest persona/workload behavior

## Delivery Review Assets

The current sprint also ships receiver-facing delivery materials outside the API payloads:

- [handoff_example_flows.md](docs/handoff_example_flows.md)
- [agent_integration_examples.md](docs/agent_integration_examples.md)
- [acceptance_walkthrough.md](docs/acceptance_walkthrough.md)
- [final_delivery_manifest.md](docs/final_delivery_manifest.md)
- [emos_v1_1_hardening_roadmap.md](docs/emos_v1_1_hardening_roadmap.md)
- `.\scripts\run_delivery_demo.ps1`
- `.\scripts\run_storage_restore_drill.ps1`
- `.\scripts\run_long_horizon_validation.ps1`
- `.\scripts\run_long_horizon_summary.ps1`

## Long-Horizon Evidence Boundary

- `long_horizon_validation` is a scenario-validation surface, not a benchmark surface.
- Review `long_horizon_validation.metrics` for stability, task-switch, and conflict-detection behavior.
- Review `benchmark_summary` / `benchmark_comparison` for hit-rate and retrieval-backend benchmark evidence.
- Do not merge those two metric families into one score or one readiness number.
- Receiver-facing handoff and acceptance materials now reference the same boundary, so delivery review can keep long-horizon drift interpretation separate from benchmark interpretation.
- Week 7 closure posture: the validation runner, rolling multi-run summary, delivery-pack sections, and receiver-facing handoff wording now all point to the same long-horizon-vs-benchmark review boundary.

## Week 8 Agent-Surface Convergence

- `plan_memory_write` and `write_memory` now expose:
  - `payload.execution_policy`
  - `payload.policy_input`
  - `payload.execution_surface`
  - `payload.action_surface`
- `update / forget / restore / supersede / merge / history` continue to expose the same lifecycle thin surface, and now also keep `service_operation`, `next_action`, and `action_surface` aligned with write flows.
- `action_surface` is the preferred place to read a canonical:
  - `recommended_action`
  - `next_action`
  - handoff `mode`
  - `action_status`
- `set_memory_block`, `delete_memory_block`, `reflect_memory`, and report-facing system surfaces now also expose `action_surface`, so report review and contract execution can use the same thin action grammar.
- Final Week 8 sweep: `retrieval_backend`, `storage_backup`, `storage_restore_drill`, `storage_migration_preflight`, `long_horizon_validation`, `long_horizon_validation_summary`, `long_horizon_validation_multi_run_summary`, and `system_report` now also expose the same thin `policy_input / execution_policy / execution_surface / action_surface` contract, so upper layers do not need endpoint-specific parsing rules.
- Delivery-pack and handoff materials now mirror that same thin read order, so receiver-facing review can stay aligned with API-facing integration behavior.
- Week 9 package finalization is now closed: delivery-pack artifact maps now also point to a formal acceptance evidence bundle, a known-limitations note, v1.1 release notes, a packaging checklist, and a package closeout note so package-level review materials can stay versioned alongside the runtime/API surfaces.
- Phase B integration hardening is now also in place: `integration_flow` can distinguish a thin runtime observation window from recent validated delivery-grade integration evidence, and will expose when that evidence bridge is applied instead of forcing upper layers to guess why readiness is green.
- Phase C user-experience friction reduction is now also in place: `user_experience` reports distinguish `protective_confirmation_ratio` from `friction_confirmation_ratio`, and recall no longer treats every low-confidence result as confirmation-only when one supported fact, core-memory support, low freshness risk, and a clear conflict profile already justify a cautious grounded answer.
- Phase D training-signal completion is now also in place: offline review exports and training reports distinguish `feedback_labeled` from `protocol_labeled` samples, and `training_protocol.readiness` can now move to `ready` when protocol-rich service-operation traces already provide contract-grade training evidence.
- Final Phase C UX closeout is now also in place: `user_experience` reports may elevate top-level readiness to `comfortable` with `readiness_basis=recent_runtime_trend` when the latest recall behavior is repeatedly grounded, no-confirmation, and fallback-free, even if the raw runtime scope still contains an older confirmation event.
- Phase E stability is now also in place: `system_report`, `long_horizon_validation`, and `long_horizon_validation_multi_run_summary` now expose `phase_e_stability`, which is the preferred surface for reading consistency/hygiene queue pressure without overreacting to thin session-scoped release posture.
- SQLite restore-drill hardening is now also in place: when delivery artifacts are stored under a non-ASCII workspace path, restore drills stage SQLite backups through an ASCII-safe temp runtime path, but still record the drill artifact under `logs/delivery/restore_drills/` so `storage_report.recovery.latest_restore_drill` can discover the newest evidence normally.

## Training Signal Classification

- `GET /system/training-protocol` now exposes:
  - `labeled_sample_count`
  - `feedback_labeled_sample_count`
  - `protocol_labeled_sample_count`
  - `labeling_mode`
  - `training_signal_status`
- Interpretation:
  - `feedback_labeled_*` means explicit or passive feedback events are attached to the sample
  - `protocol_labeled_*` means the sample is still unlabeled by judgment, but it already carries reusable decision-protocol, guardrail, response-contract, or response-plan evidence
  - `labeling_mode=hybrid` means both evidence families are present in the current training window
- Preferred training review path:
  - read `labeling_mode`
  - read `response_contract_record_count`
  - read `response_plan_record_count`
  - read `execution_surface.policy_input` for direct upper-layer consumption

## User-Experience Friction Signals

- `GET /system/user-experience` now exposes:
  - `protective_confirmation_count`
  - `friction_confirmation_count`
  - `protective_confirmation_ratio`
  - `friction_confirmation_ratio`
  - `runtime_scope`
  - `readiness_basis`
  - `thin_scope_adjustment`
- Interpretation:
  - `protective_confirmation_*` tracks caution that is still justified by freshness/currentness risk
  - `friction_confirmation_*` tracks confirmation pressure that is more likely to feel interruptive to the upper-layer agent or end user
  - `runtime_scope` describes the observed local sample window directly, while top-level `readiness` may still apply thin-scope normalization or a recent-runtime-trend uplift when the latest grounded behavior is calmer than the broader sample window
- Preferred UX review path:
  - read `runtime_scope` for raw observed confirmation pressure
  - read `readiness_basis` to see whether thin-scope normalization was applied
  - when `readiness_basis=recent_runtime_trend`, treat `runtime_scope` as historical context and top-level `readiness` as the current operator/agent-facing posture
  - read `execution_surface.policy_input` for direct upper-layer consumption

## `GET /system/long-horizon-validation`

Returns the latest in-process scenario-validation run for accumulated-memory behavior.

Highlights:

- `workload_profile.profile_count`
- `workload_profiles[]` for persona-scoped detail
- `metrics.recall_stability_rate`
- `metrics.task_switch_stability_rate`
- `metrics.conflict_detection_rate`
- `counts.task_switch_count`
- `counts.conflict_check_count`
- `evidence_boundary`
- `artifacts.artifact_path`

This endpoint is intended for long-horizon stability review and should be read separately from benchmark-result surfaces.

## `GET /system/long-horizon-summary`

Returns a rolling multi-run summary over recent long-horizon validation artifacts.

Highlights:

- `run_count`
- `aggregate_metrics`
- `profile_summaries[]`
- `drift_flags`
- `review_posture`
- `benchmark_boundary`

This endpoint is intended for pilot-facing drift review across recent runs and should stay separate from benchmark-result interpretation.

## Storage Runtime Note

Key storage expectations:

- `resolved_backend` should normally be `sqlite`
- `primary_mode_status` should normally be `healthy_primary`
- `path` may point at an ASCII-safe local runtime path even when `memory_file` stays inside the workspace
- `memory_block_count` is now part of SQLite storage metadata, so block persistence is no longer JSON-only

Operational interpretation:

- `healthy_primary`: normal SQLite primary-path operation
- `degraded_fallback`: JSON fallback is active and operator follow-up is still required
- `blocked`: storage integrity or startup must be repaired before delivery use
- `recovery.latest_restore_drill.restored_backend` should normally be `sqlite` when `resolved_backend=sqlite`
- `recovery.latest_backup` may still point at a recent JSON artifact created by other delivery flows, so operators should review `recovery.latest_restore_drill` together with `backup_inventory` instead of assuming the newest file extension alone represents the best recovery evidence

## `POST /memory/process`

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "text": "我最近考试压力有点大。"
}
```

Response highlights:

- `emotion`
- `emotion_score`
- `memory_committed`
- `recalled_memory`
- `retrieval_candidates`
- `retrieval_candidates[].embedding_score`
- `retrieval_candidates[].rerank_bonus`
- `reflection`
- `semantic_profile`

## `POST /memory/write`

Agent-facing long-term memory write contract.

Response envelope:

- `contract_version`
- `operation`
- `payload`

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "text": "I always want to see Mayday live one day.",
  "task_type": "chat",
  "memory_scope": "auto",
  "force_write": false,
  "source": "agent",
  "task_goal": "build a stable user preference profile",
  "context_summary": "The upper-layer agent is collecting durable user likes and dislikes.",
  "working_memory": ["recent discussion about music preferences"]
}
```

Returns:

- whether memory was written
- write policy decision and reasons
- memory-resolution decision (`new_memory`, `deduplicate`, or `suggest_update`)
- `decision_protocol` with a stable agent-facing governance shape
- `consistency_plan` with prioritized recommended operations
- `execution_guardrails` with blocked operations, confirmation gates, and auto-allowed operations
- resulting memory id when written
- extracted tags and emotion
- agent context fields echoed back for traceability
- next action hint for the upper-layer agent

## `POST /memory/write-plan`

Dry-run planning contract for upper-layer agents that want a write/update/deduplicate recommendation before mutating long-term memory.

Returns:

- `write_policy`
- `memory_resolution`
- `content_classification`
- `block_plan`
- `suggested_action`
- `decision_protocol`
- `consistency_plan`
- `execution_guardrails`
- `active_conflict_scan`
- resolution candidates
- extracted tags and emotion

## `POST /memory/recall`

Agent-facing memory recall contract.

Response envelope:

- `contract_version`
- `operation`
- `payload`

Request body:

```json
{
  "user_id": "demo-user",
  "query_text": "What live band do I really want to see?",
  "session_id": "demo-session",
  "top_k": 5,
  "include_profile": true,
  "task_goal": "answer from long-term memory",
  "context_summary": "Need a concise grounded answer for the personal agent.",
  "working_memory": ["respond concisely", "cite evidence"],
  "response_mode": "agent_bundle"
}
```

`response_mode` notes:

- `agent_bundle` keeps the full recall payload and marks `preferred_surface=agent_bundle`
- `execution_surface` keeps the full recall payload but marks `preferred_surface=execution_surface`, signaling that the caller should primarily consume the thin execution surface

Returns:

- recalled memory
- retrieval candidates
- compact evidence bundle
- always-visible `core_memory_blocks`
- confidence
- retrieval pipeline profile
- optional semantic profile
- top-level `decision_protocol`
- top-level `consistency_plan`
- top-level `execution_policy`
- top-level `policy_input`
- top-level `execution_surface`
- top-level `response_contract`
- top-level `response_guardrails`
- top-level `user_experience_guidance`
- top-level `agent_response_plan`
- `memory_context` bundle with:
  - task goal
  - context summary
  - working memory
  - confidence band
  - facts
  - constraints
  - citeable memory ids
  - writeback suggestion
  - nested `decision_protocol` for direct upper-layer-agent execution
  - nested `consistency_plan` for conflict-safe next-step selection
  - nested `execution_policy`
  - nested `policy_input`
  - nested `execution_surface`
  - nested `response_contract`
  - nested `response_guardrails`
  - nested `user_experience_guidance`
  - nested `agent_response_plan`
- fallback memories and fallback reason when strict retrieval returns empty
- next action hint for the upper-layer agent

Low-confidence confirmation note:

- low confidence no longer automatically implies `ask_user_confirmation`
- when recall has one supported fact, supporting core blocks, low freshness risk, no fallback, and a clear conflict profile, EMOS may return `answer_cautiously` with `can_answer_now=true` and `should_confirm=false`
- upper layers should still use `response_contract`, `response_guardrails`, and `execution_surface` as the canonical consumption path instead of inferring this behavior from confidence alone

## `POST /memory/reflect`

Agent-facing reflection contract.

Response envelope:

- `contract_version`
- `operation`
- `payload`

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "persist": false
}
```

Returns:

- reflection summary
- whether it was persisted
- current memory count

## `POST /memory/update`

Agent-facing memory update contract.

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "memory_id": "existing-memory-id",
  "text": "I always want to see Mayday and Coldplay live one day.",
  "source": "agent",
  "task_goal": "refresh a durable preference memory",
  "context_summary": "The user clarified another long-term concert preference.",
  "working_memory": ["merge with prior preference memory"]
}
```

Returns:

- whether the memory was updated
- refreshed memory payload
- updated tags and emotion
- `decision_protocol`
- `consistency_plan`
- next action hint

## `POST /memory/forget`

Agent-facing memory soft-forget contract.

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "memory_id": "existing-memory-id",
  "reason": "outdated preference",
  "source": "agent"
}
```

Returns:

- whether the memory was forgotten
- soft-forgotten memory payload
- `decision_protocol`
- `consistency_plan`
- forget reason and next action hint

## `POST /memory/block`

Create or update a persisted core memory block.

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "label": "persona_anchor",
  "value": "The user cares about emotionally meaningful live music experiences.",
  "description": "Pinned block for upper-layer personalization.",
  "read_only": false,
  "source": "agent"
}
```

## `POST /memory/block/delete`

Delete a persisted core memory block by label.

## `GET /memory/blocks`

Query params:

- `user_id` required

Returns:

- persisted core memory blocks for the requested user

## `GET /memory/history`

Query params:

- `user_id` required
- `memory_id` required
- `session_id` optional

Returns:

- structured revision history for the specified memory entry
- action records such as `update` and `forget`
- audit-friendly snapshots of prior text, emotion, score, and tags
- `decision_protocol` describing whether the upper-layer agent should inspect, restore, merge, or supersede next
- `consistency_plan` with prioritized lifecycle follow-up operations

Lifecycle contracts also now include:

- `POST /memory/restore`
- `POST /memory/supersede`
- `POST /memory/merge`

Recall-time `memory_context` now also exposes:

- `recommended_usage`
- `unsafe_to_assume`
- `conflict_detected`
- `conflict_profile`
- `memory_age_signal`
- `stability_signal`
- `requires_user_confirmation`
- nested `decision_protocol`

Shared `decision_protocol` fields across agent-facing contracts:

- `protocol_version`
- `operation`
- `decision_type`
- `recommended_action`
- `reason`
- `safe_to_execute`
- `requires_confirmation`
- `target_memory_ids`
- `target_block_labels`
- `conflict_summary`
- `suggested_followups`
- `risk_level`
- `consistency_status`
- `recommended_operations`

Shared `consistency_plan` fields:

- `plan_version`
- `status`
- `risk_level`
- `issues`
- `issue_types`
- `issue_summary`
- `governance_mode`
- `action_buckets`
- `recommended_operations[]`

Week 4 tightening notes:

- low-risk `suggest_update` write plans may now surface `suggested_action=auto_update_existing_memory`
- `write_memory` can now resolve those low-risk update cases by updating the existing target memory directly instead of always appending a new memory row
- stale-only recall paths now bias toward `confirm_required` without automatically adding `get_memory_history` as a manual-review step
- lifecycle contracts and `GET /system/consistency-audit` now also expose `consistency_maintenance`, a shared thin surface for `governance_mode`, `action_buckets`, `next_bucket`, and maintenance summary wording
- lifecycle contracts now also expose a shared thin `execution_policy / policy_input / execution_surface` layer, aligned with recall/readiness/storage consumption patterns
- `GET /system/consistency-audit` now also exposes `maintenance_jobs`, `operator_action_buckets`, and `agent_action_buckets`
- `GET /system/release-readiness` and `GET /system/agent-readiness-summary` now quote those consistency-maintenance surfaces directly and also expose consistency-driven `lifecycle_execution_paths` plus `recommended_lifecycle_execution`
- `GET /system/consistency-audit`, `GET /system/release-readiness`, and `GET /system/agent-readiness-summary` now also expose shared `ops_metric_surface` and `audit_signal_surface` objects so operator and agent consumers can read the same maintenance telemetry
- those same report surfaces now also expose `error_taxonomy` and `operator_review_order`, so operators can classify failures and follow a stable review sequence before acting
- handoff and acceptance wording for those shared observability surfaces is now centralized in [operator_observability_guide.md](docs/operator_observability_guide.md)
- delivery-pack Markdown now also renders those shared observability anchors directly, including `operator_review_order`, `error_taxonomy`, shared ops metrics, and the recommended lifecycle execution path
- the delivery demo path now also points reviewers to those delivery-pack observability sections and the shared operator observability guide
- the delivery-pack artifact map now also includes `final_delivery_manifest`, and the demo summary now uses that manifest as the canonical wording companion for delivery acceptance review
- `docs/handoff_example_flows.md` now mirrors that same review order for receiver-facing storage and demo walkthroughs
- `GET /system/long-horizon-validation` now runs a first-pass accumulated-memory validation workload and returns a delivery artifact plus stability metrics

Each `recommended_operations[]` item includes:

- `operation`
- `reason`
- `priority`
- `scope`
- `requires_confirmation`
- `arguments`

`active_conflict_scan` fields on write planning contracts:

- `has_conflict`
- `ambiguity_detected`
- `conflicts[]`
- `candidate_memory_ids`

`response_contract` fields on recall contracts:

- `answer_mode`
- `ready_for_agent_answer`
- `citation_required`
- `cite_memory_ids`
- `grounding_sources`
- `required_steps`
- `blocked_behaviors`
- `unsafe_to_assume`
- `conflict_profile`
- `freshness_guard`

`policy_input` fields on recall contracts:

- `can_answer_now`
- `should_confirm`
- `citation_required`
- `resolution_flow`
- `answer_decision`
- `confirmation_decision`
- `response_mode`
- `primary_operation`

`execution_policy` fields on recall contracts:

- `policy_version`
- `answer.decision`
- `confirmation.decision`
- `evidence.citation_required`
- `response.response_language`
- `resolution.flow`
- `resolution.primary_operation`
- nested `policy_input`

`policy_input` fields on lifecycle contracts:

- `can_execute_now`
- `should_confirm`
- `resolution_flow`
- `lifecycle_operation`
- `decision_type`
- `recommended_action`
- `primary_operation`
- `next_bucket`

`execution_policy` fields on lifecycle contracts:

- `policy_version`
- `execution.decision`
- `confirmation.decision`
- `review.bucket`
- `resolution.flow`
- `resolution.recommended_action`
- nested `policy_input`

`user_experience_guidance` fields on recall contracts:

- `interaction_style`
- `trust_level`
- `confirmation_style`
- `max_clarifying_questions`
- `should_mention_memory_source`
- `should_avoid_internal_details`
- `feedback_strategy`
- `user_visible_goal`
- `recommended_phrase_style`
- `freshness_hint`

`agent_response_plan` fields on recall contracts:

- `mode`
- `response_language`
- `preferred_response_length`
- `answer_opening`
- `answer_skeleton`
- `confirmation_prompt`
- `evidence_snippets`
- `should_reference_memory`
- `should_ask_followup`
- `freshness_strategy`

`agent_handoff` fields on recall contracts:

- `mode`
- `response_language`
- `can_answer_now`
- `should_confirm`
- `response_preview`
- `confirmation_prompt`
- `memory_ids`
- `block_labels`
- `freshness_risk`
- `trust_level`
- `primary_operation`
- `one_line_rationale`

`agent_handoff` also appears on write-side contracts such as:

- `plan_memory_write`
- `write_memory`
- `update_memory`

Write-side handoff fields:

- `mode`
- `can_execute_now`
- `should_confirm`
- `target_memory_ids`
- `target_block_labels`
- `recommended_operation`
- `memory_resolution_action`
- `block_update_label`
- `guardrail_mode`
- `risk_level`
- `one_line_rationale`

`agent_handoff` also appears on lifecycle contracts such as:

- `forget_memory`
- `get_memory_history`
- `restore_memory`
- `supersede_memory`
- `merge_memories`

Lifecycle handoff fields:

- `mode`
- `can_execute_now`
- `should_confirm`
- `target_memory_ids`
- `recommended_operation`
- `state_status`
- `risk_level`
- `one_line_rationale`

Recall contract note:

- top-level `decision_protocol.recommended_action` is aligned with `memory_context.decision_protocol.recommended_action`
- `agent_response_plan` is language-aware for user-facing reply scaffolding
- `agent_handoff` is a thin execution-oriented summary intended for direct upper-layer agent consumption
- `execution_surface` is the preferred thin upper-layer consumption object when the caller wants policy + handoff + response constraints in one place

System-facing reports also now include:

- `GET /system/integration-flow`
- `GET /system/training-protocol`
- `GET /system/user-experience`
- `GET /system/consistency-audit`
- `GET /system/memory-hygiene`
- `GET /system/release-readiness`
- `GET /system/readiness-baseline`
- `GET /system/agent-readiness-summary`

`agent_readiness_summary` now also exposes:

- `execution_policy.policy_version`
- `execution_policy.answer.decision`
- `execution_policy.write.decision`
- `execution_policy.confirmation.decision`
- `execution_policy.resolution.flow`
- `policy_input.can_answer_now`
- `policy_input.can_write_now`
- `policy_input.should_confirm`
- `policy_input.resolution_flow`
- `retrieval_runtime_advice`
- `execution_surface`

`GET /system/readiness-baseline` now also exposes:

- `baseline_summary`
- `release_posture`
- `source_map`
- `active_sources`
- `phase_targets`
- `repair_sequence`
- `evidence_snapshot`
- `execution_surface`

`GET /system/retrieval-backends` now also exposes `runtime_advice` with:

- `switch_backend.recommended`
- `switch_backend.target_backend`
- `candidate_pool.status`
- `candidate_pool.effective_size`
- `candidate_pool.recommended_min`
- `response_policy.mode`
- `response_policy.strong_answer_ok`
- `recommended_operations[]`

## `GET /memory/profile`

Query params:

- `user_id` required
- `limit` optional, default `20`

Returns:

- semantic profile
- dream/reflection summary
- recent memories
- memory count

## `GET /memory/memories`

Query params:

- `user_id` required
- `limit` optional, default `20`

Returns:

- `user_id`
- `memories`

## `GET /memory/report`

Query params:

- `user_id` required
- `limit` optional, default `10`

Returns:

- retrieval backend and storage backend
- top emotions and top tags
- recent memories
- semantic profile and dream summary

## `GET /memory/export`

Query params:

- `user_id` required
- `limit` optional, default `20`

Returns a delivery bundle that includes:

- snapshot
- user report
- backend metadata
- export timestamp

## `POST /memory/feedback`

Request body:

```json
{
  "user_id": "demo-user",
  "session_id": "demo-session",
  "memory_id": "memory-id-from-retrieval-candidates",
  "feedback_type": "correct",
  "query_text": "刚才那种考试压力我最近一直缓不过来。",
  "signal_weight": 1.0
}
```

`feedback_type` supports:

- `correct`
- `incorrect`
- `irrelevant`

Note:

- Explicit feedback can be sent through this endpoint.
- The runtime can also derive bounded passive feedback from natural follow-up turns such as corrections, affirmations, and repeated questions.
- The passive-feedback heuristics currently cover both Chinese and English follow-up patterns.

Returns:

- feedback event id and timestamp
- feedback type
- scoring delta and signal weight
- bound memory id
- query signature and backend context when available

## `GET /memory/feedback`

Query params:

- `user_id` optional
- `limit` optional, default `20`

Returns:

- feedback summary
- user-level preference profile
- profile insights including top memories/tags/attributes/backends
- recent feedback events

## `GET /system/report`

Returns runtime delivery information:

- active retrieval backend
- storage backend
- runtime file paths
- latest benchmark summary
- latest backend-comparison summary

## `GET /system/retrieval-backends`

Returns:

- active retrieval backend
- available retrieval backends
- active backend descriptor and tunable parameters
- persisted settings path
- current retrieval settings
- `pipeline_profile.control_plane` with explicit `recall / fusion / rerank`
- explainability signals
- control-plane readiness, task fit, agent recommendations, and anti-patterns
- validation notes and recommended candidate pool
- recent switch history

## `POST /system/retrieval-backend`

Request body:

```json
{
  "backend_name": "embedding_rerank",
  "embedding_dimensions": 96,
  "embedding_candidate_pool": 16,
  "change_source": "api"
}
```

Returns:

- active retrieval backend
- available retrieval backends
- current persisted settings
- backend descriptor

## Offline Review Export Notes

The offline review dataset now includes candidate-level training rows per shown retrieval candidate:

- `memory_id`
- `rank`
- `backend`
- `score`
- `label`: `preferred`, `rejected`, or `unlabeled`
- `exposed`

This makes the export closer to a direct reranker-training dataset rather than only a manual review log.

Each exported sample now also retains:

- `record_type`
- `operation`
- `task_goal`
- `context_summary`
- `working_memory`

Each candidate training row now also includes a decomposed feature bundle:

- `lexical_score`
- `semantic_score`
- `fuzzy_score`
- `embedding_score`
- `emotion_bonus`
- `recency_bonus`
- `profile_bonus`
- `abstraction_bonus`
- `attribute_bonus`
- `summary_bonus`
- `graph_bonus`
- `rerank_bonus`
- `feedback_bonus`
- hit-count features for keywords, concepts, relations, and attributes
- effective embedding dimensions / candidate pool
- recent backend-switch history

## `GET /system/storage`

Returns resolved storage information:

- requested backend
- resolved backend
- preferred primary backend
- `primary_mode_status` (`healthy_primary`, `degraded_fallback`, or `blocked`)
- `primary_storage`
- `operator_decision_path`
- `operator_acceptance_note`
- `remediation_checklist`
- storage path
- file size
- fallback reason when `auto` falls back to JSON
- SQLite runtime metadata when SQLite is active
- persistence consistency
- migration strategy
- schema status and migration readiness
- migration policy, preflight status, and rollback readiness
- latest migration attempt and rollback-availability evidence
- migration acceptance decision rule for execute-now vs preflight-only vs refresh-rollback-evidence
- recovery path
- latest backup metadata and recovery confidence
- latest restore-drill result with candidate-selection evidence
- explicit recovery-gate fields: `last_restore_drill_at`, `last_restore_drill_status`, `restore_confidence`
- restore-drill freshness contract and rerun rule
- backup inventory
- operator checklist
- deployment guidance and restore steps
- `policy_input`
- `execution_policy`
- `execution_surface`
- observability surfaces
- readiness, blockers/warnings, recommended operations
- compact `agent_handoff`

## `GET /system/agent-readiness-summary`

Query params:

- `user_id` optional
- `session_id` optional
- `limit` optional, default `200`

Returns:

- cross-surface readiness summary for upper-layer agents
- surface statuses for storage / integration / training / UX / hygiene / consistency / release
- blockers, warnings, and `next_focus`
- consistency-driven `lifecycle_execution_paths` plus `recommended_lifecycle_execution`
- shared `ops_metric_surface` and `audit_signal_surface`
- shared `error_taxonomy` and `operator_review_order`
- compact `agent_handoff`

## `GET /system/readiness-baseline`

Query params:

- `user_id` optional
- `session_id` optional
- `limit` optional, default `200`

Returns:

- a `readiness-baseline.v1` report for Phase A hardening
- `baseline_summary` with current release/agent posture plus blocker/warning counts
- `release_posture` with delivery-ready vs agent-demo-loop-ready status
- `source_map` covering each readiness blocker/warning source, its trigger condition, and observed values
- `active_sources` in prioritized repair order
- `phase_targets` mapping active issues to the next hardening phases
- `repair_sequence` with recommended action and resolution flow per active source
- `evidence_snapshot` with the current storage / integration / training / UX / hygiene / consistency / agent-execution metrics
- compact `agent_handoff`, `policy_input`, `execution_policy`, `execution_surface`, and `action_surface`

## CLI `readiness-baseline-report`

Arguments:

- `--user-id` optional, default `local-user`
- `--baseline-session-id` optional
- `--limit` optional, default `200`

Returns the same `readiness-baseline.v1` source map and repair-order surface that the API exposes through `GET /system/readiness-baseline`.

## `GET /system/long-horizon-validation`

Query params:

- `user_id` optional, default `long-horizon-user`
- `session_id` optional, default `long-horizon-session`
- `limit` optional, default `200`

Returns:

- a first-pass long-horizon validation artifact for accumulated-memory workload review
- `metrics` for:
  - `recall_stability_rate`
  - `contradiction_rate`
  - `stale_fact_exposure_rate`
  - `lifecycle_resolution_rate`
  - `pollution_signal_rate`
- `counts` and `recall_checks`
- `lifecycle_outcomes`
- `supporting_reports` derived from hygiene / consistency / readiness surfaces
- an artifact path under `logs/delivery/long_horizon/*`

## `GET /system/integration-flow`

Additional integration-flow details now include:

- `scenario_checks`
- `scenario_status`
- `incomplete_scenarios`
- `consistency_loop` coverage for history + consistency logging + lifecycle resolution
- `runtime_scope` so a caller can see the raw local-window coverage before any evidence bridge is applied
- `integration_evidence` so a caller can inspect the latest validated integration artifact that is eligible for bridging
- `evidence_bridge` so a caller can see whether top-level readiness is based on recent validated integration evidence rather than only the current thin runtime scope
- `execution_surface`
- `recommended_call_flows`
- `anti_patterns`

These surfaces are designed to validate whether real personal-agent loops are actually present in logged service operations, instead of only counting raw endpoints.

Interpretation order:

- Read `runtime_scope` first for the narrow local sample window.
- Read top-level `readiness`, `required_capabilities`, and `scenario_status` second for the delivery-facing posture.
- Read `evidence_bridge.readiness_basis` to see whether the delivery-facing posture comes from direct runtime coverage or `validated_integration_evidence`.

## `GET /system/consistency-audit`

Query params:

- `user_id` optional
- `limit` optional, default `50`

Returns:

- consistency readiness (`clean`, `review_needed`, `cleanup_needed`)
- `consistency_type_counts` for revised / stale / disputed / lifecycle surfaces
- `governance_mode` and `action_buckets` for auto-safe vs confirmation vs manual-review posture
- revised active fact candidates
- old fact candidates, including inactive superseded/merged versions and aged revised facts
- disputed watchlist candidates that should bias upper-layer agents toward confirmation
- prioritized `recommended_operations` such as `inspect_memory_history`, `prefer_confirmation_for_revised_facts`, and `audit_old_fact_versions`

## `GET /system/memory-hygiene`

Query params:

- `user_id` optional
- `limit` optional, default `50`

Returns:

- memory hygiene readiness (`clean`, `review_needed`, `cleanup_needed`)
- stale active memories
- heavily revised active memories
- inactive memories (`forgotten`, `superseded`, `merged`)
- prioritized `recommended_operations` for maintenance

## `GET /system/storage-backup`

Creates a storage backup artifact and returns:

- backup path
- backup timestamp
- resolved backend
- backup mode (`native_backup` or `json_fallback`)
- backup format
- `sha256`
- verification metadata
- restore steps
- backup `agent_handoff`

## CLI `storage-migration-preflight`

Runs a storage migration preflight and returns:

- `migration.policy_version`
- schema version and target schema version
- supported upgrade paths
- `migration.preflight`
- `migration.rollback`
- latest migration result status for artifact-based tracking
- generated preflight artifact path
- migration-preflight `agent_handoff`

The delivery-facing storage report and delivery pack also surface:

- `migration.latest_attempt`
- `migration.rollback.rollback_ready`
- rollback evidence derived from the latest backup and restore-drill posture
- `migration.migration_acceptance`

## CLI `storage-restore-drill`

Runs a restore drill against the latest healthy backup candidate and returns:

- drill status
- source backup path and format
- restored path
- restored backend
- count-match checks
- attempted candidate list and selection strategy
- restore-drill `agent_handoff`

The delivery-facing storage report and delivery pack also surface:

- `last_restore_drill_at`
- `last_restore_drill_status`
- `restore_confidence`
- `restore_drill_freshness`

Current acceptance wording:

- existing restore-drill evidence is acceptable when the latest drill is `passed` and no older than 24 hours
- rerun the restore drill when evidence is missing, failed, or older than 24 hours

## `GET /system/delivery-pack`

Generates a delivery pack and returns:

- current system report
- current storage report
- generated artifact paths
- storage runbook path
- timestamped delivery-pack JSON/Markdown outputs

The delivery pack is intended to be the formal handoff artifact for this sprint, not just a debug dump. The receiver should be able to review:

- delivery identity and active runtime configuration
- current storage readiness and recovery path
- current storage acceptance decision (`proceed`, `proceed_with_followup`, or `block`)
- generated artifact locations for review, storage recovery, and benchmark evidence

## `GET /system/offline-review-export`

Query params:

- `user_id` optional
- `limit` optional, default `500`

Returns:

- export timestamp
- output dataset path
- exported sample count
- source interaction log path
- manifest with labeled / unlabeled sample counts
- language distribution and judgment-status distribution inside the manifest
