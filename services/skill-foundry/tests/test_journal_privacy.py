from __future__ import annotations

import json

import pytest

from adapter.journal.models import GenerateRequest
from adapter.journal.service import JournalService
from adapter.privacy import safe_event_view


class CapturingGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "summary_line": "today",
                "main_thread": "done",
                "key_progress": ["progress"],
                "task_changes": "",
                "ideas_and_insights": [],
                "decisions": [],
                "risks_and_blockers": [],
                "waiting_on": [],
                "next_steps": [],
                "mood_and_energy": None,
            }
        )


def _event(event_id: str, text: str, **privacy) -> dict:
    return {
        "event_id": event_id,
        "created_at": "2026-07-30T09:00:00+08:00",
        "source": "desktop_observer",
        "app": {"name": "Code", "category": "development"},
        "content": {"summary": text, "clean_text": text, "tasks": []},
        "privacy": {
            "is_sensitive": False,
            "sensitivity_types": [],
            "action": "allow",
            "requires_user_confirmation": False,
            "allowed_to_upload": False,
            **privacy,
        },
    }


def test_only_automatically_safe_redacted_events_reach_journal_model():
    generator = CapturingGenerator()
    service = JournalService(generator)  # type: ignore[arg-type]
    events = [
        _event("safe", "contact owner@example.com about release"),
        _event("sensitive", "private roadmap", is_sensitive=True),
        _event("blocked", "blocked secret", action="block"),
        _event("pending", "waiting for approval", requires_user_confirmation=True),
        _event("credential", "token=super-secret-value"),
    ]

    response = service.generate(GenerateRequest(date="2026-07-30"), events=events)

    assert response.status == "llm_generated"
    assert len(generator.prompts) == 1
    prompt = generator.prompts[0]
    assert "owner@example.com" not in prompt
    assert "[REDACTED_EMAIL]" in prompt
    assert "private roadmap" not in prompt
    assert "blocked secret" not in prompt
    assert "waiting for approval" not in prompt
    assert "super-secret-value" not in prompt
    assert response.excluded_event_count == 4


def test_safe_voice_and_screenshot_events_do_not_require_manual_upload_flag():
    generator = CapturingGenerator()
    service = JournalService(generator)  # type: ignore[arg-type]
    events = [
        _event("voice", "voice design decision"),
        _event("screen", "screenshot implementation result"),
    ]

    response = service.generate(GenerateRequest(date="2026-07-30"), events=events)

    assert response.status == "llm_generated"
    assert "voice design decision" in generator.prompts[0]
    assert "screenshot implementation result" in generator.prompts[0]


def _xiao_visual_event(**overrides) -> dict:
    event = {
        "event_id": "xiao-visual-1",
        "created_at": "2026-07-30T11:00:00+08:00",
        "source": "xiao_pendant",
        "app": {"name": "Elfred Pendant", "category": "capture"},
        "content": {
            "content_type": "xiao_capture_visual",
            "summary": "Pendant capture completed",
            "tasks": [],
        },
        "privacy": {
            "allowed_to_upload": True,
            "review_status": "passed",
            "requires_user_confirmation": False,
        },
        "artifacts": {
            "xiao_session_id": "a" * 32,
            "representative_frame_id": "b" * 32,
            "frame_count": 200_000,
            "frame_path": r"C:\Users\person\private\frame.jpg",
            "frame_url": "http://observer/internal/frame.jpg",
            "audio_path": r"C:\Users\person\private\audio.wav",
            "extra": {"filename": "private.jpg"},
        },
    }
    event.update(overrides)
    return event


def test_safe_event_view_keeps_only_bounded_xiao_opaque_artifacts() -> None:
    view, _ = safe_event_view(_xiao_visual_event())

    assert view["artifacts"] == {
        "xiao_session_id": "a" * 32,
        "representative_frame_id": "b" * 32,
        "frame_count": 100_000,
    }
    assert view["privacy"]["allowed_to_upload"] is True
    assert view["privacy"]["review_status"] == "passed"
    serialized = json.dumps(view)
    assert "private" not in serialized
    assert "http://" not in serialized


def test_safe_event_view_drops_non_xiao_artifacts_and_locations() -> None:
    event = _event("desktop", "ordinary screenshot")
    event["artifacts"] = {
        "screenshot_id": "screen-1",
        "path": r"C:\Users\person\private\screenshot.png",
        "url": "http://observer/screens/screen-1",
    }

    view, _ = safe_event_view(event)

    assert "artifacts" not in view
    assert "allowed_to_upload" not in view["privacy"]
    assert "review_status" not in view["privacy"]


@pytest.mark.parametrize(
    "override",
    [
        {"source": "desktop_observer"},
        {"content": {"content_type": "voice_transcription"}},
        {
            "artifacts": {
                "xiao_session_id": "A" * 32,
                "representative_frame_id": "b" * 32,
            }
        },
        {
            "artifacts": {
                "xiao_session_id": "a" * 32,
                "representative_frame_id": "not-opaque",
            }
        },
    ],
)
def test_safe_event_view_rejects_non_xiao_or_invalid_artifacts(
    override: dict,
) -> None:
    view, _ = safe_event_view(_xiao_visual_event(**override))

    assert "artifacts" not in view
