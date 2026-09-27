# Acceptance Evidence Bundle

## Purpose

This document defines the minimum evidence bundle a receiver should review before accepting `EMOS v1` as a local/private-deployment-first memory service package.

## Core Evidence Set

- runtime bring-up evidence:
  - `.\scripts\run_smoke.ps1`
  - API/runtime path remains reproducible
- integration evidence:
  - `.\scripts\run_integration_flows.ps1`
  - integration-flow readiness remains visible in reports and delivery-pack output
- storage/recovery evidence:
  - storage report
  - latest verified backup artifact
  - latest restore-drill artifact
  - storage delivery runbook
- migration/rollback evidence:
  - latest migration preflight artifact
  - rollback-ready posture
  - storage migration runbook
- long-horizon evidence:
  - latest long-horizon validation artifact
  - latest long-horizon multi-run summary
  - benchmark boundary remains explicit
- delivery-package evidence:
  - latest delivery-pack JSON
  - latest delivery-pack Markdown
  - final delivery manifest
- stable regression evidence:
  - focused regression suite
  - smoke success
  - delivery-pack generation success

## Review Order

1. Confirm package identity and non-goals.
2. Confirm runtime path and smoke reproducibility.
3. Confirm integration evidence.
4. Confirm storage acceptance decision and recovery gate.
5. Confirm migration gate and rollback posture.
6. Confirm long-horizon evidence separately from benchmark evidence.
7. Confirm delivery-pack wording and artifact paths.
8. Confirm stable regression status.

## Evidence Acceptance Rule

- Accept when the evidence set is present, readable, and points to the same reproducible runtime path.
- Accept with follow-up when the package is otherwise complete but still carries environment-dependent SQLite promotion work.
- Escalate only when runtime, recovery, migration, or contract evidence cannot be reproduced from the packaged materials.
