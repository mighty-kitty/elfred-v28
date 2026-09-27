"""日报服务编排 — 对标 skill_foundry/service.py"""

from __future__ import annotations

import logging
from typing import Any

from adapter.journal.generator import JournalGenerationError, JournalGenerator
from adapter.journal.images import (
    JournalImageLoader,
    JournalImageSourceError,
)
from adapter.journal.grouper import EventGrouper
from adapter.journal.models import GenerateRequest, GenerateResponse
from adapter.journal.parser import JournalParseError, JournalParser
from adapter.journal.prompt import PromptBuilder
from adapter.privacy import decide, safe_event_view

logger = logging.getLogger("elfred.journal")


class JournalSourceError(RuntimeError):
    """Raised when generation is attempted without an authoritative source."""


class JournalService:
    """Pure privacy-safe Journal candidate generation."""

    def __init__(
        self,
        generator: JournalGenerator | None = None,
        image_loader: JournalImageLoader | None = None,
    ) -> None:
        self._grouper = EventGrouper()
        self._prompt = PromptBuilder()
        self._generator = generator
        self._parser = JournalParser()
        self._image_loader = image_loader

    @property
    def enabled(self) -> bool:
        return self._generator is not None

    @property
    def grouper(self) -> EventGrouper:
        return self._grouper

    def generate(self, request: GenerateRequest, events: list[dict[str, Any]] | None = None,
                 todo_ids: list[int] | None = None,
                 topic_names: list[str] | None = None,
                 *, fallback_on_error: bool = True) -> GenerateResponse:
        """Generate a candidate from an explicitly supplied event snapshot."""
        if events is None:
            raise JournalSourceError(
                "Journal generation requires an explicit local event snapshot"
            )
        warnings: list[str] = []
        safe_events, excluded_count = self.privacy_safe_events(events or [])
        if excluded_count:
            warnings.append(f"privacy_excluded_events:{excluded_count}")

        # 1. Group
        group = self._grouper.build(
            safe_events,
            request.date,
            todo_ids,
            topic_names,
            request.max_events,
        )
        group.excluded_event_count = excluded_count
        if not group.event_count:
            return GenerateResponse(
                status=("skipped_privacy" if excluded_count else "skipped_no_events"),
                warnings=warnings,
                excluded_event_count=excluded_count,
            )

        # 2. Prompt
        prompt = self._prompt.build(group)

        images = []
        if self._generator and self._image_loader:
            try:
                batch = self._image_loader.load(safe_events, request.date)
                images = batch.images
                warnings.extend(batch.warnings)
            except JournalImageSourceError as exc:
                warnings.append(str(exc))
                if not fallback_on_error:
                    return GenerateResponse(
                        status="generation_failed",
                        warnings=warnings,
                        excluded_event_count=excluded_count,
                    )

        # 3. Generate + Parse
        if self._generator:
            try:
                image_generate = getattr(
                    self._generator,
                    "generate_with_images",
                    None,
                )
                raw = (
                    image_generate(prompt, images)
                    if images and callable(image_generate)
                    else self._generator.generate(prompt)
                )
                try:
                    payload = self._parser.parse(raw, group)
                except JournalParseError:
                    start = raw.find("{")
                    end = raw.rfind("}")
                    if start < 0 or end <= start:
                        raise
                    warnings.append("journal_json_model_repair_attempted")
                    repaired = self._generator.generate(
                        self._prompt.build_repair(raw)
                    )
                    payload = self._parser.parse(repaired, group)
                return GenerateResponse(
                    status="llm_generated" if not request.dry_run else "dry_run",
                    payload=_asdict(payload),
                    warnings=warnings,
                    excluded_event_count=excluded_count,
                )
            except (JournalGenerationError, JournalParseError) as exc:
                logger.warning("LLM journal failed: %s", exc)
                warnings.append(str(exc))
                if not fallback_on_error:
                    return GenerateResponse(
                        status="generation_failed",
                        warnings=warnings,
                        excluded_event_count=excluded_count,
                    )

        # Fallback
        payload = self._parser.fallback(group)
        return GenerateResponse(
            status="fallback" if not request.dry_run else "dry_run",
            payload=_asdict(payload),
            warnings=warnings,
            used_fallback=True,
            excluded_event_count=excluded_count,
        )

    @staticmethod
    def privacy_safe_events(
        events: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        safe_events: list[dict[str, Any]] = []
        excluded = 0
        for event in events:
            decision = decide(event)
            requires_confirmation = bool(
                (event.get("privacy") or {}).get("requires_user_confirmation")
            )
            if not decision.local_allowed or requires_confirmation:
                excluded += 1
                continue
            safe_event, _ = safe_event_view(event)
            safe_events.append(safe_event)
        return safe_events, excluded

def _asdict(obj: Any) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(obj)
