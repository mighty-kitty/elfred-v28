from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .models import utc_now
from .utils.io import write_json


def generate_delivery_pack(
    config: AppConfig,
    system_report: dict[str, object],
    storage_report: dict[str, object] | None = None,
    storage_backup: dict[str, object] | None = None,
) -> dict[str, object]:
    generated_at = utc_now()
    timestamp = generated_at.replace(":", "").replace("-", "").replace(".", "")
    delivery_dir = config.paths.delivery_dir
    delivery_dir.mkdir(parents=True, exist_ok=True)

    json_path = delivery_dir / f"delivery_pack_{timestamp}.json"
    markdown_path = delivery_dir / f"delivery_pack_{timestamp}.md"

    payload = {
        "generated_at": generated_at,
        "project": "AI Memory System",
        "system_report": system_report,
        "storage_report": storage_report,
        "artifacts": {
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
            "long_horizon_directory": str(config.paths.delivery_dir / "long_horizon"),
            "benchmark_results": str(config.paths.logs_dir / "benchmark_results.json"),
            "benchmark_comparison": str(config.paths.logs_dir / "benchmark_comparison.json"),
            "memory_log": str(config.paths.logs_dir / "memory_system.log"),
            "storage_backup": storage_backup["path"] if storage_backup else None,
            "storage_runbook": str(config.paths.root_dir / "docs" / "storage_delivery_runbook.md"),
            "operator_observability_guide": str(config.paths.root_dir / "docs" / "operator_observability_guide.md"),
            "final_delivery_manifest": str(config.paths.root_dir / "docs" / "final_delivery_manifest.md"),
            "acceptance_evidence_bundle": str(config.paths.root_dir / "docs" / "acceptance_evidence_bundle.md"),
            "known_limitations": str(config.paths.root_dir / "docs" / "emos_v1_1_known_limitations.md"),
            "release_notes": str(config.paths.root_dir / "docs" / "emos_v1_1_release_notes.md"),
            "packaging_checklist": str(config.paths.root_dir / "docs" / "emos_v1_1_packaging_checklist.md"),
            "package_closeout": str(config.paths.root_dir / "docs" / "emos_v1_1_package_closeout.md"),
        },
    }

    write_json(json_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, object]) -> str:
    system_report = payload["system_report"]
    storage_report = payload.get("storage_report") or {}
    release_readiness = system_report.get("release_readiness_report", {}) or {}
    agent_readiness = system_report.get("agent_readiness_summary", {}) or {}
    benchmark_summary = system_report.get("benchmark_summary", {})
    comparison_summary = system_report.get("benchmark_comparison", {})
    storage_policy = storage_report.get("policy_input", {})
    storage_checklist = storage_report.get("operator_checklist", {})
    storage_decision = storage_report.get("operator_decision_path", {})
    storage_note = storage_report.get("operator_acceptance_note", {})
    remediation_checklist = storage_report.get("remediation_checklist", {})
    storage_guidance = storage_report.get("deployment_guidance", {})
    recovery = storage_report.get("recovery", {}) or {}
    restore_drill_freshness = recovery.get("restore_drill_freshness", {}) or {}
    migration = storage_report.get("migration", {}) or {}
    migration_preflight = migration.get("preflight", {}) or {}
    migration_rollback = migration.get("rollback", {}) or {}
    migration_latest_attempt = migration.get("latest_attempt", {}) or {}
    migration_acceptance = migration.get("migration_acceptance", {}) or {}
    observability_metrics = agent_readiness.get("ops_metric_surface", {}) or {}
    observability_audit = agent_readiness.get("audit_signal_surface", {}) or {}
    observability_taxonomy = release_readiness.get("error_taxonomy", {}) or {}
    observability_review_order = release_readiness.get("operator_review_order", {}) or {}
    recommended_lifecycle_execution = agent_readiness.get("recommended_lifecycle_execution", {}) or {}
    storage_action_surface = storage_report.get("action_surface", {}) or {}
    readiness_action_surface = agent_readiness.get("action_surface", {}) or {}
    long_horizon_summary = system_report.get("long_horizon_validation_summary", {}) or {}
    long_horizon_multi_run = system_report.get("long_horizon_multi_run_summary", {}) or {}
    phase_e_stability = system_report.get("phase_e_stability", {}) or {}
    long_horizon_phase_e = long_horizon_summary.get("phase_e_stability", {}) or {}
    multi_run_phase_e = long_horizon_multi_run.get("phase_e_stability", {}) or {}
    evidence_surfaces = system_report.get("evidence_surfaces", {}) or {}
    evidence_boundary = long_horizon_summary.get("benchmark_boundary", {}) or {}
    storage_backup = payload["artifacts"].get("storage_backup")
    acceptance_evidence_bundle = payload["artifacts"].get("acceptance_evidence_bundle")
    known_limitations = payload["artifacts"].get("known_limitations")
    release_notes = payload["artifacts"].get("release_notes")
    packaging_checklist = payload["artifacts"].get("packaging_checklist")
    package_closeout = payload["artifacts"].get("package_closeout")
    lines = [
        "# Delivery Pack",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Project: {payload['project']}",
        f"- Active retrieval backend: {system_report.get('retrieval_backend')}",
        f"- Active storage backend: {system_report.get('storage_backend')}",
        f"- User count: {system_report.get('user_count', 0)}",
        f"- Memory count: {system_report.get('memory_count', 0)}",
        f"- Storage backup: {storage_backup}",
        "",
        "## Storage Delivery Status",
        f"- Resolved backend: {storage_report.get('resolved_backend', 'unknown')}",
        f"- Preferred primary backend: {storage_report.get('preferred_primary_backend', 'unknown')}",
        f"- Primary storage mode: {storage_report.get('primary_mode_status', 'unknown')}",
        f"- Storage readiness: {storage_report.get('readiness', 'unknown')}",
        f"- Persistence confidence: {storage_report.get('persistence_confidence', 'unknown')}",
        f"- Storage resolution flow: {storage_policy.get('resolution_flow', 'unknown')}",
        f"- Delivery decision: {storage_decision.get('delivery_decision', 'unknown')}",
        f"- Operator action: {storage_decision.get('operator_action', 'unknown')}",
        f"- Checklist pass/warn/fail: {storage_checklist.get('pass_count', 0)}/{storage_checklist.get('warn_count', 0)}/{storage_checklist.get('fail_count', 0)}",
        f"- Restore confidence: {recovery.get('restore_confidence', recovery.get('recovery_confidence', 'unknown'))}",
        f"- Last restore drill at: {recovery.get('last_restore_drill_at', 'unknown')}",
        f"- Last restore drill status: {recovery.get('last_restore_drill_status', 'unknown')}",
        f"- Last restore drill age (hours): {recovery.get('last_restore_drill_age_hours', 'unknown')}",
        "",
        "## Unified Consumption Rule",
        "- Read `execution_surface.policy_input` first.",
        "- Read `execution_surface.action_surface` second.",
        "- Read `execution_surface.agent_handoff` third.",
        "- If `execution_surface` is absent, fall back to top-level `action_surface` before raw report fields.",
        "",
        "## Storage Action Surface",
        f"- Surface version: {storage_action_surface.get('surface_version', 'unknown')}",
        f"- Recommended action: {storage_action_surface.get('recommended_action', 'unknown')}",
        f"- Next action: {storage_action_surface.get('next_action', 'unknown')}",
        f"- Handoff mode: {storage_action_surface.get('handoff_mode', 'unknown')}",
        f"- Action status: {storage_action_surface.get('action_status', 'unknown')}",
        "",
        "## Storage Acceptance Decision",
        f"- Acceptance rule: {storage_decision.get('acceptance_rule', 'unknown')}",
        f"- Primary storage mode: {storage_decision.get('primary_storage_mode', 'unknown')}",
        f"- Acceptance note: {storage_note.get('summary', 'unknown')}",
        "",
        "## Storage Recovery Gate",
        f"- Recovery gate status: {recovery.get('last_restore_drill_status', 'unknown')}",
        f"- Recovery confidence: {recovery.get('restore_confidence', recovery.get('recovery_confidence', 'unknown'))}",
        f"- Recovery drill recommended: {recovery.get('recovery_drill_recommended', 'unknown')}",
        f"- Restore drill freshness: {restore_drill_freshness.get('status', 'unknown')}",
        f"- Rerun required: {restore_drill_freshness.get('rerun_required', 'unknown')}",
        f"- Rerun rule: {restore_drill_freshness.get('rerun_rule', 'unknown')}",
            f"- Evidence acceptable when: {restore_drill_freshness.get('evidence_acceptable_when', 'unknown')}",
            f"- Recovery gate summary: {restore_drill_freshness.get('acceptance_summary', 'unknown')}",
            "",
        "## Phase E Stability",
        f"- Surface version: {phase_e_stability.get('surface_version', 'unknown')}",
        f"- Stability posture: {phase_e_stability.get('stability_posture', 'unknown')}",
        f"- Clean Phase E: {phase_e_stability.get('clean_phase_e', 'unknown')}",
        f"- Release readiness: {phase_e_stability.get('release_readiness', 'unknown')}",
        f"- Consistency readiness: {phase_e_stability.get('consistency_readiness', 'unknown')}",
        f"- Memory hygiene readiness: {phase_e_stability.get('memory_hygiene_readiness', 'unknown')}",
        f"- Manual-review queue depth: {phase_e_stability.get('manual_review_queue_depth', 'unknown')}",
        f"- Confirm-required queue depth: {phase_e_stability.get('confirm_required_queue_depth', 'unknown')}",
        f"- Phase E summary: {phase_e_stability.get('summary', 'unknown')}",
        "",
        "## Storage Migration Gate",
        f"- Migration policy: {migration.get('policy_version', 'unknown')}",
        f"- Migration preflight status: {migration_preflight.get('status', 'unknown')}",
        f"- Latest migration attempt: {migration_latest_attempt.get('status', 'unknown')}",
        f"- Latest migration attempt at: {migration_latest_attempt.get('attempted_at', 'unknown')}",
        f"- Latest migration artifact: {migration_latest_attempt.get('artifact_path', 'unknown')}",
        f"- Rollback ready: {migration_rollback.get('rollback_ready', 'unknown')}",
        f"- Rollback artifact path: {migration_rollback.get('rollback_artifact_path', 'unknown')}",
        f"- Rollback artifact recent: {migration_rollback.get('rollback_artifact_recent', 'unknown')}",
        f"- Migration decision: {migration_acceptance.get('decision', 'unknown')}",
        f"- Migration summary: {migration_acceptance.get('summary', 'unknown')}",
        f"- Execute upgrade when: {migration_acceptance.get('execute_upgrade_when', 'unknown')}",
        f"- Preflight-only when: {migration_acceptance.get('preflight_only_when', 'unknown')}",
        f"- Refresh rollback evidence when: {migration_acceptance.get('refresh_rollback_evidence_when', 'unknown')}",
        f"- Block when: {migration_acceptance.get('block_when', 'unknown')}",
        "",
        "## Shared Observability Review",
        f"- Ops metric surface: {observability_metrics.get('surface_version', 'unknown')}",
        f"- Audit signal surface: {observability_audit.get('surface_version', 'unknown')}",
        f"- Error taxonomy: {observability_taxonomy.get('surface_version', 'unknown')}",
        f"- Operator review order: {observability_review_order.get('surface_version', 'unknown')}",
        f"- Recommended lifecycle operation: {observability_metrics.get('recommended_lifecycle_operation', 'unknown')}",
        "",
        "## Operator Review Order",
    ]

    for item in observability_review_order.get("steps", [])[:5]:
        lines.append(
            f"- Step {item.get('step')}: {item.get('check')} -> {item.get('recommended_action')} [{item.get('status')}]"
        )

    lines.extend(
        [
            "",
            "## Shared Error Taxonomy",
        ]
    )

    for item in observability_taxonomy.get("items", [])[:5]:
        lines.append(
            f"- {item.get('error_code')}: {item.get('status')} / {item.get('severity')} ({item.get('recommended_flow')})"
        )

    lines.extend(
        [
            "",
            "## Shared Ops Metrics",
            f"- Manual-review queue depth: {observability_metrics.get('manual_review_queue_depth', 'unknown')}",
            f"- Confirm-required queue depth: {observability_metrics.get('confirm_required_queue_depth', 'unknown')}",
            f"- Auto-safe queue depth: {observability_metrics.get('auto_safe_queue_depth', 'unknown')}",
            f"- Enabled maintenance jobs: {observability_metrics.get('enabled_maintenance_job_count', 'unknown')}",
            f"- Lifecycle execution path count: {observability_metrics.get('lifecycle_execution_path_count', 'unknown')}",
            "",
            "## Recommended Lifecycle Execution",
            f"- Surface version: {recommended_lifecycle_execution.get('surface_version', 'unknown')}",
            f"- Operation: {recommended_lifecycle_execution.get('operation', 'unknown')}",
            f"- Recommended operation: {recommended_lifecycle_execution.get('agent_handoff', {}).get('recommended_operation', 'unknown') if isinstance(recommended_lifecycle_execution.get('agent_handoff'), dict) else 'unknown'}",
            "",
            "## Agent Readiness Action Surface",
            f"- Surface version: {readiness_action_surface.get('surface_version', 'unknown')}",
            f"- Recommended action: {readiness_action_surface.get('recommended_action', 'unknown')}",
            f"- Next action: {readiness_action_surface.get('next_action', 'unknown')}",
            f"- Handoff mode: {readiness_action_surface.get('handoff_mode', 'unknown')}",
            f"- Primary operation: {readiness_action_surface.get('primary_operation', 'unknown')}",
            "",
        "## Storage Recovery Checklist",
        ]
    )

    for item in storage_checklist.get("items", [])[:6]:
        lines.append(
            f"- {item.get('item')}: {item.get('status')} ({item.get('reason')})"
        )

    if storage_decision.get("next_checks"):
        lines.extend(
            [
                "",
                "## Storage Decision Checks",
            ]
        )
        for item in storage_decision.get("next_checks", []):
            lines.append(f"- {item}")

    if remediation_checklist.get("items"):
        lines.extend(
            [
                "",
                "## Storage Remediation Checklist",
            ]
        )
        for item in remediation_checklist.get("items", []):
            lines.append(f"- {item.get('status')}: {item.get('step')}")

    lines.extend(
        [
            "",
            "## Restore Steps",
        ]
    )

    for step in storage_guidance.get("restore_steps", []):
        lines.append(f"- {step}")

    lines.extend(
        [
            "",
            "## Long-Horizon Validation Summary",
            f"- Status: {long_horizon_summary.get('status', 'unknown')}",
            f"- Evidence family: {long_horizon_summary.get('evidence_family', 'unknown')}",
            f"- Latest artifact path: {long_horizon_summary.get('latest_artifact_path', 'unknown')}",
            f"- Profile count: {long_horizon_summary.get('profile_count', 'unknown')}",
            f"- Recall stability rate: {long_horizon_summary.get('metrics', {}).get('recall_stability_rate', 'unknown')}",
            f"- Lifecycle resolution rate: {long_horizon_summary.get('metrics', {}).get('lifecycle_resolution_rate', 'unknown')}",
            f"- Task-switch stability rate: {long_horizon_summary.get('metrics', {}).get('task_switch_stability_rate', 'unknown')}",
            f"- Conflict detection rate: {long_horizon_summary.get('metrics', {}).get('conflict_detection_rate', 'unknown')}",
            f"- Long-horizon Phase E posture: {long_horizon_phase_e.get('stability_posture', 'unknown')}",
            f"- Long-horizon Phase E summary: {long_horizon_phase_e.get('summary', 'unknown')}",
            "",
            "## Long-Horizon Multi-Run Summary",
            f"- Status: {long_horizon_multi_run.get('status', 'unknown')}",
            f"- Run count: {long_horizon_multi_run.get('run_count', 'unknown')}",
            f"- Review posture: {long_horizon_multi_run.get('review_posture', 'unknown')}",
            f"- Latest recall stability: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('recall_stability_rate', {}) or {}).get('latest', 'unknown')}",
            f"- Recall delta from baseline: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('recall_stability_rate', {}) or {}).get('delta_from_baseline', 'unknown')}",
            f"- Latest task-switch stability: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('task_switch_stability_rate', {}) or {}).get('latest', 'unknown')}",
            f"- Task-switch delta from baseline: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('task_switch_stability_rate', {}) or {}).get('delta_from_baseline', 'unknown')}",
            f"- Latest conflict detection: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('conflict_detection_rate', {}) or {}).get('latest', 'unknown')}",
            f"- Conflict-detection delta from baseline: {(long_horizon_multi_run.get('aggregate_metrics', {}).get('conflict_detection_rate', {}) or {}).get('delta_from_baseline', 'unknown')}",
            f"- Stable Phase E runs: {multi_run_phase_e.get('stable_run_count', 'unknown')}",
            f"- Watch Phase E runs: {multi_run_phase_e.get('watch_run_count', 'unknown')}",
            f"- Investigate Phase E runs: {multi_run_phase_e.get('investigate_run_count', 'unknown')}",
            f"- Latest Phase E summary: {multi_run_phase_e.get('latest_summary', 'unknown')}",
            "",
            "## Acceptance Evidence Bundle",
            f"- Acceptance evidence path: {acceptance_evidence_bundle}",
            "- Bundle review should cover runtime, integration, storage/recovery, migration/rollback, long-horizon, delivery-pack, and stable regression evidence together.",
            "",
            "## Final Bundle Composition",
            f"- Packaging checklist path: {packaging_checklist}",
            f"- Package closeout path: {package_closeout}",
            "- Final bundle composition should include documentation, artifacts, and validation evidence together.",
            "",
            "## Known Limitations",
            f"- Known limitations path: {known_limitations}",
            "- Current release posture remains local/private-deployment first and limited-pilot oriented.",
            "- SQLite promotion may still depend on the target environment.",
            "- Consistency resolution remains guarded instead of fully auto-cleared.",
            "",
            "## Release Notes",
            f"- Release notes path: {release_notes}",
            "- This release emphasizes hardening, delivery posture, and upper-layer integration clarity over broad new feature expansion.",
            "",
            "## Evidence Boundary",
            f"- Evidence surfaces: {evidence_surfaces.get('contract_version', 'unknown')}",
            f"- Separation rule: {evidence_surfaces.get('separation_rule', evidence_boundary.get('separation_rule', 'unknown'))}",
            f"- Long-horizon review path: {(evidence_surfaces.get('long_horizon_evidence', {}) or {}).get('review_path', 'unknown')}",
            f"- Benchmark review path: {(evidence_surfaces.get('benchmark_evidence', {}) or {}).get('review_path', 'unknown')}",
            "",
        "## Benchmark Summary",
        f"- Total samples: {benchmark_summary.get('total', 0)}",
        f"- Hit@1: {benchmark_summary.get('hit_at_1', 0.0):.3f}",
        f"- Hit@3: {benchmark_summary.get('hit_at_3', 0.0):.3f}",
        f"- MRR: {benchmark_summary.get('mrr', 0.0):.3f}",
        f"- Pass@TargetRank: {benchmark_summary.get('pass_at_target_rank', 0.0):.3f}",
        "",
        "## Backend Recommendation",
        f"- Recommended backend: {comparison_summary.get('recommended_backend', 'unknown')}",
        "",
        "## Artifact Paths",
        ]
    )

    for name, path_value in payload["artifacts"].items():
        lines.append(f"- {name}: {path_value}")

    lines.extend(
        [
            "",
            "## Persona Drift Summary",
        ]
    )
    profile_summaries = long_horizon_multi_run.get("profile_summaries") or []
    if profile_summaries:
        for item in profile_summaries[:5]:
            drift = item.get("drift", {}) or {}
            lines.append(
                f"- {item.get('profile_name')}: recall_delta={drift.get('recall_stability_delta', 'unknown')}, task_switch_delta={drift.get('task_switch_stability_delta', 'unknown')}, conflict_delta={drift.get('conflict_detection_delta', 'unknown')}"
            )
    else:
        lines.append("- No persona drift profile summaries are available in this delivery pack.")

    return "\n".join(lines) + "\n"
