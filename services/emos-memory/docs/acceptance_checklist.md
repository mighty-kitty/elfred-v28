# Acceptance Checklist

## Delivery Scope

- [ ] delivery package is described as an independent memory service, not a full personal agent
- [ ] default deployment position is local/private first
- [ ] default runtime path is documented
- [ ] one-week sprint scope is documented in `docs/delivery_sprint_plan_20260425_20260502.md`
- [ ] README, API reference, handoff manual, and acceptance checklist describe the same delivery identity
- [ ] benchmark / official LoCoMo / paper-facing assets are explicitly retained rather than treated as cleanup targets

## Functional

- [ ] CLI can process a single turn
- [ ] CLI can display a user snapshot
- [ ] CLI can export a user delivery bundle
- [ ] CLI can inspect recorded feedback
- [ ] CLI can export an offline review dataset
- [ ] CLI can display a system report
- [ ] CLI can display a storage report
- [ ] CLI can create a storage backup
- [ ] CLI can inspect retrieval backend state
- [ ] CLI can switch retrieval backend state
- [ ] API can process a turn through `POST /memory/process`
- [ ] API can inspect profile through `GET /memory/profile`
- [ ] API can list recent memories through `GET /memory/memories`
- [ ] API can return a user report through `GET /memory/report`
- [ ] API can return an export bundle through `GET /memory/export`
- [ ] API can record feedback through `POST /memory/feedback`
- [ ] API can inspect feedback through `GET /memory/feedback`
- [ ] API can return a system report through `GET /system/report`
- [ ] API can inspect retrieval backend state through `GET /system/retrieval-backends`
- [ ] API can switch retrieval backend through `POST /system/retrieval-backend`
- [ ] API can return a storage report through `GET /system/storage`
- [ ] API can create a storage backup through `GET /system/storage-backup`
- [ ] API can generate a delivery pack through `GET /system/delivery-pack`
- [ ] API can export offline reevaluation samples through `GET /system/offline-review-export`
- [ ] reflection summaries are generated on configured intervals

## Retrieval

- [ ] recall handles direct lexical matches
- [ ] recall handles paraphrase matches through aliases
- [ ] recall handles semantic similarity through the semantic backend
- [ ] recall handles dense retrieval through the embedding-rerank backend
- [ ] responses include `retrieval_candidates`
- [ ] retrieval backend is configurable
- [ ] retrieval backend configuration can be persisted without code changes
- [ ] retrieval traces expose lexical, fuzzy, semantic, embedding, rerank, recency, and profile signals
- [ ] retrieval traces expose feedback-aware rerank effects

## Evaluation

- [ ] benchmark harness loads LoCoMo-style data
- [ ] benchmark harness loads LangMemEval-style data
- [ ] benchmark harness can ingest official-format adapter datasets through manifest-driven discovery
- [ ] benchmark report writes JSON output
- [ ] benchmark report writes Markdown output
- [ ] backend comparison report is generated
- [ ] summary includes hit@1, hit@3, MRR, pass@TargetRank, split metrics, task metrics, and difficulty metrics
- [ ] long-horizon validation run succeeds through `scripts/run_long_horizon_validation.ps1`
- [ ] long-horizon multi-run summary succeeds through `scripts/run_long_horizon_summary.ps1`
- [ ] long-horizon evidence remains explicitly separate from benchmark evidence

## Engineering

- [ ] test suite passes through `scripts/run_tests.ps1`
- [ ] minimal delivery regression passes for API, feedback loop, storage, and embedding backend
- [ ] benchmark run succeeds through `scripts/run_benchmarks.ps1`
- [ ] smoke run succeeds through `scripts/run_smoke.ps1`
- [ ] integration evidence run succeeds through `scripts/run_integration_flows.ps1`
- [ ] demo script succeeds through `scripts/run_delivery_demo.ps1`
- [ ] API can be started through `scripts/run_api.ps1`
- [ ] delivery pack can be generated through `scripts/run_delivery_pack.ps1`
- [ ] storage layer reports its resolved backend and health metadata
- [ ] storage layer reports delivery-oriented `policy_input` / `execution_policy` / `execution_surface`
- [ ] storage layer reports backup inventory, operator checklist, and deployment guidance
- [ ] storage layer reports `primary_storage_mode`, `primary_storage`, and `operator_decision_path`
- [ ] storage layer reports `last_restore_drill_at`, `last_restore_drill_status`, and `restore_confidence`
- [ ] storage layer reports restore-drill freshness and rerun rules
- [ ] storage layer reports migration policy, preflight status, and rollback readiness
- [ ] storage layer reports a migration acceptance decision rule
- [ ] storage layer can emit a backup artifact
- [ ] storage backup exposes verification metadata and restore steps
- [ ] storage backup falls back to JSON if SQLite backup fails at runtime
- [ ] feedback events persist to a dedicated store
- [ ] interaction logs persist to JSONL
- [ ] offline reevaluation export writes a JSON dataset artifact
- [ ] SQLite persistence survives agent restart when the environment allows SQLite
- [ ] automatic fallback to JSON works when SQLite is blocked
- [ ] development log is up to date

## Handoff

- [ ] handoff manual describes who receives EMOS and what is in scope
- [ ] handoff manual provides a receiver-facing runtime and verification sequence
- [ ] handoff example flows provide stable receiver-facing examples for runtime, integration, storage, and delivery review
- [ ] handoff manual explains when to review long-horizon validation versus benchmark evidence
- [ ] operator observability guide explains how to read `ops_metric_surface`, `audit_signal_surface`, `error_taxonomy`, and `operator_review_order`
- [ ] handoff manual and handoff example flows use the same observability-first wording as the delivery pack, demo summary, and final manifest
- [ ] handoff and acceptance wording use the same thin read order: `policy_input -> action_surface -> agent_handoff`
- [ ] delivery package points the operator to storage report, storage backup verification, and storage runbook
- [ ] storage handoff materials explain how to decide between healthy primary, degraded fallback, and blocked storage modes
- [ ] delivery pack exposes the restore-drill gate through `last_restore_drill_status` and `restore_confidence`
- [ ] delivery pack explains when existing restore-drill evidence is acceptable versus when rerun is required
- [ ] delivery pack is positioned as a formal handoff artifact instead of a debug-only export
- [ ] migration runbook describes preflight review order and rollback rule
- [ ] migration runbook explains execute-now vs preflight-only vs refresh-rollback-evidence vs block
- [ ] handoff and acceptance wording directly references shared `error_taxonomy` and `operator_review_order`

## Documentation Artifacts

- [ ] README explains package role, runtime path, delivery review order, and non-goals
- [ ] API reference explains preferred thin integration surfaces for recall, readiness, and storage
- [ ] API reference explains the shared `action_surface` contract for write, lifecycle, block, reflection, and report-facing review
- [ ] handoff manual explains the recommended handoff sequence and receiver decision rule
- [ ] acceptance walkthrough explains the reviewer sequence for runtime, integration, storage, demo, and regression checks
- [ ] acceptance walkthrough explains the reviewer sequence for long-horizon validation and multi-run drift review
- [ ] final delivery manifest summarizes runtime path, validation snapshot, retained assets, and receiver decision rule
- [ ] acceptance checklist covers package identity, operator path, and asset-retention expectations
- [ ] documentation artifacts consistently point operators to the shared observability guide for review wording
- [ ] acceptance evidence bundle is present as a formal package-level artifact
- [ ] known limitations note is present as a formal package-level artifact
- [ ] release notes are present as a formal package-level artifact
- [ ] packaging checklist is present as a formal package-level artifact
- [ ] package closeout note is present as a formal package-level artifact
