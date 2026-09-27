import json
from pathlib import Path

from src.memory_system.workflow import build_default_agent


def test_delivery_pack_is_generated(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SYSTEM_MEMORY_FILE", str(tmp_path / "delivery_memory.json"))
    monkeypatch.setenv("MEMORY_SYSTEM_SQLITE_FILE", str(tmp_path / "delivery_memory.sqlite3"))

    agent = build_default_agent()
    agent.process_turn(user_id="delivery-user", session_id="delivery-session", text="我最近考试压力有点大。")

    pack = agent.generate_delivery_pack()

    assert pack["project"] == "AI Memory System"
    assert "system_report" in pack
    assert "storage_report" in pack
    assert "artifacts" in pack

    json_path = pack["artifacts"]["json_path"]
    markdown_path = pack["artifacts"]["markdown_path"]
    storage_backup_path = pack["artifacts"]["storage_backup"]
    storage_runbook_path = pack["artifacts"]["storage_runbook"]
    observability_guide_path = pack["artifacts"]["operator_observability_guide"]
    final_manifest_path = pack["artifacts"]["final_delivery_manifest"]
    acceptance_evidence_bundle_path = pack["artifacts"]["acceptance_evidence_bundle"]
    known_limitations_path = pack["artifacts"]["known_limitations"]
    release_notes_path = pack["artifacts"]["release_notes"]
    packaging_checklist_path = pack["artifacts"]["packaging_checklist"]
    package_closeout_path = pack["artifacts"]["package_closeout"]
    long_horizon_directory = pack["artifacts"]["long_horizon_directory"]
    assert json_path.endswith(".json")
    assert markdown_path.endswith(".md")
    assert storage_backup_path
    assert long_horizon_directory.endswith("long_horizon")
    assert storage_runbook_path.endswith("storage_delivery_runbook.md")
    assert observability_guide_path.endswith("operator_observability_guide.md")
    assert final_manifest_path.endswith("final_delivery_manifest.md")
    assert acceptance_evidence_bundle_path.endswith("acceptance_evidence_bundle.md")
    assert known_limitations_path.endswith("emos_v1_1_known_limitations.md")
    assert release_notes_path.endswith("emos_v1_1_release_notes.md")
    assert packaging_checklist_path.endswith("emos_v1_1_packaging_checklist.md")
    assert package_closeout_path.endswith("emos_v1_1_package_closeout.md")
    assert pack["storage_report"]["operator_checklist"]["checklist_version"] == "storage-delivery-checklist.v1"
    assert pack["storage_report"]["operator_decision_path"]["decision_path_version"] == "storage-operator-decision-path.v1"
    assert pack["storage_report"]["operator_acceptance_note"]["note_version"] == "storage-acceptance-note.v1"
    assert pack["storage_report"]["remediation_checklist"]["checklist_version"] == "storage-remediation-checklist.v1"
    assert pack["storage_report"]["exists"] is True

    markdown_text = Path(markdown_path).read_text(encoding="utf-8")
    assert "## Storage Acceptance Decision" in markdown_text
    assert "## Storage Recovery Gate" in markdown_text
    assert "## Phase E Stability" in markdown_text
    assert "## Storage Migration Gate" in markdown_text
    assert "## Unified Consumption Rule" in markdown_text
    assert "## Storage Action Surface" in markdown_text
    assert "## Shared Observability Review" in markdown_text
    assert "## Operator Review Order" in markdown_text
    assert "## Shared Error Taxonomy" in markdown_text
    assert "## Shared Ops Metrics" in markdown_text
    assert "## Recommended Lifecycle Execution" in markdown_text
    assert "## Agent Readiness Action Surface" in markdown_text
    assert "## Long-Horizon Validation Summary" in markdown_text
    assert "## Long-Horizon Multi-Run Summary" in markdown_text
    assert "## Acceptance Evidence Bundle" in markdown_text
    assert "## Final Bundle Composition" in markdown_text
    assert "## Known Limitations" in markdown_text
    assert "## Release Notes" in markdown_text
    assert "## Evidence Boundary" in markdown_text
    assert "## Persona Drift Summary" in markdown_text
    assert "Delivery decision:" in markdown_text
    assert "Last restore drill status:" in markdown_text
    assert "Restore drill freshness:" in markdown_text
    assert "Rerun rule:" in markdown_text
    assert "Restore confidence:" in markdown_text
    assert "Stability posture:" in markdown_text
    assert "Phase E summary:" in markdown_text
    assert "Latest migration attempt:" in markdown_text
    assert "Rollback ready:" in markdown_text
    assert "Migration decision:" in markdown_text
    assert "Execute upgrade when:" in markdown_text
    assert "Operator action:" in markdown_text
    assert "Operator review order:" in markdown_text
    assert "Error taxonomy:" in markdown_text
    assert "Recommended lifecycle operation:" in markdown_text
    assert "Evidence family:" in markdown_text
    assert "Separation rule:" in markdown_text
    assert "Run count:" in markdown_text
    assert "Recall delta from baseline:" in markdown_text
    assert "Stable Phase E runs:" in markdown_text
    assert "## Storage Remediation Checklist" in markdown_text
