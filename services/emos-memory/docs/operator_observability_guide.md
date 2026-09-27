# Operator Observability Guide

## Purpose

This guide explains how an operator should read the shared observability layer that now appears across:

- `consistency_audit`
- `release_readiness`
- `agent_readiness_summary`

The goal is to keep operator and agent review aligned on the same:

- `ops_metric_surface`
- `audit_signal_surface`
- `error_taxonomy`
- `operator_review_order`

## Shared Review Principle

Do not interpret raw counters in isolation. Reviewers should read the shared observability surfaces in this order:

1. `operator_review_order`
2. `error_taxonomy`
3. `ops_metric_surface`
4. `audit_signal_surface`
5. `recommended_lifecycle_execution`

This sequence keeps the receiver focused on:

- what to inspect first
- how to classify the issue
- how large the queue or pressure is
- what evidence supports the signal
- which lifecycle execution path to follow next

## Shared Surfaces

### `ops_metric_surface`

Use this surface to inspect the current operational shape of maintenance work.

Primary fields:

- `manual_review_queue_depth`
- `confirm_required_queue_depth`
- `auto_safe_queue_depth`
- `maintenance_job_count`
- `enabled_maintenance_job_count`
- `lifecycle_execution_path_count`
- `recommended_lifecycle_operation`
- `storage_primary_mode_status`
- `storage_restore_confidence`
- `storage_restore_drill_status`
- `storage_restore_drill_freshness`

### `audit_signal_surface`

Use this surface to understand which concrete signals are currently active and shared between operator and agent consumers.

Primary signal families:

- manual review queue
- confirmation guard queue
- lifecycle execution path availability
- storage restore drill status

### `error_taxonomy`

Use this surface to classify operational issues before choosing a remediation path.

Current stable error classes:

- `storage_primary_path_degraded`
- `storage_restore_evidence_stale`
- `consistency_manual_review_queue_non_empty`
- `consistency_confirmation_queue_non_empty`
- `lifecycle_execution_paths_missing`

Each taxonomy item tells the receiver:

- category
- severity
- whether the issue is active
- the source field
- the recommended flow

### `operator_review_order`

Use this surface as the default inspection sequence. The current standard order is:

1. `storage_primary_path`
2. `storage_restore_drill_freshness`
3. `consistency_manual_review_queue`
4. `consistency_confirmation_queue`
5. `recommended_lifecycle_execution`

The `next_review` field points to the first still-relevant check.

## Review Wording

Use the following wording in operator-facing acceptance and handoff review:

- Start with `operator_review_order` rather than reading report sections out of sequence.
- Use `error_taxonomy` to classify whether the issue is storage, recovery, consistency, or execution-surface related.
- Use `ops_metric_surface` to judge queue depth and maintenance pressure.
- Use `audit_signal_surface` to confirm the signal is backed by current evidence.
- Use `recommended_lifecycle_execution` only after the earlier review steps are understood.

## Acceptance Guidance

### Accept

Accept when:

- `operator_review_order.next_review` does not point to a blocking storage/recovery failure
- `error_taxonomy.highest_severity` is not `high`
- restore-drill evidence is fresh enough for current acceptance
- lifecycle execution paths are present when consistency review is needed

### Accept With Follow-up

Accept with follow-up when:

- `storage_primary_path_degraded` is active but recovery evidence is healthy
- confirmation/manual-review queues are non-empty but bounded and visible
- the receiver has a clear `recommended_lifecycle_execution`

### Escalate / Block

Escalate or block when:

- `storage_restore_evidence_stale` is active and rerun is required
- manual-review pressure is high and no lifecycle execution path is present
- primary storage is blocked
- the shared observability surfaces are missing or internally inconsistent

## Related Materials

- [handoff_manual.md](docs/handoff_manual.md)
- [acceptance_checklist.md](docs/acceptance_checklist.md)
- [acceptance_walkthrough.md](docs/acceptance_walkthrough.md)
- [final_delivery_manifest.md](docs/final_delivery_manifest.md)
