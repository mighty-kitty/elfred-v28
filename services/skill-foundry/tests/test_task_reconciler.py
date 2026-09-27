from __future__ import annotations

from adapter.task_reconciler import (
    freetodo_payload,
    reconcile_task_observation,
    select_task_candidates,
)


def candidate(**values):
    return {
        "task_id": "task_existing",
        "title": "完成 Elfred 被动任务分析",
        "description": "实现模型分类与合并",
        "domain": "work",
        "project": "Elfred",
        "stage": "not_started",
        "progress_percent": 0,
        "priority": "high",
        **values,
    }


def observation(**values):
    return {
        "task": "完成 Elfred 被动任务分析",
        "description": "实现模型分类与合并",
        "project": "Elfred",
        "stage": "in_progress",
        "progress_percent": 45,
        "relation": "update",
        "matched_task_id": "task_existing",
        "match_confidence": 0.96,
        "confidence": 0.94,
        "priority": "high",
        **values,
    }


def test_model_match_updates_one_stable_task() -> None:
    result = reconcile_task_observation(
        observation(),
        domain="work",
        candidates=[candidate()],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "update"
    assert result.task_id == "task_existing"
    assert result.values["stage"] == "in_progress"
    assert result.values["progress_percent"] == 45


def test_exact_title_is_a_deterministic_duplicate_guard() -> None:
    result = reconcile_task_observation(
        observation(
            relation="new",
            matched_task_id=None,
            match_confidence=0,
        ),
        domain="work",
        candidates=[candidate()],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "update"
    assert result.task_id == "task_existing"


def test_related_work_on_different_hardware_remains_a_separate_task() -> None:
    result = reconcile_task_observation(
        observation(
            task="完成底座真机联调",
            project="底座",
            relation="related",
            matched_task_id="task_existing",
            match_confidence=0.99,
        ),
        domain="work",
        candidates=[candidate(title="完成吊坠真机联调", project="吊坠")],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "create"
    assert result.task_id != "task_existing"


def test_same_title_in_different_projects_is_not_merged() -> None:
    result = reconcile_task_observation(
        observation(
            project="机械臂",
            relation="new",
            matched_task_id=None,
            match_confidence=0,
        ),
        domain="work",
        candidates=[candidate(project="打印机")],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "create"
    assert result.task_id != "task_existing"


def test_duplicate_label_with_real_progress_is_promoted_to_update() -> None:
    result = reconcile_task_observation(
        observation(relation="duplicate", stage="in_progress", progress_percent=60),
        domain="work",
        candidates=[candidate(stage="in_progress", progress_percent=25)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "update"
    assert result.reason == "duplicate_with_material_progress"
    assert result.values["progress_percent"] == 60


def test_duplicate_without_material_change_only_adds_evidence() -> None:
    result = reconcile_task_observation(
        observation(relation="duplicate", stage="in_progress", progress_percent=45),
        domain="work",
        candidates=[candidate(stage="in_progress", progress_percent=45)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "evidence"
    assert result.reason == "duplicate_observation"


def test_untrusted_match_and_low_confidence_do_not_publish() -> None:
    result = reconcile_task_observation(
        observation(match_confidence=0.40, confidence=0.60),
        domain="work",
        candidates=[candidate()],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "observe"
    assert result.reason == "low_task_confidence"


def test_completed_task_is_not_regressed_by_later_screen() -> None:
    result = reconcile_task_observation(
        observation(stage="in_progress", progress_percent=30),
        domain="work",
        candidates=[candidate(stage="completed", progress_percent=100)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.values["stage"] == "completed"
    assert result.values["progress_percent"] == 100


def test_completed_task_is_not_changed_to_cancelled_by_stale_screen() -> None:
    result = reconcile_task_observation(
        observation(stage="cancelled", progress_percent=0),
        domain="work",
        candidates=[candidate(stage="completed", progress_percent=100)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.values["stage"] == "completed"
    assert result.values["progress_percent"] == 100


def test_active_task_is_not_regressed_to_not_started() -> None:
    result = reconcile_task_observation(
        observation(stage="not_started", progress_percent=0),
        domain="work",
        candidates=[candidate(stage="in_progress", progress_percent=65)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.values["stage"] == "in_progress"
    assert result.values["progress_percent"] == 65


def test_in_progress_without_explicit_progress_does_not_fabricate_percentage() -> None:
    result = reconcile_task_observation(
        observation(progress_percent=None),
        domain="work",
        candidates=[candidate(stage="not_started", progress_percent=0)],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.values["stage"] == "in_progress"
    assert result.values["progress_percent"] == 0


def test_candidate_selection_keeps_older_relevant_task() -> None:
    candidates = [
        candidate(task_id=f"recent-{index}", title=f"整理普通资料 {index}")
        for index in range(40)
    ]
    candidates.append(candidate(task_id="older-relevant", title="修复任务看板自动跳顶"))
    event = {
        "app": {"name": "Visual Studio Code", "window_title": "kanban.js"},
        "content": {"clean_text": "正在修复任务看板自动跳顶并补回归测试"},
    }

    selected = select_task_candidates(event, candidates, limit=30)

    assert selected[0]["task_id"] == "older-relevant"
    assert any(item["task_id"] == "older-relevant" for item in selected)


def test_older_retry_is_kept_as_evidence_without_reverting_current_task() -> None:
    result = reconcile_task_observation(
        observation(stage="in_progress", progress_percent=25),
        domain="work",
        candidates=[
            candidate(
                stage="in_progress",
                progress_percent=70,
                last_seen_at="2026-07-14T15:00:00+08:00",
            )
        ],
        merge_threshold=0.86,
        publish_threshold=0.70,
        observed_at="2026-07-14T14:00:00+08:00",
    )

    assert result.action == "evidence"
    assert result.reason == "stale_observation"
    assert result.values == {}


def test_unmatched_completed_observation_does_not_create_a_task() -> None:
    result = reconcile_task_observation(
        observation(
            stage="completed",
            progress_percent=100,
            relation="new",
            matched_task_id=None,
            match_confidence=0,
        ),
        domain="work",
        candidates=[],
        merge_threshold=0.86,
        publish_threshold=0.70,
    )

    assert result.action == "observe"
    assert result.reason == "terminal_without_existing_task"


def test_freetodo_payload_drives_existing_kanban_columns_and_category() -> None:
    task = candidate(stage="in_progress", progress_percent=55)
    payload = freetodo_payload(task)

    assert payload["uid"] == "elfred-task-task_existing"
    assert payload["status"] == "active"
    assert payload["percent_complete"] == 55
    assert payload["categories"] == "工作项目"
    assert "工作项目" in payload["tags"]
    assert payload["source_type"] == "elfred_analysis"
    assert payload["source_key"] == "task_existing"
    assert payload["workflow_stage"] == "in_progress"
    assert payload["project"] == "Elfred"

    completed = freetodo_payload(candidate(stage="completed", progress_percent=100))
    assert completed["status"] == "completed"
    assert completed["percent_complete"] == 100

    blocked = freetodo_payload(candidate(stage="blocked", progress_percent=40))
    assert blocked["status"] == "active"
    assert "阻塞" in blocked["tags"]
