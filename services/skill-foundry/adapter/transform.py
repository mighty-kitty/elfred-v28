from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any

from adapter.contracts import payload_hash
from adapter.privacy import safe_event_view


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n。；;，,")[:200]


def parse_due(value: Any, created_at: str) -> str | None:
    raw = str(value or "").strip()
    if not raw or raw.casefold() in {"none", "unknown", "未知", "待定"}:
        return None
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if raw in {"明天", "tomorrow"}:
        due = datetime.combine((created + timedelta(days=1)).date(), time(18, 0), created.tzinfo)
        return due.isoformat()
    if raw in {"今天", "今日", "today"}:
        return datetime.combine(created.date(), time(18, 0), created.tzinfo).isoformat()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def extract_tasks(event: dict[str, Any], threshold: float, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content = event.get("content") or {}
    suggestions = event.get("suggestions") or {}
    raw_tasks = [*(content.get("tasks") or []), *(suggestions.get("task_card_suggestions") or [])]
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_tasks:
        if isinstance(raw, str):
            raw = {"task": raw}
        if not isinstance(raw, dict):
            continue
        title = normalize_title(str(raw.get("task") or raw.get("title") or ""))
        if not title:
            continue
        deadline = raw.get("due_at") or raw.get("deadline")
        key = payload_hash([title.casefold(), str(deadline or "")])[:20]
        if key in seen:
            continue
        seen.add(key)
        confidence = float(raw.get("confidence") or 0.5)
        requires_confirmation = bool((event.get("privacy") or {}).get("requires_user_confirmation"))
        status = "active" if confidence >= threshold and not requires_confirmation else "draft"
        priority = str(raw.get("priority") or "none").casefold()
        if priority not in {"high", "medium", "low", "none"}:
            priority = "none"
        tags = [topic["display_name"] for topic in topics]
        notes = f"[ELFRED_SOURCE event_id={event['event_id']} task_key={key}]"
        description = normalize_title(str(raw.get("description") or content.get("summary") or ""))
        output.append({
            "local_key": key,
            "uid": f"elfred-{event['event_id'][:24]}-{key}",
            "payload": {
                "name": title,
                "description": description or None,
                "user_notes": notes,
                "due": parse_due(deadline, str(event["created_at"])),
                "status": status,
                "priority": priority,
                "tags": tags,
                "categories": ",".join(tags) if tags else None,
            },
            "confidence": confidence,
        })
    return output


def deterministic_analysis(event: dict[str, Any]) -> dict[str, list[str]]:
    content = event.get("content") or {}
    text = " ".join(str(content.get(key) or "") for key in ("summary", "clean_text"))
    sentences = [normalize_title(item) for item in re.split(r"[\n。！？!?；;]", text) if normalize_title(item)]

    def select(words: tuple[str, ...]) -> list[str]:
        return [sentence for sentence in sentences if any(word in sentence.casefold() for word in words)][:5]

    return {
        "ideas": select(("想法", "idea", "认识", "发现", "可以")),
        "decisions": select(("决定", "决策", "采用", "选择", "decision")),
        "risks": select(("风险", "阻塞", "问题", "失败", "risk", "bug")),
        "waiting": select(("等待", "依赖", "待确认", "waiting", "blocked")),
    }


def daily_digest(day: str, events: list[dict[str, Any]], todo_ids: list[int], topic_names: list[str]) -> dict[str, Any]:
    summaries: list[str] = []
    tasks: list[str] = []
    analyses = {"ideas": [], "decisions": [], "risks": [], "waiting": []}
    source_ids = []
    for record in events:
        event, _ = safe_event_view(record["payload"]["event"])
        source_ids.append(event["event_id"])
        content = event.get("content") or {}
        summary = normalize_title(str(content.get("summary") or content.get("clean_text") or ""))
        if summary:
            summaries.append(summary)
        for task in content.get("tasks") or []:
            if isinstance(task, dict):
                title = normalize_title(str(task.get("task") or task.get("title") or ""))
                if title:
                    tasks.append(title)
        analysis = deterministic_analysis(event)
        for key in analyses:
            analyses[key].extend(analysis[key])

    def bullets(
        values: list[str],
        empty: str = "无新增记录",
        limit: int | None = 12,
    ) -> str:
        unique = list(dict.fromkeys(values))
        selected = unique if limit is None else unique[:limit]
        return "\n".join(f"- {value}" for value in selected) if selected else f"- {empty}"

    objective = (
        "## 今日主线\n" + bullets(summaries[:3]) +
        "\n\n## 关键进展\n" + bullets(summaries) +
        "\n\n## 任务变化\n" + bullets(tasks, limit=None) +
        "\n\n## 来源索引\n" + bullets(
            [f"ContextEvent `{event_id}`" for event_id in source_ids],
            limit=None,
        )
    )
    ai = (
        "## 新想法与认识\n" + bullets(analyses["ideas"]) +
        "\n\n## 关键决策\n" + bullets(analyses["decisions"]) +
        "\n\n## 风险与卡点\n" + bullets(analyses["risks"]) +
        "\n\n## 等待与依赖\n" + bullets(analyses["waiting"]) +
        "\n\n## 下一步\n" + bullets(tasks[:5], "回顾今日主线并确认下一步")
    )
    uid = f"elfred-daily-{day}"
    return {
        "uid": uid,
        "name": f"Elfred 日报 · {day}",
        "user_notes": f"由 Elfred Adapter 生成；来源事件 {len(source_ids)} 条。",
        "date": f"{day}T12:00:00+08:00",
        "content_format": "markdown",
        "content_objective": objective,
        "content_ai": ai,
        "tags": list(dict.fromkeys(["Elfred", *topic_names])),
        "related_todo_ids": sorted(set(todo_ids)),
        "related_activity_ids": [],
    }


def weekly_digest(week_key: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    # Weekly synthesis groups ideas/decisions/risks; it deliberately does not concatenate daily text.
    themes: dict[str, int] = {}
    analysis = {"ideas": [], "decisions": [], "risks": [], "waiting": []}
    for record in events:
        event, _ = safe_event_view(record["payload"]["event"])
        app = str((event.get("app") or {}).get("category") or "待归类")
        themes[app] = themes.get(app, 0) + 1
        current = deterministic_analysis(event)
        for key in analysis:
            analysis[key].extend(current[key])
    ordered = sorted(themes.items(), key=lambda item: (-item[1], item[0]))
    return {
        "week": week_key,
        "main_threads": [{"theme": name, "event_count": count} for name, count in ordered],
        "ideas": list(dict.fromkeys(analysis["ideas"])),
        "decisions": list(dict.fromkeys(analysis["decisions"])),
        "risks": list(dict.fromkeys(analysis["risks"])),
        "waiting": list(dict.fromkeys(analysis["waiting"])),
        "next_week": list(dict.fromkeys([*analysis["waiting"], *analysis["risks"]]))[:8],
    }
