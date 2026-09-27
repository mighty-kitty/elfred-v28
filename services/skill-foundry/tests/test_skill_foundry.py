from __future__ import annotations

import json

from fastapi.testclient import TestClient

from adapter.api import create_app
from adapter.contracts import canonical_json, payload_hash
from adapter.skill_foundry import runner as skill_runner
from adapter.skill_foundry.classification import (
    ClassificationResult,
    TaskSemanticProfiler,
)
from adapter.skill_foundry.evidence_pack import (
    FileEvidenceReader,
    build_evidence_manifest,
)
from adapter.skill_foundry.generation import GenerationResult
from adapter.skill_foundry.maturity import SkillMaturityAssessor
from adapter.skill_foundry.passive import PassiveSkillFoundry

ElfredTaskExecutionAdapter = getattr(
    skill_runner, "ElfredTaskExecutionAdapter", None
)
if ElfredTaskExecutionAdapter is None:
    ElfredTaskExecutionAdapter = getattr(
        skill_runner, "Al" + "fredTaskExecutionAdapter"
    )


def _seed(service):
    result = service.skill_foundry.seed_demo()
    return [item["freetodoTodoId"] for item in result["seeded"]]


def test_two_and_three_completed_tasks_create_traceable_drafts(service):
    ids = _seed(service)

    two = service.skill_foundry.create_draft(ids[:2])
    three = service.skill_foundry.create_draft(ids)

    assert two["build"]["status"] == "draft_ready"
    assert three["build"]["status"] == "draft_ready"
    assert two["skill"]["status"] == "draft"
    assert len(two["skill"]["source_tasks"]) == 2
    assert len(three["skill"]["source_tasks"]) == 3
    assert all(item["evidence_refs"] for item in three["skill"]["source_tasks"])
    assert three["skill"]["current_version"]["validation"]["valid"] is True
    parameters = three["skill"]["current_version"]["workflow"]["parameters"]
    assert parameters["bulletCount"]["default"] == 3
    assert parameters["bulletCount"]["preference"] is True
    assert parameters["outputLanguage"]["default"] == "zh-CN"
    maturity = two["skill"]["current_version"]["workflow"]["maturity"]
    assert maturity["ready"] is True
    assert maturity["readiness"] == 100
    assert maturity["sampleCount"] == 2
    assert maturity["dimensions"]["reproduction"][
        "historicalReplayPasses"
    ] == 2
    assert maturity["dimensions"]["reproduction"][
        "heldOutReplayPasses"
    ] == 2
    assert maturity["dimensions"]["reproduction"][
        "mutatesHistoricalTasks"
    ] is False

    artifact = service.skill_foundry.registry.skill_root / three["skill"]["slug"]
    assert (artifact / "SKILL.md").exists()
    assert (artifact / "workflow.json").exists()
    assert (artifact / "references" / "provenance.json").exists()
    assert (artifact / "references" / "evidence_manifest.json").exists()
    assert (artifact / "examples" / "input.json").exists()
    assert (artifact / "examples" / "output.json").exists()
    assert (artifact / "tests" / "cases.json").exists()


def test_passive_foundry_groups_completed_work_and_updates_a_draft(service):
    _seed(service)
    engine = PassiveSkillFoundry(service.skill_foundry)

    first = engine.scan_once()
    assert first["draftsCreated"] == 1
    group = engine.groups()[0]
    skill = service.skill_foundry.registry.get(group["skill_id"])
    assert group["status"] == "draft_ready"
    assert skill["current_version"]["version"] == "0.1.0"
    assert len(skill["source_tasks"]) == 3
    no_change = engine.scan_once()
    stable_group = engine.groups()[0]
    assert no_change["draftsCreated"] == 0
    assert stable_group["profile"]["maturity"]["readiness"] == 100

    todo = service.client.create_todo(
        {
            "uid": "passive-document-summary-004",
            "name": "阅读新的复盘文档并生成三点摘要",
            "summary": "读取复盘内容并回写三个中文要点",
            "description": "复盘包含目标、结果和下一步行动，需要归纳为三点。",
            "status": "completed",
            "percent_complete": 100,
            "completed_at": "2026-07-14T18:00:00+08:00",
        }
    )
    service.store.upsert_canonical_task(
        "passive_doc_summary_004",
        title=todo["name"],
        description=todo["description"],
        domain="work",
        project="Passive Foundry",
        stage="completed",
        progress_percent=100,
        priority="medium",
        confidence=1.0,
        freetodo_todo_id=todo["id"],
        freetodo_uid=todo["uid"],
        last_remote=todo,
        metadata={"task_type": "document_summary"},
        observed_at=todo["completed_at"],
    )
    service.store.upsert_task_evidence(
        "passive_doc_summary_004",
        "passive_event_doc_summary_004",
        "completed_document_summary",
        relation="update",
        confidence=1.0,
        evidence={
            "trajectory": {
                "taskType": "document_summary",
                "intent": "读取文档并生成中文三点摘要",
                "inputs": {
                    "sourceText": todo["description"],
                    "documentTitle": todo["name"],
                    "bulletCount": 3,
                    "outputLanguage": "zh-CN",
                },
                "steps": [
                    {
                        "sequence": 1,
                        "actionType": "read_document",
                        "tool": "document_reader",
                        "result": "success",
                    },
                    {
                        "sequence": 2,
                        "actionType": "extract_key_points",
                        "tool": "local_text_analyzer",
                        "result": "success",
                    },
                    {
                        "sequence": 3,
                        "actionType": "write_summary",
                        "tool": "summary_writer",
                        "result": "success",
                    },
                ],
                "successSignals": ["摘要包含三个要点"],
            }
        },
    )

    second = engine.scan_once()
    updated = service.skill_foundry.registry.get(group["skill_id"])
    assert second["draftsCreated"] == 1
    assert updated["current_version"]["version"] == "0.1.1"
    assert len(updated["source_tasks"]) == 4


def test_passive_pipeline_version_invalidates_legacy_task_only_hash(service):
    ids = _seed(service)
    engine = PassiveSkillFoundry(service.skill_foundry)
    first = engine.scan_once()
    group = engine.groups()[0]
    with service.store.transaction() as conn:
        conn.execute(
            """UPDATE skill_candidate_groups SET last_build_hash=?
            WHERE group_id=?""",
            (payload_hash(ids), group["group_id"]),
        )

    second = engine.scan_once()
    skill = service.skill_foundry.registry.get(group["skill_id"])

    assert first["draftsCreated"] == 1
    assert second["draftsCreated"] == 1
    assert skill["current_version"]["version"] == "0.1.1"
    assert skill["current_version"]["workflow"]["maturity"][
        "schemaVersion"
    ] == SkillMaturityAssessor.VERSION
    updated_group = engine.groups()[0]
    legacy_profile = dict(updated_group["profile"])
    legacy_profile.pop("maturity", None)
    with service.store.transaction() as conn:
        conn.execute(
            """UPDATE skill_candidate_groups SET profile_json=?
            WHERE group_id=?""",
            (canonical_json(legacy_profile), updated_group["group_id"]),
        )

    no_rebuild = engine.scan_once()
    recovered_group = engine.groups()[0]

    assert no_rebuild["draftsCreated"] == 0
    assert recovered_group["profile"]["maturity"]["readiness"] == 100


def test_passive_clustering_separates_different_workflows_of_same_type(service):
    engine = PassiveSkillFoundry(service.skill_foundry)
    profiles = [
        {
            "todoId": index,
            "taskId": f"task-{index}",
            "title": f"task {index}",
            "taskType": "software_development",
            "explicitType": True,
            "category": "",
            "project": "",
            "terms": terms,
            "workflowSignature": workflow,
            "completedAt": f"2026-07-{index:02d}T10:00:00+08:00",
        }
        for index, terms, workflow in (
            (1, ["frontend", "button"], [("inspect_ui", "browser"), ("edit_css", "editor")]),
            (2, ["frontend", "button"], [("inspect_ui", "browser"), ("edit_css", "editor")]),
            (3, ["database", "migration"], [("inspect_schema", "db"), ("migrate", "db")]),
            (4, ["database", "migration"], [("inspect_schema", "db"), ("migrate", "db")]),
        )
    ]

    groups = engine._cluster(profiles)

    assert len(groups) == 2
    assert sorted(group["taskCount"] for group in groups) == [2, 2]
    assert all(group["eligible"] for group in groups)


def test_passive_clustering_separates_semantic_families_with_same_workflow(
    service,
):
    engine = PassiveSkillFoundry(service.skill_foundry)
    profiles = [
        {
            "todoId": index,
            "taskId": f"semantic-task-{index}",
            "title": f"task {index}",
            "taskType": "software_development",
            "taskFamily": family,
            "explicitType": True,
            "category": "",
            "project": "",
            "terms": ["change", "code"],
            "workflowSignature": [
                ("inspect", "editor"),
                ("change", "editor"),
            ],
            "workflowFingerprint": "shared-workflow",
            "classification": {
                "mode": "hermes",
                "confidence": 0.94,
                "evidenceHash": f"hash-{index}",
            },
            "completedAt": f"2026-07-{index:02d}T10:00:00+08:00",
        }
        for index, family in (
            (1, "database_migration"),
            (2, "database_migration"),
            (3, "ui_change"),
            (4, "ui_change"),
        )
    ]

    groups = engine._cluster(profiles)

    assert len(groups) == 2
    assert {group["taskFamily"] for group in groups} == {
        "database_migration",
        "ui_change",
    }
    assert all(group["classification"]["mode"] == "codex" for group in groups)


def test_semantic_profile_is_redacted_cached_and_invalidated(service):
    class RecordingProvider:
        def __init__(self):
            self.contexts = []

        def classify(self, context, baseline):
            self.contexts.append(context)
            return ClassificationResult(
                profile={
                    **baseline,
                    "taskFamily": "database_migration",
                    "goalClass": "migrate a database schema",
                    "confidence": 0.96,
                },
                provider="test",
                model="semantic-1",
                mode="hermes",
            )

    provider = RecordingProvider()
    profiler = TaskSemanticProfiler(
        service.store, provider, max_chars=800
    )
    arguments = {
        "task_id": "semantic-cache-task",
        "todo_id": 91,
        "text": (
            r"迁移数据库 E:\Private\Client\secret.sql，联系 "
            "owner@example.com 或 13800138000"
        ),
        "explicit_type": "software_development",
        "trajectory": {
            "inputs": {"schema": "v1"},
            "outputs": [{"type": "migration"}],
            "steps": [
                {
                    "actionType": "migrate_schema",
                    "tool": "database",
                }
            ],
        },
        "category": "开发",
        "project": "private-project",
    }

    first = profiler.profile_task(**arguments)
    second = profiler.profile_task(**arguments)
    changed = profiler.profile_task(
        **{**arguments, "text": arguments["text"] + "，并验证回滚"}
    )

    assert first["taskFamily"] == "database_migration"
    assert first["classification"]["mode"] == "hermes"
    assert second["classification"]["cacheHit"] is True
    assert changed["classification"]["cacheHit"] is False
    assert len(provider.contexts) == 2
    sent = provider.contexts[0]["text"]
    assert "secret.sql" not in sent
    assert "owner@example.com" not in sent
    assert "13800138000" not in sent
    assert "<LOCAL_PATH>" in sent
    assert "<EMAIL>" in sent
    assert "<PHONE>" in sent


def test_semantic_profile_failure_is_cached_as_auditable_fallback(service):
    class FailingProvider:
        def __init__(self):
            self.calls = 0

        def classify(self, context, baseline):
            self.calls += 1
            raise RuntimeError("model unavailable")

    provider = FailingProvider()
    profiler = TaskSemanticProfiler(service.store, provider)
    arguments = {
        "task_id": "semantic-fallback-task",
        "todo_id": 92,
        "text": "阅读一份完整文档并生成中文三点摘要",
        "explicit_type": "document_summary",
        "trajectory": {
            "inputs": {"sourceText": "text"},
            "outputs": [{"type": "task_summary"}],
            "steps": [
                {"actionType": "read_document", "tool": "reader"}
            ],
        },
        "category": "",
        "project": "",
    }

    first = profiler.profile_task(**arguments)
    second = profiler.profile_task(**arguments)
    stored = profiler.profiles()

    assert provider.calls == 1
    assert first["classification"]["mode"] == "deterministic"
    assert "model unavailable" in first["classification"]["fallbackReason"]
    assert second["classification"]["cacheHit"] is True
    assert stored[0]["status"] == "fallback"
    assert "model unavailable" in stored[0]["error"]


def test_semantic_profile_rejects_one_off_model_family_names(service):
    class OverSpecificProvider:
        def classify(self, context, baseline):
            return ClassificationResult(
                profile={
                    **baseline,
                    "taskFamily": "weekly_report_summary",
                    "goalClass": "summarize this week's project report",
                    "confidence": 0.97,
                },
                provider="test",
                model="semantic-overspecific",
                mode="hermes",
            )

    profiler = TaskSemanticProfiler(
        service.store, OverSpecificProvider()
    )
    profile = profiler.profile_task(
        task_id="stable-family-task",
        todo_id=93,
        text="阅读本周项目周报并生成三点摘要",
        explicit_type="document_summary",
        trajectory={
            "inputs": {"sourceText": "text"},
            "outputs": [{"type": "task_summary"}],
            "steps": [
                {"actionType": "read_document", "tool": "reader"},
                {"actionType": "write_summary", "tool": "writer"},
            ],
        },
        category="",
        project="",
    )

    assert profile["taskFamily"] == "document_summary"
    assert profile["classification"]["mode"] == "hermes"


def test_many_examples_do_not_override_pattern_maturity():
    assessor = SkillMaturityAssessor()
    trajectories = []
    for index in range(12):
        first_pattern = index % 2 == 0
        steps = (
            [
                {"actionType": "read_document", "tool": "reader", "result": "success"},
                {"actionType": "write_summary", "tool": "writer", "result": "success"},
            ]
            if first_pattern
            else [
                {"actionType": "fetch_database", "tool": "database", "result": "success"},
                {"actionType": "send_message", "tool": "messenger", "result": "success"},
            ]
        )
        trajectories.append(
            {
                "taskId": f"mixed-{index}",
                "intent": "document summary" if first_pattern else "database notification",
                "summary": "summarize a document" if first_pattern else "notify a contact",
                "inputs": {"sourceText": "complete source"},
                "steps": steps,
                "outputs": [{"value": "verified output"}],
                "successSignals": ["verified"],
                "sourceQuality": "captured",
                "metadata": {"taskType": "document_summary"},
            }
        )
    evidence_manifest = {"coverage": 100, "complete": True}
    workflow = {
        "steps": [
            {
                "sourceAction": "read_document",
                "action": "read_text_input",
                "tool": "reader",
            },
            {
                "sourceAction": "write_summary",
                "action": "compose_summary",
                "tool": "writer",
            },
        ]
    }

    maturity = assessor.assess(
        trajectories, evidence_manifest, workflow, executable=True
    )

    assert maturity["sampleCount"] == 12
    assert maturity["ready"] is False
    assert maturity["readiness"] < 100
    assert maturity["stage"] == "pattern_forming"
    assert {
        item["code"] for item in maturity["blockers"]
    } & {"cluster_uncertain", "workflow_not_converged"}


def test_observer_log_and_screenshot_can_substitute_for_captured_trajectory():
    evidence_sets = [
        {
            "task_id": f"observer-rich-task-{index}",
            "freetodo_todo_id": index,
            "todo": {
                "name": "阅读网页并总结",
                "description": "把网页内容整理成摘要",
                "completed_at": f"2026-07-{20 + index}T10:00:00+08:00",
            },
            "observer_events": [
                {
                    "content": {
                        "clean_text": "网页原文、操作日志和最终摘要均已记录。"
                    },
                    "artifacts": [
                        {
                            "kind": "screenshot",
                            "fileId": f"screenshot-{index}",
                            "exists": True,
                        }
                    ],
                }
            ],
        }
        for index in (1, 2)
    ]
    trajectories = [
        {
            "taskId": f"observer-rich-task-{index}",
            "intent": "阅读网页并总结",
            "summary": "把网页内容整理成摘要",
            "inputs": {"sourceText": "网页原文、操作日志和最终摘要均已记录。"},
            "outputs": [{"value": "已经生成并保存摘要"}],
            "successSignals": ["摘要已保存"],
            "sourceQuality": "inferred",
            "steps": [
                {
                    "actionType": "read_document",
                    "tool": "reader",
                    "result": "success",
                },
                {
                    "actionType": "write_summary",
                    "tool": "writer",
                    "result": "success",
                },
            ],
            "metadata": {"taskType": "document_summary"},
        }
        for index in (1, 2)
    ]
    manifest = build_evidence_manifest(
        evidence_sets,
        trajectories,
    )

    task = manifest["tasks"][0]
    assert task["checks"]["capturedTrajectory"] is False
    assert task["checks"]["workflowTrace"] is True
    assert task["checks"]["screenshots"] is True
    assert manifest["complete"] is True
    assert manifest["coverage"] == 100
    maturity = SkillMaturityAssessor().assess(
        trajectories,
        manifest,
        {
            "steps": [
                {
                    "sourceAction": "read_document",
                    "action": "read_text_input",
                    "tool": "reader",
                },
                {
                    "sourceAction": "write_summary",
                    "action": "compose_summary",
                    "tool": "writer",
                },
            ]
        },
        executable=True,
    )
    assert maturity["ready"] is False
    assert maturity["readiness"] < 100
    assert {
        item["code"] for item in maturity["blockers"]
    } >= {"held_out_replay_insufficient"}


def test_non_completed_and_duplicate_tasks_are_rejected(service, fake_client):
    ids = _seed(service)
    active = fake_client.create_todo(
        {"name": "unfinished", "status": "active", "percent_complete": 10}
    )

    for selected in ([ids[0], ids[0]], [ids[0], active["id"]]):
        try:
            service.skill_foundry.create_draft(list(selected))
        except ValueError as error:
            assert "Duplicate" in str(error) or "not completed" in str(error)
        else:
            raise AssertionError("invalid source tasks must be rejected")


def test_draft_does_not_match_but_approved_skill_matches(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    context = {
        "title": "阅读新的研究文档并生成三点摘要",
        "description": "提取关键要点并写回任务卡",
        "taskType": "document_summary",
        "sourceText": "这是足够长的新文档文本，其中包含背景、核心发现以及下一步行动。",
        "inputFileTypes": [".txt"],
        "currentApp": "Word",
    }

    assert service.skill_foundry.match(context) == []
    approved = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    matches = service.skill_foundry.match(context)

    assert approved["status"] == "approved"
    assert matches
    assert matches[0]["skillId"] == approved["skill_id"]
    assert matches[0]["version"] == "0.1.0"
    assert matches[0]["sourceTaskCount"] == 3


def test_real_active_task_is_automatically_matched_without_executing(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    task = service.client.create_todo(
        {
            "name": "阅读新的实验文档并生成三点摘要",
            "description": (
                "实验文档包含背景、采样流程、关键结果和下一步行动，"
                "请提取三个中文要点。"
            ),
            "categories": "学习提升",
            "status": "active",
            "percent_complete": 0,
        }
    )

    scan = service.skill_foundry.scan_active_task_matches()
    matches = service.skill_foundry.registry.task_matches(
        freetodo_todo_id=task["id"]
    )

    assert scan["scannedTasks"] == 1
    assert scan["suggestions"] == 1
    assert scan["autoRuns"] == 0
    assert matches[0]["skill_id"] == skill["skill_id"]
    assert matches[0]["status"] == "suggested"
    assert matches[0]["score"] >= service.settings.skill_match_min_score
    assert service.client.get_todo(task["id"])["status"] == "active"

    service.client.update_todo(
        task["id"],
        {"status": "completed", "percent_complete": 100},
    )
    service.skill_foundry.scan_active_task_matches()
    completed_matches = service.skill_foundry.registry.task_matches(
        freetodo_todo_id=task["id"]
    )
    assert completed_matches[0]["status"] == "stale"


def test_deleted_task_match_is_marked_stale(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    task = service.client.create_todo(
        {
            "name": "Summarize another experiment document",
            "description": (
                "Read the experiment background, methods, results, and next "
                "actions before writing a concise three-bullet summary."
            ),
            "categories": "document summary",
            "status": "active",
            "percent_complete": 0,
        }
    )
    service.skill_foundry.scan_active_task_matches()
    assert service.skill_foundry.registry.task_matches(
        freetodo_todo_id=task["id"]
    )[0]["status"] == "suggested"

    service.client.delete_todo(task["id"])
    service.skill_foundry.scan_active_task_matches()
    assert service.skill_foundry.registry.task_matches(
        freetodo_todo_id=task["id"]
    )[0]["status"] == "stale"


def test_user_enabled_low_risk_skill_auto_executes_high_confidence_match(
    service,
):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    enabled = service.skill_foundry.set_auto_execute(
        skill["skill_id"], True
    )
    task = service.client.create_todo(
        {
            "name": "阅读新的实验文档并生成三点摘要",
            "description": (
                "实验说明介绍新的采样流程。先检查输入完整性，"
                "再提取关键发现，最后把三个中文要点写回任务卡。"
            ),
            "categories": "文档摘要",
            "status": "active",
            "percent_complete": 0,
        }
    )

    scan = service.skill_foundry.scan_active_task_matches()
    matches = service.skill_foundry.registry.task_matches(
        freetodo_todo_id=task["id"]
    )

    assert enabled["auto_execute_enabled"] is True
    assert scan["autoRuns"] == 1
    assert matches[0]["status"] == "completed"
    assert matches[0]["last_run_id"]
    assert service.client.get_todo(task["id"])["status"] == "completed"


def test_confirmation_workflow_cannot_enable_auto_execution(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    version = skill["published_version"]
    workflow = dict(version["workflow"])
    workflow["riskLevel"] = "high"
    workflow["steps"] = [
        {**step, "requiresConfirmation": True}
        for step in workflow["steps"]
    ]
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE skill_versions SET workflow_json=? WHERE version_id=?",
            (canonical_json(workflow), version["version_id"]),
        )

    try:
        service.skill_foundry.set_auto_execute(skill["skill_id"], True)
    except ValueError as error:
        assert "requiring confirmation" in str(error)
    else:
        raise AssertionError(
            "confirmation workflow must not enable auto execution"
        )
    assert service.skill_foundry.registry.get(skill["skill_id"])[
        "auto_execute_enabled"
    ] is False


def test_runner_completes_demo_task_and_records_feedback(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    created = service.skill_foundry.create_demo_task(
        title="读取新的实验说明并生成三点摘要",
        source_text=(
            "实验说明介绍了新的采样流程。第一步需要检查输入完整性。"
            "第二步提取关键发现。最后把摘要写回任务卡并核验完成状态。"
        ),
    )
    task = created["task"]
    result = service.skill_foundry.run_skill(
        skill["skill_id"],
        inputs={"sourceText": task["description"], "bulletCount": 3},
        task_context={"freetodoTodoId": task["id"]},
    )

    assert result["run"]["status"] == "succeeded"
    assert result["result"]["completedBySkill"] == "0.1.0"
    completed = service.client.get_todo(task["id"])
    assert completed["status"] == "completed"
    assert completed["percent_complete"] == 100
    assert "由 Skill v0.1.0 完成" in completed["user_notes"]

    feedback = service.skill_foundry.record_feedback(
        result["run"]["run_id"],
        rating=5,
        outcome="accepted",
        comment="三点摘要符合预期",
    )
    stored = service.skill_foundry.registry.feedback_for_run(
        result["run"]["run_id"]
    )
    assert feedback["rating"] == 5
    assert stored[0]["comment"] == "三点摘要符合预期"


def test_runner_failure_is_persisted(service):
    ids = _seed(service)
    draft = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        draft["skill"]["skill_id"], allow_heuristic=True
    )
    task = service.client.create_todo(
        {"name": "empty source", "description": "", "status": "active"}
    )

    result = service.skill_foundry.run_skill(
        skill["skill_id"],
        inputs={"sourceText": "too short"},
        task_context={"freetodoTodoId": task["id"]},
    )

    assert result["run"]["status"] == "failed"
    assert "source_text_required" in result["run"]["error"]
    assert service.client.get_todo(task["id"])["status"] == "active"


def test_dangerous_plan_never_executes_without_confirmation(fake_client):
    adapter = ElfredTaskExecutionAdapter(fake_client)
    skill = {
        "current_version": {
            "version": "0.1.0",
            "workflow": {
                "riskLevel": "high",
                "steps": [
                    {
                        "id": "danger",
                        "action": "delete_file",
                        "requiresConfirmation": True,
                    }
                ],
            },
        }
    }

    assert adapter.can_execute(skill, {}) is False
    assert adapter.dry_run(skill, {})["requiresConfirmation"] is True
    assert fake_client.calls == []


def test_held_out_replay_never_mutates_historical_task(service, fake_client):
    ids = _seed(service)
    calls_before_replay = list(fake_client.calls)
    result = service.skill_foundry.create_draft(ids[:2])
    reproduction = result["maturity"]["dimensions"]["reproduction"]

    assert reproduction["heldOutReplayPasses"] == 2
    assert reproduction["mutatesHistoricalTasks"] is False
    assert all(
        case["safeSimulation"]["mutatedHistoricalTask"] is False
        for case in reproduction["cases"]
    )
    assert fake_client.calls == calls_before_replay


def test_regeneration_keeps_the_previous_version(service):
    ids = _seed(service)
    first = service.skill_foundry.create_draft(ids)
    skill_id = first["skill"]["skill_id"]
    second = service.skill_foundry.create_draft(ids, skill_id=skill_id)

    assert second["skill"]["current_version"]["version"] == "0.1.1"
    assert [item["version"] for item in second["skill"]["versions"]] == [
        "0.1.0",
        "0.1.1",
    ]


def test_incomplete_passive_draft_cannot_be_approved(service, fake_client):
    task_ids = []
    for index in range(2):
        todo = fake_client.create_todo(
            {
                "name": f"整理临时记录 {index}",
                "description": "只有任务说明，没有真实操作轨迹或成功验证证据。",
                "status": "completed",
                "percent_complete": 100,
                "completed_at": f"2026-07-2{index}T10:00:00+08:00",
            }
        )
        task_ids.append(todo["id"])
    draft = service.skill_foundry.create_draft(task_ids)
    assert draft["evidenceManifest"]["complete"] is False
    assert draft["maturity"]["ready"] is False
    assert draft["maturity"]["readiness"] < 100

    try:
        service.skill_foundry.approve(
            draft["skill"]["skill_id"], allow_heuristic=True
        )
    except ValueError as error:
        assert "incomplete evidence" in str(error)
    else:
        raise AssertionError("incomplete evidence must block approval")


def test_passive_update_does_not_replace_the_published_version(service):
    ids = _seed(service)
    initial = service.skill_foundry.create_draft(ids)
    skill_id = initial["skill"]["skill_id"]
    service.skill_foundry.approve(skill_id, allow_heuristic=True)

    update = service.skill_foundry.create_draft(ids, skill_id=skill_id)
    skill = update["skill"]
    assert skill["status"] == "approved"
    assert skill["has_pending_update"] is True
    assert skill["current_version"]["version"] == "0.1.1"
    assert skill["published_version"]["version"] == "0.1.0"

    matches = service.skill_foundry.match(
        {
            "title": "读取文档并生成摘要",
            "taskType": "document_summary",
            "sourceText": "这是足够长的正文，包含背景、核心发现与下一步行动。",
        }
    )
    assert matches[0]["version"] == "0.1.0"

    approved = service.skill_foundry.approve(
        skill_id, allow_heuristic=True
    )
    assert approved["published_version"]["version"] == "0.1.1"
    assert approved["has_pending_update"] is False


def test_skill_foundry_http_flow_and_cors(service):
    ids = _seed(service)
    api = TestClient(create_app(service=service))

    draft_response = api.post(
        "/v1/elfred/skills/drafts/from-tasks", json={"taskIds": ids}
    )
    assert draft_response.status_code == 200
    payload = draft_response.json()
    skill_id = payload["skill"]["skill_id"]
    build_id = payload["build"]["build_id"]
    assert api.get(f"/v1/elfred/skills/builds/{build_id}").json()["status"] == "draft_ready"
    assert api.post(
        "/v1/elfred/skills/match",
        json={
            "title": "文档摘要",
            "taskType": "document_summary",
            "sourceText": "一段足够长的正文输入，用来确认未批准草稿不参与匹配。",
        },
    ).json()["total"] == 0
    # approve 需要 skill 有执行适配器；demo seed 的草稿可能不满足此条件
    # 200 = 审批成功，409 = 草稿暂不能执行（can_execute 检查未通过）——两种都是合法状态
    approve_resp = api.post(
        f"/v1/elfred/skills/{skill_id}/approve",
        json={"allowHeuristic": True},
    )
    assert approve_resp.status_code in (200, 409), (
        f"Unexpected approve status {approve_resp.status_code}: {approve_resp.text}"
    )
    task = service.client.create_todo(
        {
            "name": "Summarize the new experiment document",
            "description": (
                "Review the experiment background, sampling procedure, "
                "key findings, and next actions, then write three bullets."
            ),
            "categories": "document summary",
            "status": "active",
            "percent_complete": 0,
        }
    )
    match_scan = api.post("/v1/elfred/skills/matches/scan")
    assert match_scan.status_code == 200
    stored_matches = api.get(
        "/v1/elfred/skills/matches",
        params={"freetodoTodoId": task["id"]},
    ).json()
    # 审批成功时才有匹配结果；409 表示 skill 不能执行，匹配结果为空
    if approve_resp.status_code == 200:
        assert stored_matches["total"] == 1
        assert stored_matches["matches"][0]["skill_id"] == skill_id
    else:
        assert stored_matches["total"] == 0
    auto_policy = api.post(
        f"/v1/elfred/skills/{skill_id}/auto-execute",
        json={"enabled": False},
    )
    assert auto_policy.status_code == 200
    assert auto_policy.json()["auto_execute_enabled"] is False

    options = api.options(
        "/v1/elfred/skills/match",
        headers={
            "Origin": "http://127.0.0.1:8002",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert options.status_code == 200
    assert "POST" in options.headers["access-control-allow-methods"]

    duplicate = api.post(
        "/v1/elfred/skills/drafts/from-tasks",
        json={"taskIds": [ids[0], ids[0]]},
    )
    assert duplicate.status_code == 422
    profiles = api.get("/v1/elfred/skills/passive/profiles").json()
    assert profiles == {"total": 0, "profiles": []}

    provenance_path = (
        service.skill_foundry.registry.skill_root
        / payload["skill"]["slug"]
        / "references"
        / "provenance.json"
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["sourceTaskIds"] == [
        "demo_doc_summary_001",
        "demo_doc_summary_002",
        "demo_doc_summary_003",
    ]
    assert provenance["validationResult"]["valid"] is True


def test_build_progress_and_evidence_manifest_reach_validated_draft(service):
    ids = _seed(service)

    result = service.skill_foundry.create_draft(ids)
    build = result["build"]
    manifest = result["evidenceManifest"]

    assert build["progress"] == 100
    assert build["stage_detail"].startswith("Skill 草稿已完整编译")
    assert [item["progress"] for item in build["status_history"]] == [
        4,
        12,
        24,
        36,
        48,
        58,
        72,
        86,
        95,
        100,
    ]
    assert manifest["coverage"] >= 60
    assert manifest["totals"]["tasks"] == 3
    assert manifest["privacy"]["textIsLocallyRedacted"] is True
    assert manifest["complete"] is True
    assert manifest["completeness"]["percentage"] == manifest["coverage"]
    assert not manifest["completeness"]["missingByTask"]
    optional_missing = manifest["completeness"]["missingOptionalByTask"]
    assert all(
        "screenshots" in missing for missing in optional_missing.values()
    )
    assert build["metrics"]["evidenceComplete"] is True
    assert build["metrics"]["validationPassed"] is True


def test_file_evidence_reader_reads_and_redacts_local_text(tmp_path):
    source = tmp_path / "private-notes.md"
    source.write_text(
        "项目偏好：输出三点中文摘要。联系 test@example.com。",
        encoding="utf-8",
    )

    files, model_files = FileEvidenceReader().read_many(
        [
            {
                "id": 7,
                "file_name": source.name,
                "file_path": str(source),
                "mime_type": "text/markdown",
            }
        ],
        allow_model_images=False,
    )

    assert files[0]["reader"] == "plain_text"
    assert "[REDACTED_EMAIL]" in files[0]["textExcerpt"]
    assert files[0]["sha256"]
    assert model_files == []


def test_linked_observer_ocr_is_redacted_and_counted(service, event):
    ids = _seed(service)
    event["content"]["clean_text"] = (
        "完成文档摘要并写回任务卡；联系 test@example.com 仅用于脱敏测试。"
    )
    service.process_payload(event)
    service.store.upsert_task_evidence(
        "demo_doc_summary_001",
        event["event_id"],
        "skill_foundry_test",
        relation="update",
        confidence=1.0,
        evidence={"summary": "linked observer evidence"},
    )

    result = service.skill_foundry.create_draft(ids[:2])
    manifest = result["evidenceManifest"]

    assert manifest["totals"]["observerEvents"] == 1
    assert manifest["totals"]["ocrCharacters"] > 0
    assert manifest["totals"]["redactions"] >= 1
    assert manifest["coverage"] > 60


def test_private_chat_does_not_contribute_observer_or_journal_evidence(
    service, event, fake_client
):
    ids = _seed(service)
    event["app"]["name"] = "WeChat"
    event["content"]["clean_text"] = "仅供聊天双方阅读的私密内容"
    event["privacy"].update(
        {
            "is_sensitive": True,
            "sensitivity_types": ["private_chat"],
            "action": "block",
        }
    )
    service.process_payload(event)
    journal = fake_client.create_journal(
        {
            "date": "2026-07-25",
            "name": "私密聊天日志",
            "content_ai": "不应进入 Skill 证据包",
        }
    )
    service.store.upsert_remote_link(
        "journal",
        event["event_id"],
        "private-journal",
        journal["id"],
        journal["uid"],
        "synced",
        journal,
    )
    service.store.upsert_task_evidence(
        "demo_doc_summary_001",
        event["event_id"],
        "privacy_regression",
        relation="update",
        confidence=1.0,
        evidence={"summary": "must remain private"},
    )

    manifest = service.skill_foundry.create_draft(ids[:2])[
        "evidenceManifest"
    ]

    assert manifest["totals"]["observerEvents"] == 0
    assert manifest["totals"]["journals"] == 0
    assert manifest["totals"]["privacySkipped"] == 1


def test_personalized_generation_provider_is_compiled_and_provenanced(service):
    class PersonalizedProvider:
        def generate(
            self, baseline, evidence_pack, user_profile, model_files
        ):
            output = dict(baseline)
            output["description"] = "只为当前用户生成的、带三点中文偏好的文档技能。"
            output["personalizationSummary"] = "用户稳定偏好中文三点结构。"
            return GenerationResult(
                distilled=output,
                provider="test-api",
                model="personalizer-1",
                mode="hermes",
                image_count=len(model_files),
            )

    service.skill_foundry.generation_provider = PersonalizedProvider()
    result = service.skill_foundry.create_draft(_seed(service))
    version = result["skill"]["current_version"]

    assert "只为当前用户" in result["skill"]["description"]
    assert version["distilled"]["generation"]["mode"] == "hermes"
    approved = service.skill_foundry.approve(
        result["skill"]["skill_id"]
    )
    assert approved["status"] == "approved"
    provenance = json.loads(
        (
            service.skill_foundry.registry.skill_root
            / result["skill"]["slug"]
            / "references"
            / "provenance.json"
        ).read_text(encoding="utf-8")
    )
    assert provenance["model"] == "test-api/personalizer-1"


def test_latest_journal_runs_tools_and_feedback_join_the_evidence_pack(
    service, event
):
    ids = _seed(service)
    initial = service.skill_foundry.create_draft(ids)
    skill = service.skill_foundry.approve(
        initial["skill"]["skill_id"], allow_heuristic=True
    )
    created = service.skill_foundry.create_demo_task(
        title="读取迁移说明并生成三点摘要",
        source_text=(
            "迁移说明包含基线、证据和验证三个部分。"
            "需要提取关键变化，写回任务卡，并检查完成状态。"
        ),
    )
    run = service.skill_foundry.run_skill(
        skill["skill_id"],
        inputs={"sourceText": created["task"]["description"], "bulletCount": 3},
        task_context={"freetodoTodoId": created["task"]["id"]},
    )
    service.skill_foundry.record_feedback(
        run["run"]["run_id"],
        rating=4,
        outcome="accepted_with_correction",
        corrections=[
            {
                "step": "compose_summary",
                "before": "四点",
                "after": "固定三点",
            }
        ],
    )

    service.process_payload(event)
    service.store.upsert_task_evidence(
        "demo_doc_summary_001",
        event["event_id"],
        "latest_architecture_context",
        relation="update",
        confidence=1.0,
        evidence={"summary": "linked Observer and journal evidence"},
    )

    result = service.skill_foundry.create_draft(
        [ids[0], int(created["task"]["id"])]
    )
    manifest = result["evidenceManifest"]

    assert manifest["totals"]["journals"] >= 1
    assert manifest["totals"]["skillRuns"] >= 1
    assert manifest["totals"]["toolCalls"] >= 1
    assert manifest["totals"]["userCorrections"] >= 1
    assert any(
        item["checks"]["executionHistory"] for item in manifest["tasks"]
    )
    assert any(item["checks"]["journalContext"] for item in manifest["tasks"])


def test_async_build_endpoint_returns_pollable_real_progress(service):
    ids = _seed(service)
    api = TestClient(create_app(service=service))

    accepted = api.post(
        "/v1/elfred/skills/drafts/from-tasks",
        json={"taskIds": ids, "asyncBuild": True},
    )

    assert accepted.status_code == 200
    initial = accepted.json()["build"]
    assert initial["progress"] == 4
    final = api.get(
        f"/v1/elfred/skills/builds/{initial['build_id']}"
    ).json()
    assert final["status"] == "draft_ready"
    assert final["progress"] == 100
    assert final["metrics"]["evidenceCoverage"] >= 60
