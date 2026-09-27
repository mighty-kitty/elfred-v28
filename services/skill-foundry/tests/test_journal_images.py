from __future__ import annotations

from collections.abc import Callable

import pytest

from adapter.journal.images import JournalImageLoader, JournalImageSourceError


DAY = "2026-08-02"
VALID_JPEG = b"\xff\xd8payload\xff\xd9"


def _opaque(value: int) -> str:
    return f"{value:032x}"


def _jpeg(size: int) -> bytes:
    return b"\xff\xd8" + (b"x" * (size - 4)) + b"\xff\xd9"


def _event(
    index: int,
    *,
    session_id: str | None = None,
    frame_id: str | None = None,
    day: str = DAY,
    content_type: str = "xiao_capture_visual",
    allowed_to_upload: bool = True,
    review_status: str = "passed",
    requires_confirmation: bool = False,
) -> dict:
    return {
        "event_id": f"event-{index}",
        "created_at": f"{day}T{index:02d}:00:00+08:00",
        "source": "xiao_pendant",
        "app": {"name": "Elfred Pendant", "category": "capture"},
        "content": {
            "content_type": content_type,
            "summary": f"capture {index}",
            "tasks": [],
        },
        "privacy": {
            "allowed_to_upload": allowed_to_upload,
            "review_status": review_status,
            "requires_user_confirmation": requires_confirmation,
        },
        "artifacts": {
            "xiao_session_id": session_id or _opaque(index + 1),
            "representative_frame_id": frame_id or _opaque(index + 101),
        },
    }


def _loader(
    fetcher: Callable[[str], tuple[str, bytes]],
    **kwargs,
) -> JournalImageLoader:
    return JournalImageLoader("http://observer", fetcher=fetcher, **kwargs)


def test_load_keeps_one_safe_visual_frame_per_session() -> None:
    first_session = _opaque(1)
    first_frame = _opaque(101)
    fetched: list[str] = []

    def fetcher(frame_id: str) -> tuple[str, bytes]:
        fetched.append(frame_id)
        return "image/jpeg", VALID_JPEG

    events = [
        _event(1, session_id=first_session, frame_id=first_frame),
        _event(2, session_id=first_session, frame_id=_opaque(102)),
        _event(3, content_type="voice_transcription"),
        _event(4, allowed_to_upload=False),
        _event(5, review_status="pending"),
        _event(6, requires_confirmation=True),
        _event(7, day="2026-08-01"),
        _event(8),
    ]

    batch = _loader(fetcher, max_images=8).load(events, DAY)

    assert fetched == [first_frame, _opaque(109)]
    assert [image.session_id for image in batch.images] == [
        first_session,
        _opaque(9),
    ]
    assert batch.warnings == []


def test_load_samples_representative_sessions_across_the_day() -> None:
    fetched: list[str] = []

    def fetcher(frame_id: str) -> tuple[str, bytes]:
        fetched.append(frame_id)
        return "image/jpeg", VALID_JPEG

    events = [_event(index) for index in range(7)]

    batch = _loader(fetcher, max_images=3).load(events, DAY)

    assert fetched == [_opaque(101), _opaque(104), _opaque(107)]
    assert [image.created_at[11:13] for image in batch.images] == [
        "00",
        "03",
        "06",
    ]


@pytest.mark.parametrize(
    ("session_id", "frame_id"),
    [
        ("A" * 32, _opaque(101)),
        ("g" * 32, _opaque(101)),
        ("a" * 31, _opaque(101)),
        (_opaque(1), "B" * 32),
        (_opaque(1), "z" * 32),
        (_opaque(1), "b" * 31),
    ],
)
def test_load_rejects_non_opaque_identifiers(
    session_id: str,
    frame_id: str,
) -> None:
    fetched: list[str] = []

    def fetcher(requested_frame_id: str) -> tuple[str, bytes]:
        fetched.append(requested_frame_id)
        return "image/jpeg", VALID_JPEG

    batch = _loader(fetcher).load(
        [_event(1, session_id=session_id, frame_id=frame_id)],
        DAY,
    )

    assert batch.images == []
    assert fetched == []


@pytest.mark.parametrize(
    ("mime", "data"),
    [
        ("image/png", VALID_JPEG),
        ("image/jpeg", b"not-a-jpeg"),
        ("image/jpeg", _jpeg(1025)),
    ],
)
def test_load_rejects_invalid_or_oversized_jpegs(
    mime: str,
    data: bytes,
) -> None:
    loader = _loader(
        lambda _frame_id: (mime, data),
        max_image_bytes=1024,
    )

    with pytest.raises(JournalImageSourceError):
        loader.load([_event(1)], DAY)


def test_load_warns_on_partial_fetch_failure_and_keeps_successes() -> None:
    failed_frame = _opaque(101)

    def fetcher(frame_id: str) -> tuple[str, bytes]:
        if frame_id == failed_frame:
            raise OSError("observer unavailable")
        return "image/jpeg", VALID_JPEG

    batch = _loader(fetcher).load([_event(0), _event(1)], DAY)

    assert [image.frame_id for image in batch.images] == [_opaque(102)]
    assert batch.warnings == [f"xiao_frame_unavailable:{failed_frame[:8]}"]


def test_load_enforces_total_byte_budget() -> None:
    batch = _loader(
        lambda _frame_id: ("image/jpeg", _jpeg(700)),
        max_image_bytes=1024,
        max_total_bytes=1024,
    ).load([_event(0), _event(1)], DAY)

    assert len(batch.images) == 1
    assert batch.warnings == ["xiao_frame_total_budget_exceeded"]


def test_load_raises_retryable_error_when_all_selected_frames_fail() -> None:
    def fetcher(_frame_id: str) -> tuple[str, bytes]:
        raise TimeoutError("temporary observer timeout")

    with pytest.raises(
        JournalImageSourceError,
        match="temporarily unavailable",
    ):
        _loader(fetcher).load([_event(0), _event(1)], DAY)
