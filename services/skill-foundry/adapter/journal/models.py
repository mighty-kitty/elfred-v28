"""日报模块数据模型 — 沿用 adapter 的 dataclass 风格"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DayGroup:
    """日报管道的中间数据载体——分组后的事件摘要"""
    date: str
    event_count: int = 0
    summaries: list[str] = field(default_factory=list)
    task_titles: list[str] = field(default_factory=list)
    app_breakdown: dict[str, int] = field(default_factory=dict)
    source_event_ids: list[str] = field(default_factory=list)
    todo_ids: list[int] = field(default_factory=list)
    topic_names: list[str] = field(default_factory=list)
    included_event_count: int = 0
    excluded_event_count: int = 0
    truncated: bool = False


@dataclass
class JournalPayload:
    """FreeTodo journal 写入负载"""
    uid: str
    name: str
    date: str
    content_format: str = "markdown"
    content_objective: str = ""
    content_ai: str = ""
    user_notes: str = ""
    tags: list[str] = field(default_factory=list)
    related_todo_ids: list[int] = field(default_factory=list)
    related_activity_ids: list = field(default_factory=list)


@dataclass
class GenerateRequest:
    """日报生成请求"""
    date: str
    dry_run: bool = False
    max_events: int = 30


@dataclass
class GenerateResponse:
    """日报生成响应"""
    status: str
    journal_id: int | None = None
    payload: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    used_fallback: bool = False
    excluded_event_count: int = 0
