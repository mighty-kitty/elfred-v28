# Final Delivery Manifest

## Package Identity

- Package: `EMOS v1`
- Position: independent memory engine / memory service
- Deployment mode: local/private-deployment first
- Non-goal for this sprint: public-cloud multi-tenant SaaS

## Primary Runtime Path

1. `.\scripts\run_api.ps1`
2. `.\scripts\run_smoke.ps1`
3. `.\scripts\run_integration_flows.ps1`
4. `.\scripts\run_long_horizon_validation.ps1`
5. `.\scripts\run_long_horizon_summary.ps1`
6. `.\scripts\run_delivery_pack.ps1`
7. `.\scripts\run_delivery_demo.ps1`

## Core Handoff Materials

- [README.md](README.md)
- [api_reference.md](docs/api_reference.md)
- [handoff_manual.md](docs/handoff_manual.md)
- [handoff_example_flows.md](docs/handoff_example_flows.md)
- [acceptance_checklist.md](docs/acceptance_checklist.md)
- [acceptance_walkthrough.md](docs/acceptance_walkthrough.md)
- [operator_observability_guide.md](docs/operator_observability_guide.md)
- [storage_delivery_runbook.md](docs/storage_delivery_runbook.md)
- [storage_migration_runbook.md](docs/storage_migration_runbook.md)
- [acceptance_evidence_bundle.md](docs/acceptance_evidence_bundle.md)
- [emos_v1_1_known_limitations.md](docs/emos_v1_1_known_limitations.md)
- [emos_v1_1_release_notes.md](docs/emos_v1_1_release_notes.md)
- [emos_v1_1_packaging_checklist.md](docs/emos_v1_1_packaging_checklist.md)
- [emos_v1_1_package_closeout.md](docs/emos_v1_1_package_closeout.md)

## Delivery Artifacts

- delivery-pack JSON/Markdown under `logs/delivery/*`
- storage backups under `logs/delivery/storage_backups/*`
- migration preflights under `logs/delivery/migrations/*`
- long-horizon validation artifacts under `logs/delivery/long_horizon/*`
- demo-run outputs under `logs/delivery/demo_runs/*`
- interaction logs under `logs/memory_interactions.jsonl`
- offline review exports under `logs/offline_eval/*`

The delivery-pack Markdown should now directly surface the storage acceptance decision so a receiver can see whether storage is in:

- `proceed`
- `proceed_with_followup`
- `block`

The storage report should also expose a standard acceptance note and remediation checklist for degraded fallback review.

The delivery-pack Markdown should also surface the recovery gate directly so a receiver can review:

- `last_restore_drill_at`
- `last_restore_drill_status`
- `restore_confidence`
- `restore_drill_freshness`

The delivery-pack Markdown should now also surface the migration gate directly so a receiver can review:

- `migration.preflight.status`
- `migration.latest_attempt`
- `migration.rollback.rollback_ready`
- `migration.migration_acceptance`

Shared operator observability review should now be anchored on:

- `release_readiness.error_taxonomy`
- `release_readiness.operator_review_order`
- `agent_readiness_summary.ops_metric_surface`
- `agent_readiness_summary.audit_signal_surface`
- `agent_readiness_summary.recommended_lifecycle_execution`

The delivery-pack Markdown should now also surface those same review anchors directly so the receiver can inspect observability posture without opening the nested JSON first.

The delivery-pack Markdown should now also state the preferred thin read order explicitly:

1. `execution_surface.policy_input`
2. `execution_surface.action_surface`
3. `execution_surface.agent_handoff`
4. top-level `action_surface` when a full execution surface is not present

Long-horizon validation should now be reviewed through two distinct surfaces:

- `long_horizon_validation_summary` for the latest multi-profile workload run
- `long_horizon_multi_run_summary` for recent-run drift across personas/workloads

That evidence must stay separate from benchmark evidence:

- long-horizon validation is for pilot-facing stability and drift review
- benchmark outputs remain for hit-rate and retrieval-quality review

The delivery demo summary should now point the receiver through the same order:

1. delivery-pack artifact paths
2. delivery-pack shared observability sections
3. final delivery manifest wording
4. integration evidence
5. operator observability guide

Current restore-drill acceptance wording:

- accept current recovery evidence when the latest restore drill is `passed` and no older than 24 hours
- rerun the restore drill when evidence is missing, failed, or older than 24 hours

Current migration/rollback acceptance wording:

- `execute_now`: preflight is ready, latest migration attempt is ready, and rollback evidence is fresh
- `preflight_only`: preflight is ready but the receiver should stop short of execution
- `refresh_rollback_evidence`: refresh backup and/or restore-drill evidence before any upgrade
- `block`: do not execute until preflight blockers are cleared

## Validation Snapshot

- `.\scripts\run_tests.ps1` -> `60 passed`
- `.\scripts\run_smoke.ps1` -> success
- `.\scripts\run_integration_flows.ps1` -> success
- `.\scripts\run_long_horizon_validation.ps1` -> success
- `.\scripts\run_long_horizon_summary.ps1` -> success
- `.\scripts\run_delivery_pack.ps1` -> success
- `.\scripts\run_delivery_demo.ps1` -> success

## Current Delivery Posture

- integration evidence: ready
- training protocol: ready
- release readiness: limited pilot
- storage recovery path: present
- long-horizon validation path: present
- long-horizon multi-run drift review: present
- restore drill gate: surfaced in delivery pack and acceptance materials
- primary runtime friction still to watch:
  - JSON fallback may remain active when SQLite is blocked in the environment
  - consistency review remains a guarded follow-up path rather than a fully auto-cleared path

## Package Finalization Notes

- acceptance evidence bundle: [acceptance_evidence_bundle.md](docs/acceptance_evidence_bundle.md)
- known limitations: [emos_v1_1_known_limitations.md](docs/emos_v1_1_known_limitations.md)
- release notes: [emos_v1_1_release_notes.md](docs/emos_v1_1_release_notes.md)
- packaging checklist: [emos_v1_1_packaging_checklist.md](docs/emos_v1_1_packaging_checklist.md)
- package closeout: [emos_v1_1_package_closeout.md](docs/emos_v1_1_package_closeout.md)
- these bundle-level materials should be treated as formal package-level companions to the delivery-pack JSON/Markdown, not optional side notes
- the packaging checklist and package closeout should be treated as the final bundle-composition and closeout companions

## Storage Acceptance Rule

- `primary_storage_mode=healthy_primary`: accept normally if the rest of the delivery gates are green
- `primary_storage_mode=degraded_fallback`: accept only with explicit follow-up for primary-path restoration
- `primary_storage_mode=blocked`: do not accept until the storage path is unblocked

## Retained Assets

The following asset families remain intentionally present and must not be treated as cleanup targets:

- benchmark runners
- benchmark datasets
- official LoCoMo fixtures and related evaluation assets
- paper/arXiv-facing replication materials

## Receiver Decision Rule

- Accept the package when the runtime path, delivery artifacts, storage recovery path, migration/rollback review path, and demo walkthrough are all reproducible.
- Accept with follow-up when SQLite promotion is still environment-dependent but the fallback/recovery path is healthy.
- Escalate only when runtime, recovery, or contract surfaces cannot be reproduced from the packaged materials.
