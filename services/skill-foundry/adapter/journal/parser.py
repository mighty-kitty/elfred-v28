"""LLM 响应解析器 — JSON → JournalPayload"""

from __future__ import annotations

import json
from typing import Any

from adapter.journal.models import DayGroup, JournalPayload


class JournalParseError(ValueError):
    """LLM 响应解析失败"""


class JournalParser:
    """解析 LLM 返回的 JSON，映射为 JournalPayload"""

    def parse(self, raw_text: str, group: DayGroup) -> JournalPayload:
        """主入口：提取 JSON → 验证 → 映射"""
        parsed = self._extract_json(raw_text)
        return self._build_payload(parsed, group)

    def fallback(self, group: DayGroup) -> JournalPayload:
        """LLM 失败时的降级日报"""
        return JournalPayload(
            uid=f"elfred-daily-{group.date}",
            name=f"Elfred 日报 · {group.date}",
            date=f"{group.date}T12:00:00+08:00",
            content_objective="## 事件摘要\n\n" + "\n".join(f"- {s}" for s in group.summaries),
            content_ai="（LLM 日记生成失败，已使用确定性摘要作为备选。）",
            user_notes=f"由 Elfred fallback 生成；来源事件 {group.event_count} 条。",
            tags=["Elfred"] + group.topic_names,
            related_todo_ids=group.todo_ids,
        )

    # --- private ---

    def _extract_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if not text:
            raise JournalParseError("Empty LLM response")
        # 去掉 ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            elif lines[0].startswith("```"):
                lines = lines[1:]
            text = "\n".join(lines)
        # 找 JSON 边界
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise JournalParseError("LLM response must be a JSON object")
            return parsed
        except json.JSONDecodeError:
            pass
        # 第一次失败 → 尝试自动修复
        try:
            from adapter.json_repair import repair_json
            repaired = repair_json(text)
            parsed = json.loads(repaired)
            if not isinstance(parsed, dict):
                raise JournalParseError("LLM response must be a JSON object")
            return parsed
        except Exception as exc:
            raise JournalParseError(f"JSON parse failed: {exc}") from exc

    def _build_payload(self, parsed: dict[str, Any], group: DayGroup) -> JournalPayload:
        parsed = self._validate(parsed)
        return JournalPayload(
            uid=f"elfred-daily-{group.date}",
            name=f"Elfred 日报 · {group.date}",
            date=f"{group.date}T12:00:00+08:00",
            content_objective=self._build_objective(parsed),
            content_ai=self._build_ai(parsed),
            user_notes=f"由 Elfred LLM 日报引擎生成；来源事件 {group.event_count} 条。",
            tags=["Elfred"] + group.topic_names,
            related_todo_ids=group.todo_ids,
        )

    def _validate(self, parsed: dict[str, Any]) -> dict[str, Any]:
        text_limits = {
            "summary_line": 500,
            "main_thread": 8000,
            "task_changes": 2500,
            "mood_and_energy": 1200,
        }
        list_fields = {
            "key_progress",
            "ideas_and_insights",
            "decisions",
            "risks_and_blockers",
            "waiting_on",
            "next_steps",
        }
        output: dict[str, Any] = {}
        for field, limit in text_limits.items():
            value = parsed.get(field)
            if value is None:
                output[field] = None
                continue
            if not isinstance(value, str):
                raise JournalParseError(f"{field} must be a string or null")
            value = value.strip()
            if len(value) > limit:
                raise JournalParseError(f"{field} exceeds {limit} characters")
            output[field] = value
        for field in list_fields:
            value = parsed.get(field, [])
            if value is None:
                value = []
            if not isinstance(value, list):
                raise JournalParseError(f"{field} must be an array")
            if len(value) > 5:
                raise JournalParseError(f"{field} must contain at most 5 items")
            items: list[str] = []
            for item in value:
                if not isinstance(item, str):
                    raise JournalParseError(f"{field} items must be strings")
                item = item.strip()
                if len(item) > 1000:
                    raise JournalParseError(
                        f"{field} item exceeds 1000 characters"
                    )
                if item:
                    items.append(item)
            output[field] = items
        return output

    def _build_objective(self, parsed: dict[str, Any]) -> str:
        parts: list[str] = []
        if s := parsed.get("summary_line"):
            parts.append(f"## 今日概要\n{s}")
        if m := parsed.get("main_thread"):
            parts.append(f"## 主线\n{m}")
        return "\n\n".join(parts) or "（无数据）"

    def _build_ai(self, parsed: dict[str, Any]) -> str:
        sections = [
            ("关键进展", parsed.get("key_progress")),
            ("任务变化", parsed.get("task_changes")),
            ("新想法与认识", parsed.get("ideas_and_insights")),
            ("关键决策", parsed.get("decisions")),
            ("风险与卡点", parsed.get("risks_and_blockers")),
            ("等待与依赖", parsed.get("waiting_on")),
            ("下一步", parsed.get("next_steps")),
        ]
        result: list[str] = []
        for title, value in sections:
            if not value:
                continue
            if isinstance(value, list):
                result.append(f"## {title}\n" + "\n".join(f"- {item}" for item in value))
            elif isinstance(value, str) and value.strip():
                result.append(f"## {title}\n{value}")
        if mood := parsed.get("mood_and_energy"):
            result.append(f"## 状态感知\n{mood}")
        return "\n\n".join(result) or "（无数据）"
