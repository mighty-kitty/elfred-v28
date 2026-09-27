# EMOS v1.1 Hardening Roadmap

## Goal

`EMOS v1.1` does not expand into a full personal agent or a cloud SaaS product.

The goal is to move EMOS from `limited_pilot` toward a more mature market-applicable memory system by hardening:

- storage primary path
- backup / recovery / restore confidence
- migration / rollback discipline
- consistency auto-governance
- observability and operator surfaces
- long-horizon workload evidence
- thin agent-facing integration surfaces

## Scope Rules

- Keep benchmark / official LoCoMo / paper-facing assets intact.
- Prefer hardening and operational trust over adding broad new features.
- Preserve the current local/private-deployment-first delivery position.

## Week 1: Storage Primary Path Hardening

### Objective

Move storage from “has fallback” toward “has a clearly modeled primary path.”

### Tasks

- define the primary storage expectation explicitly in the storage report
- distinguish `healthy_primary`, `degraded_fallback`, and `blocked` storage states
- treat JSON fallback as a degraded mode when SQLite is the preferred primary path
- tighten storage operator guidance around primary-path recovery and fallback handling
- update tests and API docs to reflect the stronger primary-path contract

### Expected Outputs

- storage report exposes a formal primary-path surface
- operator checklist distinguishes degraded fallback from healthy primary operation
- upper-layer policy input can point to primary-path hardening when fallback is active

## Week 2: Backup / Recovery / Restore Drill

### Objective

Turn backup/recovery from a capability into a verified drill path.

### Tasks

- add a restore-drill script
- validate backup readability, hash integrity, and restore format before acceptance
- record last restore-drill status in storage/recovery surfaces
- document recovery acceptance criteria and operator SOP

### Expected Outputs

- repeatable restore drill
- recovery confidence backed by drill evidence
- recovery acceptance checklist

## Week 3: Migration / Upgrade / Rollback

### Objective

Make storage upgrades and schema changes safe enough for delivery use.

### Tasks

- define schema version policy
- add migration preflight checks
- add migration status and rollback availability surfaces
- document migration and rollback runbooks

### Expected Outputs

- migration policy
- migration report/preflight
- rollback-ready operator path

## Week 4: Consistency Auto-Governance I

### Objective

Reduce the amount of manual consistency review needed for everyday operation.

### Tasks

- classify revised, superseded, disputed, stale, and ambiguous memory states
- define which cases can auto-resolve, confirm, or require history-first review
- strengthen recall/write guardrails around revised and stale facts
- improve write/update resolution stability

### Expected Outputs

- consistency rule table
- safer auto-handled consistency flow
- stronger regression coverage for conflict cases

## Week 5: Consistency Auto-Governance II

### Objective

Push consistency handling from a report surface toward a maintenance surface.

### Tasks

- add a consistency maintenance surface
- split actions into auto-safe / confirm-required / manual-review buckets
- further thin lifecycle/history execution surfaces
- align release readiness more directly with consistency state

### Expected Outputs

- consistency maintenance view
- thinner lifecycle integration surface
- tighter readiness gating

## Week 6: Observability / Audit / Ops Metrics

### Objective

Make EMOS look more like an operable service than a feature-complete codebase.

### Tasks

- add service/storage/backup/consistency health metrics
- define an error taxonomy
- add audit trail coverage for backup, restore, migration, and fallback transitions
- document operator review order

### Expected Outputs

- production-leaning ops metric surface
- audit event taxonomy
- operator observability guidance

## Week 7: Long-Horizon Workload Validation

### Objective

Prove stability beyond short smoke/integration runs.

### Tasks

- create long-horizon workload fixtures
- build a long-horizon validation runner
- report pollution, contradiction, stale-fact exposure, and recall stability
- separate benchmark evidence from long-horizon workload evidence

### Expected Outputs

- long-horizon validation runner
- stability report for accumulated memory usage

## Week 8: Agent Surface Final Unification

### Objective

Reduce remaining upper-layer integration friction.

### Tasks

- unify write/update/lifecycle execution surfaces
- unify top-level policy input shape
- converge recommended action / next action schema
- add stronger integration examples for chat, recall, lifecycle, and storage review

### Expected Outputs

- more uniform agent-facing contract family
- stronger integration example pack

## Week 9: Packaging / Deployment / Acceptance Finalization

### Objective

Turn v1.1 into a cleaner release package.

### Tasks

- finalize delivery bundle composition
- package acceptance evidence
- publish known limitations and follow-up items
- write v1.1 release notes

### Expected Outputs

- final v1.1 delivery bundle
- acceptance evidence bundle
- release note and limitation note

## Priority Mapping

- `P0`: Week 1, Week 2, Week 3, Week 4
- `P1`: Week 5, Week 6, Week 7, Week 8
- finalization: Week 9

## Weekly Operating Rhythm

Each week should still update:

- [README.md](README.md)
- [docs/api_reference.md](docs/api_reference.md)
- [docs/development_log.md](docs/development_log.md)

Each week should still validate:

- `.\scripts\run_tests.ps1`
- `.\scripts\run_smoke.ps1`
- `.\scripts\run_integration_flows.ps1`
- `.\scripts\run_delivery_pack.ps1`
- `.\scripts\run_delivery_demo.ps1`

## v1.1 Exit Intent

By the end of `EMOS v1.1`, the system should be materially closer to:

- stable primary storage instead of routine fallback posture
- repeatable restore confidence
- safer migration and rollback
- lower consistency-review pressure
- stronger operator/observability posture
- longer-horizon runtime evidence
- thinner and more uniform upper-layer integration
