# EMOS Delivery Sprint Plan (2026-04-25 to 2026-05-02)

## Delivery Target

Deliver `EMOS v1` as a local/private-deployment-first memory engine / memory service.

This sprint does not target a full cloud SaaS launch. It targets a stable and explainable delivery package that an upper-layer personal agent can call through API without depending on ad-hoc memory logic.

## Locked Scope

### In Scope

- stable memory service API for `write / plan / recall / reflect / update / forget`
- lifecycle and consistency surfaces
- agent-facing `policy_input`, `agent_handoff`, and response contracts
- local/private deployment guidance
- storage, backup, and recovery guidance appropriate for delivery
- real integration-flow evidence for chat, task, and consistency-resolution loops
- benchmark and official LoCoMo evaluation assets retained for later paper work

### Out of Scope For This Sprint

- public-cloud multi-tenant SaaS deployment
- large-scale online learning loop
- full market-scale observability platform
- major benchmark-driven architecture pivots

## Deployment Position

- Default delivery mode: local or private-server deployment
- Default retrieval backend: `embedding_rerank`
- Default storage mode: `auto`, preferring SQLite and falling back to JSON when blocked
- Default operator goal: run EMOS as an independent memory service behind API for an upper-layer personal agent

## Default Runtime Path

### Recommended startup

```powershell
.\scripts\run_api.ps1
```

### Recommended smoke verification

```powershell
.\scripts\run_smoke.ps1
```

### Stable regression set

```powershell
python -B -m pytest tests/test_memory_service_contract.py tests/test_api.py tests/test_feedback_maturity.py tests/test_passive_feedback.py tests/test_retrieval_pipeline.py tests/test_storage_report.py -q
```

## Daily Plan

### 2026-04-25

- lock delivery scope
- lock deployment positioning
- lock default runtime path
- remove obvious packaging/runtime confusion

### 2026-04-26

- add real integration-flow evidence
- prioritize clearing readiness blockers caused by missing runtime traces
- make chat / task / consistency-resolution loops observable in reports
- implementation path: `.\scripts\run_integration_flows.ps1`

### 2026-04-27

- further thin the agent-facing execution surface
- converge upper-layer inputs around `policy_input`, `agent_handoff`, and direct policy-style fields

### 2026-04-28

- finish storage / backup / recovery delivery hardening
- make storage guidance read like a deployment checklist rather than an engineering note

### 2026-04-29

- update `README.md`
- update `docs/api_reference.md`
- update handoff / integration / delivery-facing docs

### 2026-04-30

- prepare end-to-end demo script
- prepare acceptance checklist
- prepare stable example flows for delivery handoff

### 2026-05-01

- run full regression
- fix edge cases
- clean delivery materials

### 2026-05-02

- reserve buffer for fixes only
- no new feature expansion
- package and hand off

## Required Exit Criteria

- smoke run succeeds
- stable regression set succeeds
- API startup path is documented and reproducible
- upper-layer agent can consume direct policy-style memory outputs
- at least chat, task, and consistency-resolution flows are evidenced in reports/logs
- storage/backup/recovery guidance is delivery-ready
- README, API reference, and development log are current

## Assets To Keep During Cleanup

- `src/memory_system/benchmarks/*`
- `scripts/run_benchmarks.ps1`
- `scripts/run_official_locomo.ps1`
- `scripts/run_official_locomo_midscale.ps1`
- `scripts/run_official_locomo_batch.py`
- `data/benchmarks/*`
- benchmark result snapshots needed for paper writing

## Non-Destructive Cleanup Rule

During this sprint, do not delete benchmark datasets, benchmark runners, or paper-facing evaluation assets. Cleanup should focus on broken entrypoints, generated runtime artifacts, stale cache files, and packaging confusion.
