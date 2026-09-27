from __future__ import annotations

from typing import Any

from adapter.storage import SQLiteStore


TOPIC_SEED = [
    ("topic_elfred", "Elfred", ["阿福", "Elfred项目", "Personal Agent项目", "PersonalAgent"]),
    ("topic_research", "科研", ["研究", "论文", "research"]),
    ("topic_development", "开发", ["编程", "代码", "Codex", "development"]),
    ("topic_work", "工作", ["办公", "项目工作"]),
    ("topic_life", "生活", ["个人", "日常"]),
    ("topic_inbox", "待归类", ["Inbox", "未分类"]),
]


class TopicRegistry:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        for topic_id, name, aliases in TOPIC_SEED:
            self.store.seed_topic(topic_id, name, aliases)

    def resolve_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        event_id = event["event_id"]
        content = event.get("content") or {}
        candidates: list[tuple[str, float]] = []
        for task in content.get("tasks") or []:
            if isinstance(task, dict) and task.get("project"):
                candidates.append((str(task["project"]), float(task.get("confidence") or 0.8)))
        for entity in content.get("entities") or []:
            if isinstance(entity, dict) and str(entity.get("type") or "").casefold() in {"project", "topic", "product"}:
                candidates.append((str(entity.get("text") or ""), 0.9))
        app_category = str((event.get("app") or {}).get("category") or "")
        if "research" in app_category:
            candidates.append(("科研", 0.9))
        elif app_category:
            candidates.append(("工作", 0.75))
        unique: dict[str, tuple[str, float]] = {}
        for name, confidence in candidates:
            normalized = self.store.normalize_topic(name)
            if normalized and (normalized not in unique or confidence > unique[normalized][1]):
                unique[normalized] = (name, confidence)
        if not unique:
            unique["inbox"] = ("待归类", 1.0)
        topics = [self.store.resolve_topic(name, event_id, confidence) for name, confidence in unique.values()]
        # Preserve stable ordering while avoiding aliases resolving to the same topic.
        return list({topic["topic_id"]: topic for topic in topics}.values())
