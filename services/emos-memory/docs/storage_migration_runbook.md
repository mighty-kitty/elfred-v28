# Storage Migration Runbook

## Purpose

Use this runbook before any storage upgrade, schema promotion, or backend migration.

EMOS v1.1 Week 3 treats migration as acceptable only when preflight and rollback posture are both visible.

## Primary Command

- `python -m src.memory_system.cli_app storage-migration-preflight`
- `.\scripts\run_storage_migration_preflight.ps1`

## Review Order

Read these fields first from `storage_report.migration`:

- `policy_version`
- `schema_version`
- `schema_status`
- `target_schema_version`
- `upgrade_strategy`
- `preflight`
- `rollback`
- `latest_attempt`

## Preflight Rule

- `preflight.status=ready`: migration can proceed if the operator still wants to perform the change in this round.
- `preflight.status=review`: do not execute migration yet; resolve warning items first, usually backup freshness or restore-drill freshness.
- `preflight.status=blocked`: do not execute migration until blocking issues are cleared.

## Rollback Rule

- Treat migration as rollback-ready only when `rollback.rollback_ready=true`.
- Prefer the latest recent backup artifact as the rollback anchor.
- If rollback evidence is present but stale, refresh backup and restore-drill evidence before any upgrade.

## Latest Attempt Rule

- Treat `latest_attempt.status` as the current migration-result evidence for this delivery round.
- If `latest_attempt.status=not_run`, there is still no recorded migration attempt artifact.
- If `latest_attempt.status=ready`, the latest recorded migration preflight is green enough to prepare an actual upgrade step.
- If `latest_attempt.status=review` or `blocked`, do not proceed until those issues are cleared.

## Operator Decision Rule

- `migration_acceptance.decision=execute_now`: upgrade may execute now because preflight is ready and rollback evidence is fresh.
- `migration_acceptance.decision=preflight_only`: do not execute yet; the system is only ready to stay at preflight posture until a fresh migration attempt is recorded.
- `migration_acceptance.decision=refresh_rollback_evidence`: do not execute yet; refresh backup and/or restore-drill evidence first.
- `migration_acceptance.decision=block`: do not execute until blocking preflight issues are cleared.

## Current Baseline Policy

- preferred target schema version: `2`
- fallback backend: `json`
- rollback strategy: `restore_latest_verified_backup`
- supported upgrade paths:
  - `json_snapshot_replace_to_sqlite_v2`
  - `sqlite_in_place_v2`

## Operator Checklist

1. Run storage preflight.
2. Confirm `storage_integrity_ok`.
3. Confirm recent backup availability.
4. Confirm restore-drill evidence is still acceptable for the current delivery round.
5. Confirm rollback artifact path is known.
6. Only then schedule or execute the storage migration step.
