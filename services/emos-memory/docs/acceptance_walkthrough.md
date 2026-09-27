# Acceptance Walkthrough

## Goal

This walkthrough is the recommended reviewer path for accepting `EMOS v1` as a local/private-deployment-first memory engine / memory service.

## Step 1: Confirm Delivery Identity

Review:

- [README.md](README.md)
- [api_reference.md](docs/api_reference.md)
- [handoff_manual.md](docs/handoff_manual.md)
- [acceptance_checklist.md](docs/acceptance_checklist.md)

Confirm:

- EMOS is positioned as an independent memory service
- the target deployment mode is local/private first
- benchmark / official LoCoMo / paper-facing assets are retained

## Step 2: Confirm Runtime Path

Run:

```powershell
.\scripts\run_api.ps1
```

Confirm:

- the service starts through the documented default entrypoint

## Step 3: Confirm Basic Service Health

Run:

```powershell
.\scripts\run_smoke.ps1
```

Confirm:

- the runtime can process, write, recall, and reflect
- no ad-hoc patching is required to complete the smoke path

## Step 4: Confirm Integration Evidence

Run:

```powershell
.\scripts\run_integration_flows.ps1
```

Confirm:

- the output includes scenario-level loops for chat, task, lifecycle, core-memory, and consistency handling
- the upper-layer integration surface is visible through `execution_surface`

## Step 5: Confirm Long-Horizon Validation Evidence

Run:

```powershell
.\scripts\run_long_horizon_validation.ps1
.\scripts\run_long_horizon_summary.ps1
```

Confirm:

- the output includes multi-profile workload evidence rather than a single linear scenario
- the validation output includes task-switch and conflict-detection metrics
- the multi-run summary includes `profile_summaries`, `drift_flags`, and `review_posture`
- long-horizon evidence is explicitly kept separate from benchmark evidence through `evidence_boundary`

## Step 6: Confirm Storage / Backup / Recovery Delivery Surface

Run:

```powershell
.\scripts\run_delivery_pack.ps1
```

Confirm:

- the delivery pack includes the current `storage_report`
- the delivery pack directly shows the shared observability review anchors for `operator_review_order`, `error_taxonomy`, ops metrics, and recommended lifecycle execution
- the storage report includes `operator_checklist` and `deployment_guidance`
- the storage backup surface includes verification metadata and restore steps
- the runbook at [storage_delivery_runbook.md](docs/storage_delivery_runbook.md) is sufficient for operator follow-up

## Step 7: Confirm Shared Observability Review Wording

Review:

- [operator_observability_guide.md](docs/operator_observability_guide.md)
- `release_readiness.error_taxonomy`
- `release_readiness.operator_review_order`
- `agent_readiness_summary.ops_metric_surface`
- `agent_readiness_summary.audit_signal_surface`

Confirm:

- the receiver has one documented wording source for shared observability review
- `error_taxonomy` classifies maintenance work into stable failure classes
- `operator_review_order` tells the reviewer which checks to inspect first
- `ops_metric_surface` and `audit_signal_surface` match the same maintenance posture
- the reviewer can continue from observability review to `recommended_lifecycle_execution`

## Step 8: Confirm Migration / Rollback Readiness

Run:

```powershell
.\scripts\run_storage_migration_preflight.ps1
```

Confirm:

- a migration preflight artifact is generated under `logs/delivery/migrations/*`
- `migration.preflight.status` is visible
- `migration.latest_attempt` is visible
- `migration.rollback.rollback_ready` is visible
- `migration.migration_acceptance` tells the reviewer whether the posture is `execute_now`, `preflight_only`, `refresh_rollback_evidence`, or `block`
- the runbook at [storage_migration_runbook.md](docs/storage_migration_runbook.md) is sufficient for upgrade-prep and rollback-prep follow-up

## Step 9: Confirm Demo/Handoff Reproducibility

Run:

```powershell
.\scripts\run_delivery_demo.ps1
```

Confirm:

- the script executes the stable demo path without requiring a separate demo-only runtime
- the generated summary points to smoke, integration, and delivery-pack outputs

## Step 10: Confirm Stable Regression

Run:

```powershell
python -B -m pytest tests/test_memory_service_contract.py tests/test_api.py tests/test_feedback_maturity.py tests/test_passive_feedback.py tests/test_retrieval_pipeline.py tests/test_storage_report.py -q
```

Confirm:

- the stable regression set passes

## Acceptance Decision

- Accept `EMOS v1` when delivery identity, runtime path, integration evidence, storage recovery path, shared observability review path, migration/rollback review path, demo reproducibility, and stable regression are all present.
- Accept `EMOS v1` when delivery identity, runtime path, integration evidence, long-horizon validation evidence, storage recovery path, shared observability review path, migration/rollback review path, demo reproducibility, and stable regression are all present.
- Confirm the formal package companions are present and readable:
  - [acceptance_evidence_bundle.md](docs/acceptance_evidence_bundle.md)
  - [emos_v1_1_known_limitations.md](docs/emos_v1_1_known_limitations.md)
  - [emos_v1_1_release_notes.md](docs/emos_v1_1_release_notes.md)
  - [emos_v1_1_packaging_checklist.md](docs/emos_v1_1_packaging_checklist.md)
  - [emos_v1_1_package_closeout.md](docs/emos_v1_1_package_closeout.md)
- Accept with follow-up when the package is otherwise complete but the target environment still needs SQLite promotion planning.
- Reject only when the documented runtime path, contract surfaces, or recovery path cannot be reproduced.
