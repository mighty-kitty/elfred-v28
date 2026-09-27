# Handoff Example Flows

## Purpose

This document gives a receiver-facing set of stable example flows for `EMOS v1` handoff.

EMOS is handed off as an independent memory engine / memory service, not as the full personal agent.

## Flow 1: Service Bring-Up And Health Check

1. Start the service with `.\scripts\run_api.ps1`.
2. Run `.\scripts\run_smoke.ps1`.
3. Confirm that the runtime can:
   - process user turns
   - write memory
   - recall memory
   - generate reflection

Receiver expectation:

- the service starts without custom patching
- the smoke path completes successfully
- the runtime path matches the documented local/private deployment posture

## Flow 2: Upper-Layer Agent Integration Review

1. Generate realistic service evidence with `.\scripts\run_integration_flows.ps1`.
2. Review the integration output for:
   - `chat_loop`
   - `task_loop`
   - `lifecycle_loop`
   - `core_memory_loop`
   - `consistency_loop`
3. For thin upper-layer consumption, start with:
   - `payload.execution_surface.policy_input`
   - `payload.execution_surface.action_surface`
   - `payload.execution_surface.execution_policy`
   - `payload.execution_surface.agent_handoff`
   - `payload.execution_surface.response_contract`
   - `payload.execution_surface.response_guardrails`
4. For block / reflection flows and report-facing review, read the same shape:
   - top-level `action_surface`
   - then `agent_handoff`
   - then any deeper report-specific surfaces

Receiver expectation:

- EMOS exposes stable memory-service contracts
- the upper-layer agent does not need to reconstruct memory policy from raw fields
- the upper-layer agent can read `recommended_action / next_action / mode` through one shared `action_surface`
- integration evidence shows actual end-to-end usage instead of only endpoint presence

## Flow 3: Operator Storage And Recovery Review

1. Generate a delivery-grade pack with `.\scripts\run_delivery_pack.ps1`.
2. Start the review in this order:
   - delivery-pack shared observability sections
   - `operator_review_order`
   - `error_taxonomy`
   - shared ops metrics
   - `recommended_lifecycle_execution`
3. Then review:
   - report-level `action_surface`
   - report-level `agent_handoff`
   - `delivery_pack.storage_report`
   - `storage_report.execution_surface`
   - `storage_report.operator_checklist`
   - `storage_report.deployment_guidance`
   - `storage_backup.verification`
4. Cross-check:
   - [operator_observability_guide.md](docs/operator_observability_guide.md)
   - [storage_delivery_runbook.md](docs/storage_delivery_runbook.md)

Receiver expectation:

- storage is described as an operator surface, not just backend metadata
- the receiver sees observability posture before diving into raw storage fields
- the receiver sees a shared action surface before diving into raw storage fields
- backup output includes verification and restore guidance
- the receiver can identify whether follow-up is needed for SQLite promotion or migration planning

## Flow 4: Delivery Package Review

1. Run `.\scripts\run_delivery_demo.ps1` for the packaged demo path.
2. Open the generated demo summary under `logs/delivery/demo_runs/*/demo_summary.md`.
3. Follow the demo summary review path in this order:
   - delivery-pack artifact paths
   - delivery-pack shared observability sections
   - [final_delivery_manifest.md](docs/final_delivery_manifest.md)
   - integration evidence
   - [operator_observability_guide.md](docs/operator_observability_guide.md)
4. When the receiver opens any embedded contract/report, prefer:
   - `execution_surface.policy_input`
   - `execution_surface.action_surface`
   - `agent_handoff`
5. This same read order now also applies to retrieval backend review, storage backup / restore-drill / migration-preflight artifacts, long-horizon summaries, and the top-level system report.
6. Review the linked raw outputs for:
   - smoke evidence
   - integration evidence
   - delivery-pack evidence

Receiver expectation:

- a single script can reproduce the demo sequence without inventing a new runtime path
- the handoff package points the receiver to the right artifacts and the same observability-first review order used by the delivery pack and final manifest

## Flow 5: Long-Horizon Validation And Drift Review

1. Run `.\scripts\run_long_horizon_validation.ps1`.
2. Run `.\scripts\run_long_horizon_summary.ps1`.
3. Review:
   - `system_report.long_horizon_validation_summary`
   - `system_report.long_horizon_multi_run_summary`
   - `long_horizon_validation.evidence_boundary`
   - persona-scoped `profile_summaries`
4. Keep benchmark review separate:
   - long-horizon validation is for pilot-facing stability and drift review
   - benchmark outputs remain for hit-rate and retrieval-quality review

Receiver expectation:

- the receiver can inspect single-run and multi-run long-horizon evidence without reading raw artifacts by hand
- the receiver can compare baseline vs latest persona behavior through drift deltas
- the receiver does not merge long-horizon stability evidence into benchmark scoring

## Flow 6: Migration Prep And Rollback Prep Review

1. Run `.\scripts\run_storage_migration_preflight.ps1`.
2. Review:
   - `storage_report.migration.preflight`
   - `storage_report.migration.latest_attempt`
   - `storage_report.migration.rollback`
   - `storage_report.migration.migration_acceptance`
3. Cross-check [storage_migration_runbook.md](docs/storage_migration_runbook.md).

Receiver expectation:

- the receiver can tell whether upgrade execution is allowed now or only preflight-ready
- the receiver can identify when rollback evidence must be refreshed first
- the receiver has a clear order for upgrade-prep and rollback-prep checks before touching storage

## Escalation Guidance

- Accept the handoff when the runtime path, integration evidence, long-horizon validation path, storage recovery path, migration/rollback review path, and delivery artifacts are all present and readable.
- Escalate when the target environment requires SQLite as the preferred primary store but EMOS remains in JSON fallback mode.
- Do not escalate merely because benchmark / official LoCoMo / paper-facing assets remain in the repository; those assets are intentionally retained.
