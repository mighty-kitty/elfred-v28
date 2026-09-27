"""事件分组器 — 从 Observer 事件中提取结构化摘要"""

from __future__ import annotations

from typing import Any

from adapter.journal.models import DayGroup


class EventGrouper:
    """把 Observer 事件列表按日期过滤，提取摘要/任务/应用分布"""

    def build(self, events: list[dict[str, Any]], target_date: str,
              todo_ids: list[int] | None = None,
              topic_names: list[str] | None = None,
              max_events: int = 30) -> DayGroup:
        """一站式构建：过滤→提取→打包"""
        day_events = sorted(
            (
                event
                for event in events
                if str(event.get("created_at") or "").startswith(target_date)
            ),
            key=lambda event: (
                str(event.get("created_at") or ""),
                str(event.get("event_id") or ""),
            ),
        )
        prompt_events = self._representative_events(day_events, max_events)

        return DayGroup(
            date=target_date,
            event_count=len(day_events),
            summaries=self._extract_summaries(prompt_events),
            # Structured task evidence is compact and must represent the full day;
            # max_events only bounds free-text event detail.
            task_titles=self._extract_tasks(day_events),
            app_breakdown=self._extract_apps(day_events),
            source_event_ids=[str(e.get("event_id") or "") for e in prompt_events],
            todo_ids=todo_ids or [],
            topic_names=topic_names or [],
            included_event_count=len(prompt_events),
            truncated=len(prompt_events) < len(day_events),
        )

    def _representative_events(
        self,
        events: list[dict[str, Any]],
        max_events: int,
    ) -> list[dict[str, Any]]:
        """Select stable, day-spanning evidence while retaining high-value events."""

        limit = max(1, int(max_events))
        if len(events) <= limit:
            return list(events)

        priority = [
            (self._priority(event), index)
            for index, event in enumerate(events)
            if self._priority(event) > 0
        ]
        priority.sort(
            key=lambda item: (
                -item[0],
                str(events[item[1]].get("created_at") or ""),
                str(events[item[1]].get("event_id") or ""),
            )
        )
        priority_budget = min(len(priority), max(1, limit // 3))
        selected = {index for _, index in priority[:priority_budget]}

        candidates = [index for index in range(len(events)) if index not in selected]
        needed = limit - len(selected)
        if needed == 1:
            selected.add(candidates[len(candidates) // 2])
        elif needed > 1:
            for position in range(needed):
                candidate_position = round(
                    position * (len(candidates) - 1) / (needed - 1)
                )
                selected.add(candidates[candidate_position])

        if len(selected) < limit:
            for index in candidates:
                selected.add(index)
                if len(selected) == limit:
                    break
        return [events[index] for index in sorted(selected)[:limit]]

    @staticmethod
    def _priority(event: dict[str, Any]) -> int:
        content = event.get("content") or {}
        content_type = str(content.get("content_type") or "").casefold()
        text = " ".join(
            str(content.get(field) or "")
            for field in ("summary", "clean_text")
        ).casefold()
        score = 0
        if "voice" in content_type or "transcri" in content_type:
            score += 8
        if content.get("tasks"):
            score += 6
        if any(
            marker in text
            for marker in (
                "决定", "决策", "风险", "阻塞", "卡点", "等待",
                "decision", "risk", "blocker", "blocked", "waiting",
            )
        ):
            score += 4
        return score

    def _extract_summaries(self, events: list[dict[str, Any]]) -> list[str]:
        """从每事件提取摘要文本，加上时间戳和应用名，去重"""
        seen: set[str] = set()
        result: list[str] = []
        for ev in events:
            content = ev.get("content") or {}
            text = content.get("summary") or content.get("clean_text") or ""
            text = " ".join(str(text).split())[:1200]
            if not text or text in seen:
                continue
            seen.add(text)
            app = (ev.get("app") or {}).get("name", "")
            ts = (ev.get("created_at") or "")[11:16]
            prefix = f"{ts} [{app}] " if app else f"{ts} "
            result.append(f"{len(result) + 1}. {prefix}{text}")
        return result

    def _extract_tasks(self, events: list[dict[str, Any]]) -> list[str]:
        """提取事件中关联的任务标题，去重"""
        seen: set[str] = set()
        tasks: list[str] = []
        for ev in events:
            for t in (ev.get("content") or {}).get("tasks") or []:
                title = str(t.get("task") or t.get("title") or "").strip()[:500]
                if title and title not in seen:
                    seen.add(title)
                    tasks.append(title)
        return tasks

    def _extract_apps(self, events: list[dict[str, Any]]) -> dict[str, int]:
        """按应用类别统计事件数，降序"""
        counts: dict[str, int] = {}
        for ev in events:
            app = ev.get("app") or {}
            cat = app.get("category") or app.get("name") or "未知"
            counts[cat] = counts.get(cat, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
