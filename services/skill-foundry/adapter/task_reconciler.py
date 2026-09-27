from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from adapter.contracts import payload_hash


DOMAIN_LABELS = {
    "work": "工作项目",
    "life": "个人生活",
    "learning": "学习提升",
    "uncategorized": "未分类",
}
TERMINAL_STAGES = {"completed", "cancelled"}
ACTIVE_STAGES = {"in_progress", "blocked", "waiting"}
_PREVIOUS_PRODUCT_PATTERN = re.compile(
    re.escape(bytes.fromhex("616c66726564").decode("ascii")),
    re.IGNORECASE,
)


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _key(value: Any) -> str:
    normalized = _PREVIOUS_PRODUCT_PATTERN.sub("Elfred", _text(value, 240))
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized.casefold())


def _domain(value: Any) -> str:
    normalized = _text(value, 40).casefold()
    return normalized if normalized in DOMAIN_LABELS else "uncategorized"


def _stage(value: Any) -> str:
    normalized = _text(value, 40).casefold()
    return normalized if normalized in {
        "not_started", "in_progress", "blocked", "waiting",
        "completed", "cancelled", "unknown",
    } else "unknown"


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _progress(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def _optional_progress(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _progress(value)


def _character_grams(value: Any) -> set[str]:
    normalized = _key(value)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def select_task_candidates(
    event: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Rank task candidates by current evidence instead of recency alone."""

    content = event.get("content") or {}
    app = event.get("app") or {}
    context = " ".join(
        str(value or "")
        for value in (
            content.get("clean_text"),
            content.get("transcript"),
            app.get("name"),
            app.get("window_title"),
        )
    )[:20_000]
    context_key = _key(context)
    context_grams = _character_grams(context)
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    total = max(1, len(candidates))
    for index, candidate in enumerate(candidates):
        title_key = _key(candidate.get("title"))
        title_grams = _character_grams(candidate.get("title"))
        overlap = (
            len(title_grams & context_grams) / len(title_grams)
            if title_grams
            else 0.0
        )
        score = overlap * 4.0
        if title_key and title_key in context_key:
            score += 6.0
        project_key = _key(candidate.get("project"))
        if project_key and project_key in context_key:
            score += 1.5
        if _stage(candidate.get("stage")) not in TERMINAL_STAGES:
            score += 0.35
        score += (total - index) / total * 0.1
        ranked.append((score, index, candidate))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[: max(1, min(60, limit))]]


def project_task_candidates(
    candidates: list[dict[str, Any]], *, limit: int = 20
) -> list[dict[str, Any]]:
    """Expose only the small, model-relevant projection of Elfred-managed tasks."""

    output: list[dict[str, Any]] = []
    for item in candidates:
        task_id = _text(item.get("task_id"), 128)
        title = _text(item.get("title"), 200)
        if not task_id or not title:
            continue
        output.append(
            {
                "id": task_id,
                "title": title,
                "domain": _domain(item.get("domain")),
                "project": _text(item.get("project"), 100) or None,
                "stage": _stage(item.get("stage")),
                "progress_percent": _progress(item.get("progress_percent")),
            }
        )
        if len(output) >= max(1, min(30, limit)):
            break
    return output


@dataclass(frozen=True)
class TaskReconcileDecision:
    action: str
    task_id: str
    values: dict[str, Any]
    observation_key: str
    reason: str


def _exact_candidate(
    task: dict[str, Any], domain: str, candidates: list[dict[str, Any]]
) -> dict[str, Any] | None:
    title_key = _key(task.get("task") or task.get("title"))
    project_key = _key(task.get("project"))
    if not title_key:
        return None
    for candidate in candidates:
        if _key(candidate.get("title")) != title_key:
            continue
        candidate_domain = _domain(candidate.get("domain"))
        if domain != "uncategorized" and candidate_domain not in {domain, "uncategorized"}:
            continue
        candidate_project = _key(candidate.get("project"))
        if project_key and candidate_project and project_key != candidate_project:
            continue
        return candidate
    return None


def _matched_candidate(
    task: dict[str, Any],
    domain: str,
    candidates: list[dict[str, Any]],
    merge_threshold: float,
) -> dict[str, Any] | None:
    by_id = {
        _text(item.get("task_id"), 128): item
        for item in candidates
        if _text(item.get("task_id"), 128)
    }
    matched_id = _text(task.get("matched_task_id"), 128)
    relation = _text(task.get("relation"), 40).casefold()
    if (
        matched_id in by_id
        and relation in {"update", "duplicate"}
        and _confidence(task.get("match_confidence")) >= merge_threshold
    ):
        return by_id[matched_id]
    return _exact_candidate(task, domain, candidates)


def _merge_stage(
    existing: dict[str, Any] | None,
    proposed_stage: str,
    proposed_progress: int | None,
) -> tuple[str, int]:
    current_stage = _stage((existing or {}).get("stage"))
    current_progress = _progress((existing or {}).get("progress_percent"))
    # A later screenshot may still show stale UI. Once a task is completed, do
    # not let that stale observation reopen or cancel it automatically.
    if current_stage == "completed":
        return "completed", 100
    if current_stage == "cancelled" and proposed_stage != "completed":
        return "cancelled", current_progress
    if current_stage in ACTIVE_STAGES and proposed_stage in {"not_started", "unknown"}:
        return current_stage, current_progress
    stage = proposed_stage if proposed_stage != "unknown" else current_stage
    if stage == "unknown":
        stage = "not_started"
    if stage == "not_started":
        progress = 0 if existing is None else current_progress
    elif stage in {"in_progress", "blocked", "waiting"}:
        progress = current_progress if proposed_progress is None else proposed_progress
        progress = max(0, min(99, progress))
        if current_stage not in TERMINAL_STAGES:
            progress = max(current_progress, progress)
    elif stage == "completed":
        progress = 100
    else:  # cancelled
        progress = current_progress
    return stage, progress


def _is_stale_observation(
    existing: dict[str, Any] | None, observed_at: str | None
) -> bool:
    if not existing or not observed_at or not existing.get("last_seen_at"):
        return False
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        last_seen = datetime.fromisoformat(
            str(existing["last_seen_at"]).replace("Z", "+00:00")
        )
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return observed < last_seen
    except (TypeError, ValueError):
        return False


def reconcile_task_observation(
    task: dict[str, Any],
    *,
    domain: str,
    candidates: list[dict[str, Any]],
    merge_threshold: float,
    publish_threshold: float,
    observed_at: str | None = None,
) -> TaskReconcileDecision:
    """Turn one validated model task observation into a deterministic action."""

    normalized_domain = _domain(domain)
    title = _text(task.get("task") or task.get("title"), 200)
    project = _text(task.get("project"), 100)
    relation = _text(task.get("relation"), 40).casefold() or "new"
    confidence = _confidence(task.get("confidence"))
    matched = _matched_candidate(task, normalized_domain, candidates, merge_threshold)
    proposed_stage = _stage(task.get("stage"))
    proposed_progress = _optional_progress(task.get("progress_percent"))

    signature = [title.casefold(), project.casefold(), normalized_domain]
    task_id = (
        _text((matched or {}).get("task_id"), 128)
        or "task_" + payload_hash(signature)[:24]
    )
    observation_key = payload_hash(
        {
            "task_id": task_id,
            "title": title,
            "stage": proposed_stage,
            "progress": proposed_progress,
            "relation": relation,
            "project": project,
        }
    )[:24]

    if not title:
        return TaskReconcileDecision("observe", task_id, {}, observation_key, "empty_title")
    if confidence < publish_threshold:
        return TaskReconcileDecision("observe", task_id, {}, observation_key, "low_task_confidence")
    if relation == "none":
        return TaskReconcileDecision("observe", task_id, {}, observation_key, "non_action_relation")
    if matched is None and relation in {"update", "duplicate"}:
        return TaskReconcileDecision("observe", task_id, {}, observation_key, "untrusted_match")
    if matched is None and proposed_stage in TERMINAL_STAGES:
        return TaskReconcileDecision("observe", task_id, {}, observation_key, "terminal_without_existing_task")
    if matched is not None and _is_stale_observation(matched, observed_at):
        return TaskReconcileDecision("evidence", task_id, {}, observation_key, "stale_observation")

    stage, progress = _merge_stage(matched, proposed_stage, proposed_progress)
    existing_domain = _domain((matched or {}).get("domain"))
    values = {
        "title": _text((matched or {}).get("title"), 200) or title,
        "description": _text(task.get("description"), 500)
        or _text((matched or {}).get("description"), 500),
        "domain": normalized_domain
        if normalized_domain != "uncategorized"
        else existing_domain,
        "project": project or _text((matched or {}).get("project"), 100),
        "stage": stage,
        "progress_percent": progress,
        "priority": _text(task.get("priority"), 20).casefold()
        if _text(task.get("priority"), 20).casefold() in {"high", "medium", "low", "none"}
        else "none",
        "due_at": _text(task.get("deadline") or task.get("due_at"), 80) or None,
        "confidence": confidence,
    }
    if matched is None:
        action = "create"
        reason = "new_model_task"
    elif relation == "duplicate":
        material_change = (
            values["stage"] != _stage(matched.get("stage"))
            or values["progress_percent"] != _progress(matched.get("progress_percent"))
            or (
                values.get("due_at") is not None
                and values.get("due_at") != matched.get("due_at")
            )
            or (
                values.get("priority") not in {None, "none"}
                and values.get("priority") != matched.get("priority")
            )
        )
        action = "update" if material_change else "evidence"
        reason = (
            "duplicate_with_material_progress"
            if material_change
            else "duplicate_observation"
        )
    else:
        action = "update"
        reason = "matched_existing_task"
    return TaskReconcileDecision(action, task_id, values, observation_key, reason)


def freetodo_payload(task: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
    """Map a canonical task to FreeTodo without introducing UI-specific behavior."""

    task_id = _text(task.get("task_id"), 128)
    domain = _domain(task.get("domain"))
    stage, progress = _merge_stage(task, _stage(task.get("stage")), _progress(task.get("progress_percent")))
    if stage == "completed":
        status = "completed"
    elif stage == "cancelled":
        status = "canceled"
    else:
        status = "active"
    label = DOMAIN_LABELS[domain]
    project = _text(task.get("project"), 100)
    stage_labels = {
        "blocked": "阻塞",
        "waiting": "等待",
    }
    tags = list(
        dict.fromkeys(
            [
                label,
                *([project] if project else []),
                *([stage_labels[stage]] if stage in stage_labels else []),
            ]
        )
    )
    payload: dict[str, Any] = {
        "uid": f"elfred-task-{task_id}"[:64],
        "name": _text(task.get("title"), 200),
        "description": _text(task.get("description"), 500) or None,
        "user_notes": f"[ELFRED_TASK task_id={task_id}]",
        "status": status,
        "percent_complete": progress,
        "priority": _text(task.get("priority"), 20).casefold() or "none",
        "due": task.get("due_at") or None,
        "categories": label,
        "tags": tags,
        "source_type": "elfred_analysis",
        "source_key": task_id,
        "workflow_stage": stage,
        "project": project or None,
        "confidence": _confidence(task.get("confidence")),
        "last_observed_at": observed_at,
    }
    if status == "completed":
        payload["completed_at"] = observed_at or datetime.now().astimezone().isoformat()
    return payload
