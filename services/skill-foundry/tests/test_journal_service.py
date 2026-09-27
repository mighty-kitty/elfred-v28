from __future__ import annotations

import pytest

from adapter.journal.generator import JournalGenerationError
from adapter.journal.images import (
    JournalImage,
    JournalImageBatch,
    JournalImageSourceError,
)
from adapter.journal.models import GenerateRequest
from adapter.journal.service import JournalService, JournalSourceError


def _fake_events(count: int, date: str = "2026-07-30") -> list[dict]:
    return [
        {
            "event_id": str(i),
            "created_at": f"{date}T09:00:{i:02d}+08:00",
            "app": {"name": "Code", "category": "development"},
            "content": {"summary": f"Event {i}", "tasks": []},
        }
        for i in range(count)
    ]


def test_skips_when_no_events():
    svc = JournalService(None)
    resp = svc.generate(GenerateRequest(date="2026-07-30"), events=[])
    assert resp.status == "skipped_no_events"


def test_missing_source_snapshot_fails_closed():
    svc = JournalService(None)

    with pytest.raises(JournalSourceError):
        svc.generate(GenerateRequest(date="2026-07-30"), events=None)


def test_fallback_when_no_generator():
    svc = JournalService(None)
    resp = svc.generate(GenerateRequest(date="2026-07-30"), events=_fake_events(5))
    assert resp.used_fallback is True
    assert resp.payload
    assert "Event 0" in resp.payload.get("content_objective", "")


def test_fallback_when_llm_fails():
    """LLM 调用失败 → 降级输出"""

    class FailingGenerator:
        def generate(self, prompt: str) -> str:
            raise JournalGenerationError("mock failure")

    svc = JournalService(FailingGenerator())  # type: ignore[arg-type]
    resp = svc.generate(GenerateRequest(date="2026-07-30"), events=_fake_events(5))
    assert resp.used_fallback is True
    assert resp.payload
    assert resp.warnings


def test_llm_generated_on_success():
    """LLM 正常返回 → used_fallback=False"""

    class SuccessGenerator:
        def generate(self, prompt: str) -> str:
            return '{"summary_line":"today","main_thread":"done","key_progress":["a"],"task_changes":"","ideas_and_insights":[],"decisions":[],"risks_and_blockers":[],"waiting_on":[],"next_steps":[],"mood_and_energy":null}'

    svc = JournalService(SuccessGenerator())  # type: ignore[arg-type]
    resp = svc.generate(GenerateRequest(date="2026-07-30"), events=_fake_events(5))
    assert resp.used_fallback is False
    assert "today" in resp.payload.get("content_objective", "")
    assert "a" in resp.payload.get("content_ai", "")


def test_malformed_json_gets_one_bounded_model_repair_before_queue_retry():
    class RepairingGenerator:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def generate(self, prompt: str) -> str:
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return '{"summary_line":"today","main_thread" "broken"}'
            return '{"summary_line":"today","main_thread":"fixed","key_progress":["a"],"task_changes":"","ideas_and_insights":[],"decisions":[],"risks_and_blockers":[],"waiting_on":[],"next_steps":[],"mood_and_energy":null}'

    generator = RepairingGenerator()
    response = JournalService(generator).generate(  # type: ignore[arg-type]
        GenerateRequest(date="2026-07-30"),
        events=_fake_events(5),
        fallback_on_error=False,
    )

    assert response.status == "llm_generated"
    assert response.used_fallback is False
    assert response.warnings == ["journal_json_model_repair_attempted"]
    assert len(generator.prompts) == 2
    assert "BEGIN_UNTRUSTED_MALFORMED_JOURNAL_JSON" in generator.prompts[1]
    assert "fixed" in response.payload.get("content_objective", "")


def _xiao_visual_event() -> dict:
    return {
        "event_id": "xiao-visual-1",
        "created_at": "2026-07-30T10:00:00+08:00",
        "source": "xiao_pendant",
        "app": {"name": "Elfred Pendant", "category": "capture"},
        "content": {
            "content_type": "xiao_capture_visual",
            "summary": "Pendant session completed",
            "tasks": [],
        },
        "privacy": {
            "is_sensitive": False,
            "sensitivity_types": [],
            "action": "allow",
            "allowed_to_upload": True,
            "review_status": "passed",
            "requires_user_confirmation": False,
        },
        "artifacts": {
            "xiao_session_id": "a" * 32,
            "representative_frame_id": "b" * 32,
            "frame_count": 12,
        },
    }


def test_service_sends_voice_text_and_frames_to_one_image_aware_call() -> None:
    image = JournalImage(
        session_id="a" * 32,
        frame_id="b" * 32,
        created_at="2026-07-30T10:00:00+08:00",
        filename="xiao-20260730100000-frame.jpg",
        mime="image/jpeg",
        data=b"\xff\xd8\xff\xd9",
    )

    class RecordingLoader:
        events: list[dict] | None = None
        day = ""

        def load(self, events: list[dict], day: str) -> JournalImageBatch:
            self.events = events
            self.day = day
            return JournalImageBatch(images=[image], warnings=["partial-warning"])

    class RecordingGenerator:
        calls: list[tuple[str, list[JournalImage]]]

        def __init__(self) -> None:
            self.calls = []

        def generate(self, _prompt: str) -> str:
            raise AssertionError("text-only generation must not be used")

        def generate_with_images(
            self,
            prompt: str,
            images: list[JournalImage],
        ) -> str:
            self.calls.append((prompt, images))
            return '{"summary_line":"today","main_thread":"done","key_progress":["a"],"task_changes":"","ideas_and_insights":[],"decisions":[],"risks_and_blockers":[],"waiting_on":[],"next_steps":[],"mood_and_energy":null}'

    voice_event = _fake_events(1)[0]
    voice_event["content"] = {
        "content_type": "voice_transcription",
        "clean_text": "Voice decision from the pendant",
        "tasks": [],
    }
    loader = RecordingLoader()
    generator = RecordingGenerator()

    response = JournalService(  # type: ignore[arg-type]
        generator,
        loader,
    ).generate(
        GenerateRequest(date="2026-07-30"),
        events=[voice_event, _xiao_visual_event()],
    )

    assert response.status == "llm_generated"
    assert response.warnings == ["partial-warning"]
    assert loader.day == "2026-07-30"
    assert loader.events is not None
    assert len(generator.calls) == 1
    prompt, images = generator.calls[0]
    assert "Voice decision from the pendant" in prompt
    assert images == [image]


def test_image_source_failure_is_retryable_without_fallback() -> None:
    class FailingLoader:
        def load(
            self,
            _events: list[dict],
            _day: str,
        ) -> JournalImageBatch:
            raise JournalImageSourceError("observer frame source unavailable")

    class GeneratorMustNotRun:
        def generate(self, _prompt: str) -> str:
            raise AssertionError("generator must not run without requested frames")

    response = JournalService(  # type: ignore[arg-type]
        GeneratorMustNotRun(),
        FailingLoader(),
    ).generate(
        GenerateRequest(date="2026-07-30"),
        events=[_xiao_visual_event()],
        fallback_on_error=False,
    )

    assert response.status == "generation_failed"
    assert response.payload is None
    assert response.used_fallback is False
    assert response.warnings == ["observer frame source unavailable"]


def test_journal_llm_receives_voice_and_screenshot_text_together():
    class CapturingGenerator:
        prompt = ""

        def generate(self, prompt: str) -> str:
            self.prompt = prompt
            return '{"summary_line":"today","main_thread":"done","key_progress":["a"],"task_changes":"","ideas_and_insights":[],"decisions":[],"risks_and_blockers":[],"waiting_on":[],"next_steps":[],"mood_and_energy":null}'

    generator = CapturingGenerator()
    events = [
        {
            "event_id": "voice-1",
            "created_at": "2026-07-30T09:00:00+08:00",
            "app": {"name": "Elfred Pendant", "type": "voice"},
            "content": {
                "content_type": "voice_transcription",
                "clean_text": "语音里记录了今天的设计决定",
                "tasks": [],
            },
        },
        {
            "event_id": "screen-1",
            "created_at": "2026-07-30T10:00:00+08:00",
            "app": {"name": "Code", "type": "screen"},
            "content": {
                "content_type": "work_log",
                "summary": "截图显示实现已经通过测试",
                "tasks": [],
            },
        },
    ]

    service = JournalService(generator)  # type: ignore[arg-type]
    response = service.generate(
        GenerateRequest(date="2026-07-30"),
        events=events,
    )

    assert response.status == "llm_generated"
    assert "语音里记录了今天的设计决定" in generator.prompt
    assert "截图显示实现已经通过测试" in generator.prompt
