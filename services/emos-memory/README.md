# AI Memory System

A modular memory engine / memory service for local development, evaluation, delivery, and API serving.

## GitHub Quickstart

```powershell
git clone <repo-url>
cd <repo-dir>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m src.memory_system.api.server
```

In another terminal, run the minimal integration client:

```powershell
python examples\agent_api_client.py
```

## Delivery Mode

- EMOS is not positioned as a full personal agent.
- EMOS is positioned as an independent memory engine / memory service that an upper-layer personal agent calls through API.
- The current delivery target is `EMOS v1`: a local/private-deployment-first service package that is stable, explainable, and easy to integrate.
- The current sprint plan is documented in [docs/delivery_sprint_plan_20260425_20260502.md](docs/delivery_sprint_plan_20260425_20260502.md).

## Delivery Package Summary

- Package name: `EMOS v1`
- Package role: independent memory engine / memory service for an upper-layer personal agent
- Deployment position: local workstation or private server first
- Primary runtime shape: API service with CLI/operator entrypoints
- Agent API discovery surfaces:
  - `GET /`
  - `GET /openapi.json`
  - `GET /system/agent-api-manifest`
- Intended readers of this repository:
  - integration engineers wiring a personal agent to memory APIs
  - private-deployment operators responsible for backup / recovery / migration
  - reviewers validating that EMOS is deliverable as a standalone subsystem

## What Ships In EMOS v1

- Stable memory-service contracts for `write / plan / recall / reflect / update / forget`
- Core memory block management and memory lifecycle operations
- Delivery-facing storage, backup, recovery, and migration surfaces
- Retrieval backend governance, runtime switching, and explainable recall traces
- Integration evidence, delivery-pack generation, and system-readiness reporting
- Benchmark, official LoCoMo, and paper-facing evaluation assets retained for later reruns

## What EMOS v1 Does Not Claim To Be

- Not a full personal agent
- Not a public-cloud multi-tenant SaaS product in this sprint
- Not a replacement for upper-layer dialogue policy, product UX, or orchestration logic
- Not a reason to delete benchmark or paper-facing assets that are still needed for later replication

## Current Status

- Core workflow implemented: observe, emotion tagging, memory commit, recall, reflection.
- Retrieval supports configurable aliases, stop tokens, weights, and backend selection.
- Retrieval and passive-feedback utilities are designed to generalize across both Chinese and English user turns.
- Available retrieval backends: `lexical`, `semantic`, `hybrid`, `embedding_rerank`.
- Default retrieval backend is `embedding_rerank`.
- Default storage backend is `auto`: prefer SQLite with a `DELETE` journal mode primary path, then fall back to JSON only when SQLite is truly blocked.
- When the workspace path is not SQLite-safe, EMOS now places the primary SQLite runtime under an ASCII-safe local temp runtime path and bootstraps current JSON state into SQLite automatically.
- Formal benchmark harness is wired for LoCoMo-style and LangMemEval-style datasets, plus official-format adapter fixtures.
- Formal benchmark harness can also ingest the official LoCoMo full QA dataset through `data/benchmarks/official`.
- Benchmark comparison now evaluates canonical backends under isolated runtime storage, with per-task and per-difficulty summaries.
- API supports processing, profile inspection, memory listing, user export, storage inspection, and system report generation.
- API now also supports feedback capture, offline-review export, runtime retrieval-backend switching, and agent-facing memory lifecycle operations.
- API now also exposes agent-facing `write / recall / reflect / update / forget` memory service contracts for upper-layer personal agents.
- API now also exposes machine-readable agent discovery surfaces:
  - `GET /`
  - `GET /openapi.json`
  - `GET /system/agent-api-manifest`
- Agent-facing service responses now use a stable `contract_version / operation / payload` envelope so upper-layer agents can integrate without depending on ad-hoc response shapes.
- Retrieval switching now exposes backend descriptors, parameter validation, and switch history for runtime governance.
- Feedback capture now retains event ids, weighted signals, profile insights, and bounded rerank adaptation.
- Offline-review export now produces manifest-backed reevaluation datasets with sample labels derived from linked feedback.
- Delivery-pack generation is available through CLI and script entrypoints.
- Long-horizon validation now runs as a multi-profile workload with persona-specific conflict checks and task-switch recall, separate from benchmark evidence.
- Week 7 long-horizon closure: the multi-profile runner, multi-run drift summary, delivery-pack evidence boundary, and receiver-facing review path have all been validated together and are ready for Week 8 handoff.
- Week 8 agent-surface unification has started: write-plan / write now expose the same thin execution-policy pattern as lifecycle flows, and a shared `action_surface` now normalizes `recommended_action`, `next_action`, and handoff `mode`.
- Week 8 follow-through: block, reflection, storage, readiness, and report-facing surfaces now also expose the same `action_surface` semantics, so upper-layer consumers can keep one stable read order across memory contracts and delivery reports.
- Week 8 final sweep: retrieval backend review, storage backup / restore-drill / migration-preflight artifacts, long-horizon evidence summaries, and the top-level system report now also expose the same thin `policy_input + execution_policy + execution_surface + action_surface` contract, so there are no remaining delivery-visible surfaces that require special-case parsing.
- Delivery-pack Markdown now also spells out the same thin read order, so packaged handoff materials mirror the API/report contract style instead of only listing artifacts.
- Week 9 package finalization is now closed: the package now carries a formal acceptance evidence bundle, a known-limitations note, v1.1 release notes, a packaging checklist, and a package closeout note, so receiver-facing delivery behaves like a final release bundle instead of a loose collection of reports.
- Phase A readiness baseline is now live: `readiness-baseline-report` and `GET /system/readiness-baseline` expose a source map, repair sequence, and evidence snapshot for the current `release_readiness` / `agent_readiness_summary` posture, so the next hardening phases can work from one explicit baseline instead of manually stitching multiple reports.
- Phase B integration hardening is now live: `integration-flow-report` and `GET /system/integration-flow` can bridge thin runtime scopes with recent validated integration evidence, so a narrow local sample window no longer falsely degrades `integration.readiness` when delivery-grade integration artifacts are already green.
- Phase C user-experience friction reduction is now live: `user_experience-report` now distinguishes `protective_confirmation` from `friction_confirmation`, and recall no longer forces confirmation for every low-confidence answer when one grounded fact, supporting core blocks, clean conflict state, and low freshness risk already support a cautious answer.
- Phase D training-signal completion is now live: offline review exports now recognize `protocol_labeled` service-operation samples as formal training signal, so decision-protocol, guardrail, response-contract, and response-plan-rich traces are no longer miscounted as fully unlabeled.
- Phase C final UX closeout is now also live: the UX report distinguishes raw runtime posture from a recent calm-runtime trend, so older one-off confirmation events no longer permanently outweigh a newer sequence of grounded, no-confirmation recall behavior.
- Current post-Phase-C/Phase-D baseline snapshot on `2026-04-30`: `integration_readiness=ready`, `training_readiness=ready`, `user_experience_readiness=comfortable`, `release_readiness=market_pilot_ready`, and the scoped readiness baseline currently has no active sources.
- Phase E stability surface is now live: long-horizon validation, multi-run summary, and the top-level system report now expose `phase_e_stability`, so consistency/hygiene queue pressure can be reviewed separately from thin session-scoped release posture.
- Phase E false-positive fix is now live: resolved `supersede / merge` lifecycle history no longer gets misclassified as manual-review consistency debt inside the consistency audit.
- SQLite recovery drill hardening is now live: when delivery artifacts live under a non-ASCII workspace path, restore drills stage SQLite backups through an ASCII-safe temp runtime path and still write discoverable drill evidence back into `logs/delivery/restore_drills/`.
- Current storage/recovery snapshot on `2026-04-30`: `resolved_backend=sqlite`, `primary_mode_status=healthy_primary`, latest `restore_drill.restored_backend=sqlite`, and delivery-pack recovery gates now reflect SQLite-backed restore evidence instead of older JSON fallback evidence.
- Development log is maintained in `docs/development_log.md`.
- Agent API onboarding quickstart is maintained in [docs/agent_api_quickstart.md](docs/agent_api_quickstart.md).
- Agent local deployment guide is maintained in [docs/agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md).
- Agent endpoint catalog is maintained in [docs/agent_api_endpoint_catalog.md](docs/agent_api_endpoint_catalog.md).
- A minimal example client is available in [examples/agent_api_client.py](examples/agent_api_client.py).
- A request collection for manual API testing is available in [examples/agent_api_requests.http](examples/agent_api_requests.http).
- Official benchmark experiments also support mid-scale stage-gate runs and optional consolidation-free analysis.

## Project Layout

```text
.
├─ src\memory_system\
│  ├─ api\
│  ├─ benchmarks\
│  ├─ cli_app.py
│  ├─ config.py
│  ├─ emotion_engine.py
│  ├─ emotion_v2.py
│  ├─ memory_features.py
│  ├─ memory_repository.py
│  ├─ retrieval_assets.py
│  ├─ retrieval_backends.py
│  ├─ retrieval_config.py
│  ├─ storage_backends.py
│  └─ workflow.py
├─ configs\
├─ data\benchmarks\
├─ docs\
├─ logs\
├─ scripts\
├─ tests\
├─ final.py
├─ legacy\
└─ test.py
```

## Key Capabilities

- Semantic memory: persistent user interests and keyword accumulation.
- Episodic memory: event-centric storage tied to users and sessions.
- Emotional memory: rule-based emotional signals and salience gating.
- Reflection memory: periodic dream-style summaries of recent trajectories.
- Explainable recall: ranked `retrieval_candidates` with lexical, semantic, fuzzy, embedding, rerank, recency, profile, abstraction, and surface-text metadata.
- Configurable retrieval: aliases, stop tokens, backend weights, backend name.
- Benchmark reporting: hit@1, hit@3, MRR, pass@TargetRank, average top score, split summaries, backend comparison, and manifest-driven dataset discovery.
- Delivery exports: user bundle, storage backup, and system report surfaces for handoff and demo.
- Long-horizon workload validation: scenario-based accumulated-memory evidence with separate stability, task-switch, and conflict-detection metrics that are reviewed independently from benchmark hit-rate metrics.
- Long-horizon multi-run summary: recent validation runs are now aggregated into a drift-oriented summary so persona/workload stability can be reviewed over time instead of only per run.
- Feedback loop: explicit and passive interaction feedback, weighted feedback events, decayed user preference profile, preference-aware rerank bonus, and profile insights.
- Passive feedback adaptation: natural user corrections, affirmations, and repeated questioning can be converted into bounded memory-ranking signals without requiring explicit button clicks.
- Offline review entry: interaction logs are retained with interaction ids and query signatures, then exported into manifest-backed offline reevaluation datasets.
- Offline review exports now retain language hints, shown-set metadata, and positive/negative preference ids for later rerank training.
- Offline review exports now also include candidate-level exposure labels, operation metadata, agent context fields, and score decomposition features so later reranker training can consume shown candidates with preferred/rejected/unlabeled status directly.
- Replaceable retrieval backend: API and config can switch between `lexical`, `semantic`, `hybrid`, and `embedding_rerank`, with validated settings and switch history.
- Agent-facing memory service: separate write/recall/reflect contracts so an upper-layer personal agent does not have to infer long-term-memory policy from a single generic endpoint.
- Agent-facing memory lifecycle: upper-layer personal agents can now update or soft-forget long-term memories instead of only writing and recalling them.
- Hierarchical memory interface: recall now returns both archival retrieval results and always-visible core memory blocks, closer to mature agent-memory architectures.
- Auditable memory lifecycle: update/forget operations now preserve revision history so upper-layer agents and operators can inspect how a memory changed over time.
- Write-time memory resolution: the service now distinguishes between new memory, near-duplicate memory, and update-worthy related memory, which helps prevent long-term memory bloat in real deployments.
- Dry-run write planning: upper-layer personal agents can now ask the memory engine for a write/update/deduplicate recommendation before mutating long-term memory.
- Compact write/update handoff: `plan_memory_write`, `write_memory`, and `update_memory` now also return an `agent_handoff` bundle so an upper-layer personal agent can quickly see whether it can execute now, whether confirmation is needed, which memory/block targets are involved, and what the primary next operation should be.
- Lifecycle closure: the service now supports restore / supersede / merge flows and exposes richer memory-state hints inside recall-time `memory_context`.
- Compact lifecycle handoff: `forget_memory`, `get_memory_history`, `restore_memory`, `supersede_memory`, and `merge_memories` now also return an `agent_handoff` bundle so upper-layer agents can quickly see lifecycle state, target memories, the primary next operation, and whether confirmation is needed.
- Unified write planning: the service now classifies incoming content (`stable_identity`, `stable_preference`, `long_term_goal`, `hard_constraint`, `ephemeral_tool_state`, etc.) and returns a `block_plan` alongside `memory_resolution`.
- Unified agent decision protocol: `write-plan / write / recall / update / forget / block / history / restore / supersede / merge` now all return a consistent `decision_protocol` payload so upper-layer personal agents can consume one governance shape instead of per-endpoint heuristics.
- Consistency governance: agent-facing contracts now also return a `consistency_plan` with risk level, issues, and prioritized `recommended_operations` so upper-layer personal agents can handle duplicates, lifecycle conflicts, and low-confidence recall more safely.
- Active conflict detection and guardrails: write planning now scans for textual contradiction, lifecycle-state collisions, and ambiguous close matches, then returns explicit `execution_guardrails` instead of leaving the upper-layer agent to infer safety.
- Agent-facing recall now exposes a low-confidence fallback path when strict retrieval returns empty, so upper-layer agents can degrade gracefully instead of receiving a blank memory result.
- Agent-facing write/recall now accept agent context such as task goal, context summary, and working memory, and recall returns a `memory_context` bundle that upper-layer agents can consume directly.
- Compact recall handoff: recall now also returns an `agent_handoff` bundle so an upper-layer personal agent can quickly read whether it can answer now, whether it should confirm first, what response preview to use, and which memory ids / block labels to ground on.
- Safer recall consumption: recall now also returns `response_contract` and `response_guardrails`, so the upper-layer agent knows whether it may answer directly, must cite memory ids, or must ask the user for confirmation.
- Freshness-aware recall guardrails: recall now also returns a `freshness_guard`, helping the upper-layer agent avoid answering “now / recently / these days” questions from aged memory as if the current state were verified.
- User-comfort guidance: recall now also returns `user_experience_guidance`, helping the upper-layer agent keep confirmations brief, avoid exposing internal protocol details, and stay passive-feedback-first.
- Direct response planning: recall now also returns `agent_response_plan`, giving the upper-layer agent a grounded answer skeleton, confirmation prompt, and short-response plan instead of forcing it to reconstruct all reply behavior itself.
- Language-aware response planning: `agent_response_plan` now also exposes `response_language`, and Chinese recall queries no longer default to English-style answer openings or confirmation prompts.
- Agent-facing write/recall/reflect operations are now also logged as service-operation records, so later debugging and offline review can inspect how the upper-layer agent used the memory engine.
- Productization reports: storage health, integration-flow readiness, and training-protocol readiness are now inspectable through system-facing reports instead of being implicit.
- User-experience observability: the service now exposes a dedicated user-experience report so we can track confirmation pressure, fallback frequency, and passive-vs-explicit feedback reliance.
- User-experience friction classification: the UX report now also separates `protective_confirmation_count` from `friction_confirmation_count`, exposes `runtime_scope`, `readiness_basis`, and `thin_scope_adjustment`, and lets readiness distinguish calm-but-cautious operation from truly interruptive confirmation pressure.
- Recent calm-runtime uplift: when the latest recall behavior is repeatedly grounded, no-confirmation, and fallback-free, the UX report can now promote the top-level readiness from raw `acceptable` runtime scope to `comfortable` with `readiness_basis=recent_runtime_trend`.
- Low-confidence recall relaxation: recall now prefers a cautious grounded answer over a forced confirmation when one supported fact, visible core-memory support, low freshness risk, and a clear conflict profile already provide enough grounding for direct agent execution.
- Training signal classification: offline review exports and training reports now distinguish `feedback_labeled` from `protocol_labeled` samples, so upper layers can tell whether training readiness came from explicit judgment feedback, protocol-rich service traces, or both.
- Memory hygiene observability: the service now exposes a dedicated memory-hygiene report with stale / revised / inactive memory candidates plus prioritized maintenance actions.
- Release gate: the service now exposes a release-readiness report that combines storage health, integration coverage, training protocol maturity, and user-comfort signals into an internal-only / limited-pilot / market-pilot-ready recommendation.
- Readiness baseline fix surface: the service now also exposes a dedicated readiness-baseline report that maps each active blocker/warning to its source report, trigger values, recommended fix, next hardening phase, and repair order.
- Storage operability: the storage report now exposes migration, recovery, observability, consistency, readiness, and recommended-operation surfaces instead of only raw backend metadata.
- Storage productionization: the storage report now also exposes schema status, backup freshness, recovery confidence, and migration readiness so upper-layer systems can tell whether persistence is merely present or actually operationally trustworthy.
- Compact block / reflection handoff: `set_memory_block`, `delete_memory_block`, and `reflect_memory` now return `agent_handoff` bundles so an upper-layer agent can directly consume core-block and reflection decisions.
- Agent-facing readiness summary: the service now exposes `agent_readiness_summary`, a compact cross-surface report that summarizes storage, integration, training, UX, hygiene, and release readiness for upper-layer orchestration.
- Thin execution-policy input: `agent_readiness_summary` now also exposes `execution_policy` and a flatter `policy_input` view so an upper-layer agent can directly read `can_answer_now / can_write_now / should_confirm / resolution_flow` without stitching multiple reports together.
- Thinner direct execution surface: recall and readiness contracts now also expose a compact `execution_surface` bundle that co-locates `policy_input`, `execution_policy`, `agent_handoff`, and recall-time response guardrails/contracts so upper-layer agents can consume one stable object instead of stitching fields across the payload.
- Recall-time policy convergence: recall now also exposes its own `execution_policy` and flat `policy_input`, so upper-layer agents can reuse the same policy-style consumption pattern across per-request recall decisions and system-level readiness decisions.
- Storage delivery hardening: storage reports now also expose `policy_input`, `execution_policy`, `execution_surface`, `backup_inventory`, `operator_checklist`, and `deployment_guidance` so private-deployment operators can read storage readiness as a delivery checklist instead of reverse-engineering raw health metadata.
- SQLite primary-path repair: SQLite runtime initialization now repairs stale zero-byte sidecars, persists `memory_blocks` inside SQLite, bootstraps existing JSON state into SQLite when needed, and keeps native SQLite backup artifacts working even when delivery artifacts live under a non-ASCII workspace path.
- Storage primary-path hardening: storage reports now also distinguish `healthy_primary`, `degraded_fallback`, and `blocked` states, plus a dedicated `primary_storage` surface, so SQLite-as-primary delivery posture is modeled explicitly instead of being hidden behind generic backend metadata.
- Storage operator decision path: storage reports now also expose `operator_decision_path`, so acceptance can distinguish “accept”, “accept with follow-up”, and “block” without relying only on prose guidance.
- Delivery-pack storage decision visibility: delivery-pack Markdown now surfaces the storage acceptance decision directly, so the receiver can see `proceed / proceed_with_followup / block` without opening the raw JSON first.
- Degraded-fallback operator follow-up: storage reports now also expose `operator_acceptance_note` and `remediation_checklist`, so the receiver gets a standard handoff note plus concrete remediation steps instead of an abstract warning.
- Recovery drill evidence: storage reports and CLI/scripts now also surface the latest restore-drill result, including latest-healthy-backup candidate selection evidence, so recovery confidence can be backed by a real replay instead of backup existence alone.
- Recovery gate surface: delivery-pack and acceptance materials now also surface `last_restore_drill_at`, `last_restore_drill_status`, and `restore_confidence`, so recovery posture is visible without opening the raw storage JSON.
- Restore-drill freshness rule: EMOS now states when existing recovery evidence is still acceptable and when a restore drill must be rerun, instead of leaving that timing judgment implicit.
- Migration preflight surface: storage reports now also expose schema policy, preflight status, and rollback readiness, and operators can record a migration-preflight artifact before any upgrade step.
- Migration gate visibility: delivery-pack and storage reports now also surface the latest migration attempt plus rollback-availability evidence, so upgrade posture is reviewable from handoff materials.
- Migration operator decision rule: EMOS now states when an upgrade may execute now, when it must stay preflight-only, and when rollback evidence must be refreshed first.
- Migration handoff sequence: acceptance and handoff materials now tell the receiver which migration artifact and rollback artifact to inspect first, instead of only listing the fields.
- Backup artifacts now also expose verification metadata (`format`, `sha256`, verification status, restore steps) so backup generation is closer to a handoff-grade recovery surface than a bare file dump.
- Delivery pack now also embeds the current `storage_report` and points to a dedicated operator runbook at `docs/storage_delivery_runbook.md`, so storage recovery guidance ships with the delivery artifact instead of living only in API responses.
- Retrieval control-plane clarity: retrieval backend reports now expose a structured `control_plane` with explicit `recall / fusion / rerank` components, plus explainability signals and contract-level support flags for upper-layer agents.
- Retrieval task-fit guidance: backend reports now also expose `control_plane_status`, `task_fit`, `agent_recommendations`, and `anti_patterns`, so upper-layer agents can tell whether the current backend is merely available or actually suitable for conservative grounded recall.
- Retrieval runtime advice: backend reports now also expose `runtime_advice`, including backend-switch recommendations, candidate-pool sufficiency, and strong-answer policy hints so runtime retrieval guidance looks more like direct agent policy input than engineering commentary.
- Integration-flow realism: integration reports now validate scenario-level loops (`chat_loop`, `task_loop`, `lifecycle_loop`, `core_memory_loop`) instead of only exposing raw operation counters.
- Consistency-loop validation: integration reports now also validate `consistency_loop`, so personal-agent readiness includes “history + consistency logging + lifecycle resolution” rather than treating conflict handling as an implicit side effect.
- Integration execution guidance: integration reports now also expose `execution_surface`, `recommended_call_flows`, and `anti_patterns`, so upper-layer agents can see how to call EMOS correctly instead of inferring the flow from raw endpoints.
- Conflict-aware recall consumption: recall now returns a structured `conflict_profile` so upper-layer agents can distinguish inactive memory states, disputed versions, ambiguity, and freshness risk instead of reacting to a single boolean flag.
- Recall protocol convergence: top-level recall `decision_protocol` now aligns with the nested `memory_context.decision_protocol` recommended action, reducing execution ambiguity for upper-layer agents.
- Consistency audit observability: the service now exposes a dedicated `consistency_audit` report with revised-fact, old-fact, and disputed-watchlist candidates, plus prioritized maintenance operations that tie directly into lifecycle actions.
- Release/readiness consistency gating: release readiness and agent readiness now include consistency risk as a first-class surface instead of treating lifecycle drift as only a memory-hygiene side effect.
- Consistency auto-governance foundations: `consistency_plan` now classifies revised/disputed/stale/lifecycle consistency types, exposes `governance_mode` plus `action_buckets`, and gives upper-layer agents a thinner auto-safe vs confirm-required vs manual-review split.
- Consistency auto-governance tightening: low-risk related write updates can now resolve as `auto_update_existing_memory`, and stale-only recall paths now prefer confirmation-first handling without forcing manual history review.
- Consistency maintenance unification: lifecycle contracts and the consistency audit report now both expose a shared `consistency_maintenance` surface so upper-layer systems can consume the same `auto_safe / confirm_required / manual_review` template across per-memory actions and report-level review.
- Consistency maintenance readiness wiring: `consistency_audit` now also exposes `maintenance_jobs` plus operator/agent action buckets, and both `release_readiness` and `agent_readiness_summary` now quote those surfaces directly instead of only summarizing consistency as a single readiness label.
- Lifecycle execution-surface convergence: `update / forget / restore / supersede / merge / history` now also expose `policy_input`, `execution_policy`, and `execution_surface`, so upper-layer agents can consume lifecycle actions through the same thin policy-style object already used by recall, readiness, and storage.
- Readiness-to-lifecycle convergence: `release_readiness` and `agent_readiness_summary` now also surface consistency-driven `lifecycle_execution_paths` plus a `recommended_lifecycle_execution`, so readiness can point directly at a unified lifecycle execution path instead of only naming a risk bucket.
- Shared ops/audit signal surface: `consistency_audit`, `release_readiness`, and `agent_readiness_summary` now also expose `ops_metric_surface` and `audit_signal_surface`, so operator and agent views share the same queue depth, lifecycle-path, and restore-drill signals for the same maintenance actions.
- Shared failure taxonomy and review order: those same observability surfaces now also expose `error_taxonomy` and `operator_review_order`, so maintenance work is grouped into stable failure classes and a receiver-facing inspection sequence instead of raw counters alone.
- Formal operator observability guide: handoff and acceptance materials now point to `docs/operator_observability_guide.md` as the default wording source for shared observability review.
- Delivery-pack observability visibility: delivery-pack Markdown now also surfaces the shared observability review anchors directly, so a receiver can see `operator_review_order`, `error_taxonomy`, shared ops metrics, and the recommended lifecycle execution path without opening raw JSON first.
- Demo-summary observability visibility: the delivery demo summary now also points reviewers directly to the delivery-pack shared observability sections and the operator observability guide, so the demo path and handoff path use the same review order.
- Demo-summary/manifest convergence: the delivery demo summary and `final_delivery_manifest` now share the same observability-first review wording, and `delivery_pack_output.json` now exposes the manifest path directly in its artifact map.
- Handoff-example observability convergence: `handoff_example_flows.md` now also teaches receiver-facing storage and demo review through the same observability-first order used by the delivery pack, demo summary, and final manifest.
- Long-horizon validation expansion: EMOS now runs a multi-profile long-horizon workload with separate persona scenarios, task-switch recall checks, conflict probes, and a formal benchmark-evidence boundary so scenario stability evidence is no longer mixed with benchmark results.
- Long-horizon drift summary: EMOS now also aggregates recent long-horizon runs into a multi-run summary with persona drift deltas and review posture, so pilot-facing stability review can compare baseline vs latest behavior without touching benchmark metrics.
- Long-horizon handoff closure: handoff, acceptance, and final manifest materials now explicitly include long-horizon validation and multi-run drift review as part of the delivery path.

## Recommended Commands

```powershell
.\scripts\run_smoke.ps1
.\\scripts\\run_integration_flows.ps1
.\\scripts\\run_delivery_demo.ps1
.\\scripts\\run_storage_restore_drill.ps1
.\\scripts\\run_storage_migration_preflight.ps1
.\\scripts\\run_long_horizon_validation.ps1
.\\scripts\\run_long_horizon_summary.ps1
.\scripts\run_benchmarks.ps1
.\scripts\run_tests.ps1
.\scripts\run_api.ps1
.\\scripts\\run_delivery_pack.ps1
.\scripts\run_official_locomo.ps1
.\scripts\run_official_locomo.ps1 -MaxSamples 100
.\scripts\run_official_locomo_midscale.ps1 -MaxSamples 400
python .\scripts\export_offline_review.py --limit 200
```

## Default Delivery Path

- Preferred deployment mode: local machine or private server
- Preferred retrieval backend: `embedding_rerank`
- Preferred runtime entrypoint: `.\scripts\run_api.ps1`
- Default API bind address:
  - host: `127.0.0.1`
  - port: `8000`
- Optional API bind overrides:
  - `MEMORY_SYSTEM_API_HOST`
  - `MEMORY_SYSTEM_API_PORT`
- Default SQLite runtime path behavior:
  - if the configured SQLite path is ASCII-safe, use it directly
  - otherwise, use an ASCII-safe local runtime path under `%TEMP%\EMOS\runtime`
  - operators can still override the path explicitly with `MEMORY_SYSTEM_SQLITE_FILE`
- Preferred smoke verification: `.\scripts\run_smoke.ps1`
- Preferred integration-evidence run: `.\scripts\run_integration_flows.ps1`
- Preferred integration-readiness interpretation:
  - read `integration_flow.runtime_scope` to see the narrow local observation window
  - read top-level `integration_flow.readiness` and `integration_flow.evidence_bridge` to see whether recent validated integration evidence has been applied
- Preferred stable regression set:
  - `python -B -m pytest tests/test_memory_service_contract.py tests/test_api.py tests/test_feedback_maturity.py tests/test_passive_feedback.py tests/test_retrieval_pipeline.py tests/test_storage_report.py -q`
- Benchmark and official LoCoMo assets are intentionally retained in this repository because they are still required for later paper writing and reruns.

## Delivery Review Order

- `README.md`: package position, runtime path, and handoff surfaces
- [docs/api_reference.md](docs/api_reference.md): integration-facing contract details
- [docs/handoff_manual.md](docs/handoff_manual.md): operator and receiver handoff path
- [docs/handoff_example_flows.md](docs/handoff_example_flows.md): stable example flows for receiver review
- [docs/agent_integration_examples.md](docs/agent_integration_examples.md): upper-layer agent examples for write, recall, lifecycle, and storage review
- [docs/agent_api_quickstart.md](docs/agent_api_quickstart.md): quickest API onboarding path for an external agent team
- [docs/agent_local_deployment_guide.md](docs/agent_local_deployment_guide.md): step-by-step local deployment guide for an external agent team
- [docs/agent_api_endpoint_catalog.md](docs/agent_api_endpoint_catalog.md): endpoint-by-endpoint catalog so receivers do not need to search the codebase
- [docs/acceptance_checklist.md](docs/acceptance_checklist.md): release-style acceptance checks
- [docs/acceptance_walkthrough.md](docs/acceptance_walkthrough.md): reviewer sequence for runtime, storage, and demo acceptance
- [docs/final_delivery_manifest.md](docs/final_delivery_manifest.md): final package map, validation snapshot, and receiver decision rule
- [docs/acceptance_evidence_bundle.md](docs/acceptance_evidence_bundle.md): formal acceptance evidence bundle for receiver review
- [docs/emos_v1_1_known_limitations.md](docs/emos_v1_1_known_limitations.md): explicit limitation and follow-up note
- [docs/emos_v1_1_release_notes.md](docs/emos_v1_1_release_notes.md): v1.1 release summary
- [docs/emos_v1_1_packaging_checklist.md](docs/emos_v1_1_packaging_checklist.md): final bundle-composition checklist
- [docs/emos_v1_1_package_closeout.md](docs/emos_v1_1_package_closeout.md): final package closeout note
- [docs/storage_delivery_runbook.md](docs/storage_delivery_runbook.md): backup / recovery / storage operator runbook
- [docs/storage_migration_runbook.md](docs/storage_migration_runbook.md): migration / upgrade / rollback operator runbook
- [docs/operator_observability_guide.md](docs/operator_observability_guide.md): shared observability wording for operators and reviewers
- [docs/emos_v1_1_hardening_roadmap.md](docs/emos_v1_1_hardening_roadmap.md): post-v1 delivery hardening roadmap

## Delivery Acceptance Path

- Start the service with `.\scripts\run_api.ps1`
- Verify runtime health with `.\scripts\run_smoke.ps1`
- Generate integration evidence with `.\scripts\run_integration_flows.ps1`
- Generate the delivery package with `.\scripts\run_delivery_pack.ps1`
- Re-run the full demo/handoff chain with `.\scripts\run_delivery_demo.ps1`
- Review:
  - `delivery_pack.storage_report`
  - `storage_report.operator_checklist`
  - `storage_backup.verification`
  - `agent_readiness_summary.execution_surface`
  - `system_report.long_horizon_validation_summary`
  - `system_report.long_horizon_multi_run_summary`
  - `system_report.evidence_surfaces`
  - `docs/final_delivery_manifest.md`

## Direct Entrypoints

```bash
python final.py --once "我最近考试压力有点大。"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 process --text "我最近考试压力有点大。"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 write-memory --text "我一直很喜欢五月天。" --task-type chat --memory-scope auto --task-goal "build preference profile" --context-summary "agent is collecting stable user tastes" --working-memory "user asked about favorite bands"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 plan-write-memory --text "我一直很喜欢五月天。" --task-type chat --memory-scope auto
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 recall-memory --query-text "我喜欢什么乐队？" --top-k 3 --include-profile --task-goal "answer from memory" --context-summary "need grounded answer" --working-memory "cite supporting memory"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 reflect-memory
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 update-memory --memory-id MEMORY_ID --text "我一直很喜欢五月天和Coldplay。" --task-goal "refresh durable preference"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 forget-memory --memory-id MEMORY_ID --reason "outdated preference"
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 set-memory-block --label persona_anchor --value "User cares about music and emotionally meaningful live experiences."
python -m src.memory_system.cli_app --user-id demo memory-blocks
python -m src.memory_system.cli_app --user-id demo --session-id demo-s1 memory-history --memory-id MEMORY_ID
python -m src.memory_system.cli_app --user-id demo snapshot --limit 10
python -m src.memory_system.cli_app --user-id demo report --limit 10
python -m src.memory_system.cli_app --user-id demo export --limit 10
python -m src.memory_system.cli_app --user-id demo feedback-report --limit 10
python -m src.memory_system.cli_app --user-id demo export-offline-review --limit 100
python -m src.memory_system.cli_app system-report
python -m src.memory_system.cli_app storage-report
python -m src.memory_system.cli_app integration-flow-report --user-id demo --integration-session-id demo-s1 --limit 50
python -m src.memory_system.cli_app training-protocol-report --user-id demo --limit 50
python -m src.memory_system.cli_app user-experience-report --user-id demo --experience-session-id demo-s1 --limit 50
python -m src.memory_system.cli_app consistency-audit-report --user-id demo --limit 50
python -m src.memory_system.cli_app memory-hygiene-report --user-id demo --limit 50
python -m src.memory_system.cli_app release-readiness-report --user-id demo --release-session-id demo-s1 --limit 50
python -m src.memory_system.cli_app agent-readiness-report --user-id demo --agent-session-id demo-s1 --limit 50
python -m src.memory_system.cli_app long-horizon-validation --user-id demo --session-id demo-long --limit 50
python -m src.memory_system.cli_app storage-backup
python -m src.memory_system.cli_app delivery-pack
python -m src.memory_system.cli_app retrieval-backends
python -m src.memory_system.cli_app set-retrieval-backend --backend-name lexical
python -m src.memory_system.benchmarks.runner
python -m src.memory_system.benchmarks.runner --benchmark-root D:\official_benchmarks
python -m src.memory_system.benchmarks.runner --benchmark-root data\benchmarks\official --benchmark locomo_official_full --backend embedding_rerank --skip-comparison --max-samples 50
python -m src.memory_system.benchmarks.runner --benchmark-root data\benchmarks\official --benchmark locomo_official_full --skip-comparison --max-samples 150 --no-consolidation
python -m src.memory_system.api.server
```

For upper-layer agents, the preferred thin recall consumption path is now:

- `payload.execution_surface.policy_input`
- `payload.execution_surface.execution_policy`
- `payload.execution_surface.agent_handoff`
- `payload.execution_surface.response_contract`
- `payload.execution_surface.response_guardrails`

For system-level orchestration, the preferred readiness consumption path is now:

- `execution_surface.policy_input`
- `execution_surface.execution_policy`
- `execution_surface.agent_handoff`

For lifecycle actions, the preferred thin consumption path is now:

- `payload.execution_surface.policy_input`
- `payload.execution_surface.execution_policy`
- `payload.execution_surface.agent_handoff`
- `payload.consistency_maintenance`

For storage operations and delivery handoff, the preferred operator path is now:

- `storage_report.execution_surface`
- `storage_report.operator_checklist`
- `storage_report.deployment_guidance`
- `storage_backup.verification`
- `delivery_pack.storage_report`
- [docs/storage_delivery_runbook.md](docs/storage_delivery_runbook.md)

## Config Files

- `configs/semantic_aliases.json`
- `configs/stop_tokens.json`
- `configs/retrieval_settings.json`

These can also be overridden with:

- `MEMORY_SYSTEM_SEMANTIC_ALIASES_FILE`
- `MEMORY_SYSTEM_STOP_TOKENS_FILE`
- `MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE`
- `MEMORY_SYSTEM_MEMORY_FILE`
- `MEMORY_SYSTEM_SQLITE_FILE`
- `MEMORY_SYSTEM_FEEDBACK_STORE_FILE`
- `MEMORY_SYSTEM_INTERACTION_LOG_FILE`
- `MEMORY_SYSTEM_OFFLINE_EVAL_DIR`
- `MEMORY_SYSTEM_STORAGE_BACKEND`
- `MEMORY_SYSTEM_BENCHMARK_EXTRA_ROOTS`

## Validation Snapshot

- `run_tests.ps1`: `37 passed`
- `run_benchmarks.ps1`: `32` formalized samples across local sets and official-format adapter fixtures
- `run_official_locomo.ps1`: now defaults to a scoped `50`-sample official LoCoMo run so official evaluation stays safe-by-default
- Current benchmark snapshot on the larger local set: `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000`, `pass@TargetRank=1.000`
- Current official LoCoMo snapshot on `50` samples: `hit@1=0.980`, `hit@3=0.980`, `MRR=0.980`, `pass@TargetRank=0.980`
- Current official LoCoMo `qa-category-2` snapshot on `50` samples: `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000`
- Current official LoCoMo `qa-category-3` snapshot on `50` samples: `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000`
- Current `150`-sample official LoCoMo stage-gate run: `hit@1=0.860`, `hit@3=0.953`, `MRR=0.900`
- Current `250`-sample official LoCoMo stage-gate run: `hit@1=0.796`, `hit@3=0.912`, `MRR=0.847`
- Current `320`-sample official LoCoMo stage-gate run: `hit@1=0.800`, `hit@3=0.931`, `MRR=0.857`
- Current `400`-sample official LoCoMo stage-gate run: `hit@1=0.828`, `hit@3=0.958`, `MRR=0.886`
- Current `400`-sample official LoCoMo `qa-category-4`: `hit@1=0.870`, `hit@3=0.965`, `MRR=0.913`
- Backend comparison: `lexical`, `semantic`, `hybrid`, `embedding_rerank`
- Current recommended backend: `embedding_rerank`

## Delivery Docs

- `docs/development_log.md`
- `docs/delivery_sprint_plan_20260425_20260502.md`
- `docs/handoff_manual.md`
- `docs/handoff_example_flows.md`
- `docs/acceptance_checklist.md`
- `docs/acceptance_walkthrough.md`
- `docs/final_delivery_manifest.md`
- `docs/api_reference.md`
- `docs/benchmark_protocol.md`
- `docs/architecture.md`
