from __future__ import annotations

from typing import Any, Protocol


class MemoryAdapter(Protocol):
    def get_user_preferences(self, scope: str) -> list[dict[str, Any]]: ...

    def search_related_experiences(self, query: str) -> list[dict[str, Any]]: ...

    def save_skill_learning(self, event: dict[str, Any]) -> None: ...


class NullMemoryAdapter:
    """MVP boundary for the future EMOS-backed implementation."""

    def get_user_preferences(self, scope: str) -> list[dict[str, Any]]:
        return []

    def search_related_experiences(self, query: str) -> list[dict[str, Any]]:
        return []

    def save_skill_learning(self, event: dict[str, Any]) -> None:
        return None


class LocalMemoryAdapter:
    """Small local adapter using the Adapter settings table."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def get_user_preferences(self, scope: str) -> list[dict[str, Any]]:
        value = self.store.get_setting(f"skill_preferences:{scope}", [])
        return list(value) if isinstance(value, list) else []

    def search_related_experiences(self, query: str) -> list[dict[str, Any]]:
        value = self.store.get_setting("skill_learning_events", [])
        if not isinstance(value, list):
            return []
        terms = {part.casefold() for part in query.split() if part}
        return [
            item
            for item in value[-100:]
            if terms.intersection(str(item).casefold().split())
        ][-20:]

    def save_skill_learning(self, event: dict[str, Any]) -> None:
        current = self.store.get_setting("skill_learning_events", [])
        events = list(current) if isinstance(current, list) else []
        events.append(event)
        self.store.set_setting("skill_learning_events", events[-200:])
