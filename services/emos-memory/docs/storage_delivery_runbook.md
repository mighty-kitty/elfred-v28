# Storage Delivery Runbook

## Goal

This runbook is the operator-facing storage / backup / recovery checklist for `EMOS v1`.

Use it when preparing local/private deployment handoff, validating a pilot environment, or restoring storage after runtime failure.

## Default Position

- Preferred deployment mode: local machine or private server
- Preferred storage mode: `auto`
- Preferred steady state: SQLite active as the primary store, JSON fallback available
- Preferred startup path: `.\scripts\run_api.ps1`

## Daily Operator Checklist

1. Run `python -m src.memory_system.cli_app storage-report`.
2. Confirm `readiness` is not `risky`.
3. Confirm `operator_checklist.fail_count` is `0`.
4. Confirm the latest backup is recent enough for your delivery window.
5. Confirm `operator_decision_path.primary_storage_mode`.
6. If `primary_storage_mode=degraded_fallback`, record that explicitly in the handoff note and keep backups current.
7. Before handoff, create a fresh backup with `python -m src.memory_system.cli_app storage-backup`.
8. Run `python -m src.memory_system.cli_app storage-restore-drill` when you need fresh recovery evidence for the current delivery round, and confirm the latest healthy backup candidate is the one that passed.

## Required Review Fields

Read these fields first from the storage report:

- `execution_surface`
- `policy_input`
- `execution_policy`
- `operator_checklist`
- `operator_decision_path`
- `operator_acceptance_note`
- `remediation_checklist`
- `deployment_guidance`
- `recovery.latest_backup`
- `recovery.latest_restore_drill`
- `recovery.restore_drill_freshness`
- `backup_inventory`

## Delivery Gate

Treat storage as delivery-ready only when all of the following are true:

- `integrity_ok` is `true`
- `operator_checklist.fail_count` is `0`
- `operator_decision_path.delivery_decision` is not `block`
- `recovery.recovery_confidence` is not `low`
- a backup artifact exists
- the latest restore drill is `passed` and fresh enough for the current delivery round when recovery evidence is required
- restore steps are documented in the active delivery pack or handoff package

## Restore-Drill Freshness Rule

- Existing restore-drill evidence is acceptable when `recovery.latest_restore_drill.status=passed` and `recovery.restore_drill_freshness.age_hours<=24`.
- Rerun the restore drill when the latest evidence is missing, failed, or older than 24 hours.
- If the latest drill failed, fix the recovery issue before treating a rerun as valid evidence.

## Primary Storage Decision Path

- `healthy_primary`
  - Delivery decision: proceed
  - Operator action: maintain primary storage health
  - Acceptance posture: normal acceptance if other gates are green
- `degraded_fallback`
  - Delivery decision: proceed with follow-up
  - Operator action: restore the preferred primary storage path
  - Acceptance posture: only accept if the fallback state is explicitly recorded and recovery evidence is current
- `blocked`
  - Delivery decision: block
  - Operator action: fix storage integrity before delivery
  - Acceptance posture: do not accept until the primary path is unblocked

## Backup Procedure

1. Run `python -m src.memory_system.cli_app storage-backup`.
2. Record the returned:
   - `path`
   - `backend`
   - `backup_mode`
   - `format`
   - `sha256`
   - `verification.status`
3. Keep the newest verified backup path in the delivery note.
4. Do not delete older benchmark or evaluation assets during storage cleanup.

## Recovery Procedure

1. Stop the EMOS API or any process writing to the active store.
2. If the current store is still readable, create one last backup before replacement.
3. Choose the latest healthy backup from `backup_inventory`.
4. Replace the active JSON or SQLite file with the selected artifact.
5. Restart EMOS.
6. Run:
   - `python -m src.memory_system.cli_app storage-report`
   - `.\scripts\run_smoke.ps1`
   - `.\scripts\run_integration_flows.ps1`
7. Confirm the storage report shows healthy integrity and the expected memory count.

## Escalation Rules

Pause delivery and treat storage as blocked when:

- `readiness` is `risky`
- `operator_decision_path.delivery_decision` is `block`
- `storage_schema_drift` appears in blockers
- `storage_integrity_not_ok` appears in blockers
- backup verification is incomplete and no earlier healthy backup is available

## Handoff Note Template

- Storage backend:
- Storage readiness:
- Primary storage mode:
- Primary storage decision:
- Acceptance note summary:
- Restore-drill freshness summary:
- Persistence confidence:
- Latest backup path:
- Latest backup sha256:
- Backup mode:
- Restore-tested this round: yes / no
- Known storage warnings:

## Degraded Fallback Remediation Checklist

When `primary_storage_mode=degraded_fallback`, record the acceptance note and complete at least:

- keep one recent verified backup artifact available
- inspect the SQLite fallback reason
- record that the current delivery is accepted only with follow-up
- schedule restoration of the preferred primary path before the next stricter delivery gate
