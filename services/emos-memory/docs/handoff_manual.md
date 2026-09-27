# Handoff Manual

## What This Project Delivers

This repository delivers an independent memory engine / memory service with:

- user/session-based memory persistence
- storage health reporting and backup generation
- semantic, episodic, emotional, and reflection-style memory layers
- configurable retrieval strategy with lexical, semantic, hybrid, and embedding-rerank backends
- benchmark runner for LoCoMo-style and LangMemEval-style evaluation, including official-format adapter ingestion
- backend-comparison reporting for retrieval strategy selection
- API endpoints for processing turns, exporting user bundles, recording user feedback, exporting offline review data, switching retrieval backends, and inspecting system status

## Delivery Position

- EMOS is not the full personal agent.
- EMOS is the memory layer that an upper-layer personal agent calls through API.
- The default delivery mode for this sprint is local/private deployment first, not cloud-first SaaS.
- The current one-week delivery plan is documented in [delivery_sprint_plan_20260425_20260502.md](docs/delivery_sprint_plan_20260425_20260502.md).

## Handoff Audience

- integration owner wiring an upper-layer personal agent to EMOS
- operator responsible for local/private deployment, backup, recovery, and migration prep
- reviewer signing off on delivery readiness and package scope

## Handoff Scope

This handoff covers:

- how to start and verify the memory service
- how to read the agent-facing execution surfaces
- how to review storage / backup / recovery posture
- how to review long-horizon validation evidence and recent drift without mixing it into benchmark scoring
- how to review migration / rollback readiness before any upgrade
- how to review shared observability, failure taxonomy, and operator review order
- how to inspect the generated delivery package

This handoff does not claim:

- that EMOS is the full personal agent product
- that public-cloud SaaS deployment is in scope for this sprint
- that benchmark / official LoCoMo / paper assets are disposable

## Main Entrypoints

- CLI process: `python -m src.memory_system.cli_app process --text "..."`
- CLI snapshot: `python -m src.memory_system.cli_app snapshot --user-id demo --limit 10`
- CLI export: `python -m src.memory_system.cli_app export --user-id demo --limit 10`
- CLI feedback report: `python -m src.memory_system.cli_app feedback-report --user-id demo --limit 10`
- CLI offline-review export: `python -m src.memory_system.cli_app export-offline-review --user-id demo --limit 100`
- CLI system report: `python -m src.memory_system.cli_app system-report`
- CLI storage report: `python -m src.memory_system.cli_app storage-report`
- CLI storage backup: `python -m src.memory_system.cli_app storage-backup`
- CLI storage migration preflight: `python -m src.memory_system.cli_app storage-migration-preflight`
- CLI delivery pack: `python -m src.memory_system.cli_app delivery-pack`
- CLI long-horizon validation: `python -m src.memory_system.cli_app long-horizon-validation --limit 200`
- CLI long-horizon summary: `python -m src.memory_system.cli_app long-horizon-summary-report --limit 5`
- CLI retrieval-backend report: `python -m src.memory_system.cli_app retrieval-backends`
- CLI set retrieval backend: `python -m src.memory_system.cli_app set-retrieval-backend --backend-name embedding_rerank`
- API server: `python -m src.memory_system.api.server`
- Benchmark run: `python -m src.memory_system.benchmarks.runner`

## Runtime Scripts

- `scripts/run_smoke.ps1`
- `scripts/run_integration_flows.ps1`
- `scripts/run_delivery_demo.ps1`
- `scripts/run_long_horizon_validation.ps1`
- `scripts/run_long_horizon_summary.ps1`
- `scripts/run_storage_migration_preflight.ps1`
- `scripts/run_benchmarks.ps1`
- `scripts/run_tests.ps1`
- `scripts/run_api.ps1`
- `scripts/run_delivery_pack.ps1`
- `scripts/export_offline_review.py`

## Default Runtime Path

- Start API: `.\scripts\run_api.ps1`
- Run smoke verification: `.\scripts\run_smoke.ps1`
- Run delivery-grade integration evidence generation: `.\scripts\run_integration_flows.ps1`
- Run stable regression set:
  - `python -B -m pytest tests/test_memory_service_contract.py tests/test_api.py tests/test_feedback_maturity.py tests/test_passive_feedback.py tests/test_retrieval_pipeline.py tests/test_storage_report.py -q`

## Recommended Handoff Sequence

1. Start the runtime with `.\scripts\run_api.ps1`.
2. Confirm base health with `.\scripts\run_smoke.ps1`.
3. Generate integration evidence with `.\scripts\run_integration_flows.ps1`.
4. Generate long-horizon validation evidence with `.\scripts\run_long_horizon_validation.ps1`.
5. Review recent long-horizon drift with `.\scripts\run_long_horizon_summary.ps1`.
6. Generate migration/rollback readiness evidence with `.\scripts\run_storage_migration_preflight.ps1`.
7. Generate the formal delivery package with `.\scripts\run_delivery_pack.ps1`.
8. Review:
   - follow the observability-first review order from `delivery-pack -> final delivery manifest -> operator observability guide`
   - for any agent-facing contract or report-facing surface, prefer `policy_input -> action_surface -> agent_handoff`
   - `delivery_pack.storage_report`
   - `system_report.long_horizon_validation_summary`
   - `system_report.long_horizon_multi_run_summary`
   - long-horizon `evidence_boundary`
   - delivery-pack shared observability sections for `operator_review_order` and `error_taxonomy`
   - `storage_report.operator_checklist`
   - `storage_backup.verification`
   - `storage_report.migration.latest_attempt`
   - `storage_report.migration.rollback`
   - `storage_report.migration.migration_acceptance`
   - `agent_readiness_summary.execution_surface`
   - `release_readiness.error_taxonomy`
   - `release_readiness.operator_review_order`
   - `agent_readiness_summary.ops_metric_surface`
   - `agent_readiness_summary.audit_signal_surface`

## Delivery Artifact Checklist

- integration evidence under `logs/delivery/*`
- storage backup artifacts under `logs/delivery/storage_backups/*`
- migration preflight artifacts under `logs/delivery/migrations/*`
- long-horizon validation artifacts under `logs/delivery/long_horizon/*`
- delivery-pack JSON/Markdown outputs under `logs/delivery/*`
- demo-run summaries under `logs/delivery/demo_runs/*`
- storage operator runbook at [storage_delivery_runbook.md](docs/storage_delivery_runbook.md)
- storage migration operator runbook at [storage_migration_runbook.md](docs/storage_migration_runbook.md)
- operator observability guide at [operator_observability_guide.md](docs/operator_observability_guide.md)
- handoff example flows at [handoff_example_flows.md](docs/handoff_example_flows.md)
- acceptance walkthrough at [acceptance_walkthrough.md](docs/acceptance_walkthrough.md)
- final package manifest at [final_delivery_manifest.md](docs/final_delivery_manifest.md)
- acceptance evidence bundle at [acceptance_evidence_bundle.md](docs/acceptance_evidence_bundle.md)
- known limitations note at [emos_v1_1_known_limitations.md](docs/emos_v1_1_known_limitations.md)
- release notes at [emos_v1_1_release_notes.md](docs/emos_v1_1_release_notes.md)
- packaging checklist at [emos_v1_1_packaging_checklist.md](docs/emos_v1_1_packaging_checklist.md)
- package closeout note at [emos_v1_1_package_closeout.md](docs/emos_v1_1_package_closeout.md)
- benchmark and official LoCoMo assets retained for later reruns rather than cleaned up

## Important Outputs

- `logs/delivery/*.json`
- `logs/delivery/*.md`
- `logs/delivery/storage_backups/*`
- `logs/delivery/migrations/*`
- `logs/delivery/demo_runs/*`

## Delivery Notes

- The current default retrieval backend is `embedding_rerank`.
- The current default storage backend is `auto`, which prefers SQLite and falls back to JSON when needed.
- For storage delivery review, start with:
  - `storage_report.execution_surface.policy_input`
  - `storage_report.execution_surface.action_surface`
  - `storage_report.execution_surface.agent_handoff`
  - `storage_report.operator_checklist`
  - `storage_report.deployment_guidance`
- For report-facing review, use the same thin order when available:
  - top-level `action_surface`
  - then `agent_handoff`
  - then report-specific observability or storage fields
- For storage migration/rollback review, then continue with:
  - `storage_report.migration.preflight`
  - `storage_report.migration.latest_attempt`
  - `storage_report.migration.rollback`
  - `storage_report.migration.migration_acceptance`
- For long-horizon pilot evidence review, then continue with:
  - `system_report.long_horizon_validation_summary`
  - `system_report.long_horizon_multi_run_summary`
  - `long_horizon_validation.evidence_boundary`
  - persona-scoped `profile_summaries` before comparing any benchmark metrics
- For shared maintenance observability review, then continue with:
  - `release_readiness.error_taxonomy`
  - `release_readiness.operator_review_order`
  - `agent_readiness_summary.ops_metric_surface`
  - `agent_readiness_summary.audit_signal_surface`
  - `agent_readiness_summary.recommended_lifecycle_execution`
- A handoff-grade storage backup now also includes:
  - format
  - `sha256`
  - verification status
  - restore steps
- Delivery-pack artifacts now also carry:
  - the current `storage_report`
  - the storage runbook path
  - migration gate wording for upgrade-prep and rollback-prep review

## Receiver Decision Rule

- Accept the package as `EMOS v1` when the runtime path, integration evidence, storage recovery path, migration/rollback review path, and delivery-pack artifacts are all present and readable.
- Use [operator_observability_guide.md](docs/operator_observability_guide.md) as the default wording source for shared `error_taxonomy` and `operator_review_order` review.
- Keep receiver-facing review wording observability-first across delivery pack, demo summary, final manifest, and handoff example flows.
- Use migration-preflight evidence to decide whether upgrade prep is executable now, still preflight-only, or waiting on refreshed rollback evidence.
- Use long-horizon validation and long-horizon multi-run summary as pilot-facing stability evidence, and keep that evidence family separate from benchmark hit-rate evidence.
- Escalate for follow-up when storage remains in JSON fallback mode for a target environment that expects SQLite as the preferred primary runtime.
- Do not block this sprint handoff merely because benchmark/paper assets are still present; they are intentionally retained.
