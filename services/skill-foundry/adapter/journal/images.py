from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


JPEG_MIME_TYPES = {"image/jpeg", "image/jpg"}
OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


class JournalImageSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class JournalImage:
    session_id: str
    frame_id: str
    created_at: str
    filename: str
    mime: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class JournalImageBatch:
    images: list[JournalImage]
    warnings: list[str]


class JournalImageLoader:
    def __init__(
        self,
        observer_base_url: str,
        *,
        max_images: int = 6,
        max_image_bytes: int = 3 * 1024 * 1024,
        max_total_bytes: int = 20 * 1024 * 1024,
        timeout_seconds: float = 8.0,
        fetcher: Callable[[str], tuple[str, bytes]] | None = None,
    ) -> None:
        self.base_url = observer_base_url.rstrip("/")
        self.max_images = min(max(int(max_images), 1), 24)
        self.max_image_bytes = min(
            max(int(max_image_bytes), 1024),
            5 * 1024 * 1024,
        )
        self.max_total_bytes = min(
            max(int(max_total_bytes), self.max_image_bytes),
            24 * 1024 * 1024,
        )
        self.timeout_seconds = max(float(timeout_seconds), 0.1)
        self.fetcher = fetcher or self._fetch

    def load(
        self,
        events: list[dict[str, Any]],
        day: str,
    ) -> JournalImageBatch:
        candidates = self._candidates(events, day)
        selected = [
            candidates[index]
            for index in self._representative_indices(
                len(candidates),
                self.max_images,
            )
        ]
        images: list[JournalImage] = []
        warnings: list[str] = []
        total_bytes = 0
        for candidate in selected:
            frame_id = candidate["frame_id"]
            try:
                mime, data = self.fetcher(frame_id)
                self._validate_image(mime, data)
            except Exception:
                warnings.append(f"xiao_frame_unavailable:{frame_id[:8]}")
                continue
            if total_bytes + len(data) > self.max_total_bytes:
                warnings.append("xiao_frame_total_budget_exceeded")
                continue
            total_bytes += len(data)
            images.append(
                JournalImage(
                    session_id=candidate["session_id"],
                    frame_id=frame_id,
                    created_at=candidate["created_at"],
                    filename=self._filename(candidate),
                    mime="image/jpeg",
                    data=data,
                )
            )

        if candidates and not images:
            raise JournalImageSourceError(
                "representative XIAO frames are temporarily unavailable"
            )
        return JournalImageBatch(images=images, warnings=warnings)

    def _fetch(self, frame_id: str) -> tuple[str, bytes]:
        request = urllib.request.Request(
            f"{self.base_url}/xiao/frames/{frame_id}",
            method="GET",
        )
        with urllib.request.urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            mime = str(response.headers.get("Content-Type") or "").split(";", 1)[0]
            data = response.read(self.max_image_bytes + 1)
        return mime.casefold(), data

    def _validate_image(self, mime: str, data: bytes) -> None:
        if str(mime).casefold() not in JPEG_MIME_TYPES:
            raise ValueError("XIAO frame is not JPEG")
        if not data or len(data) > self.max_image_bytes:
            raise ValueError("XIAO frame exceeds the byte limit")
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise ValueError("XIAO frame has an invalid JPEG envelope")

    @staticmethod
    def _candidates(
        events: list[dict[str, Any]],
        day: str,
    ) -> list[dict[str, str]]:
        by_session: dict[str, dict[str, str]] = {}
        for event in events:
            if not str(event.get("created_at") or "").startswith(day):
                continue
            content = event.get("content") or {}
            privacy = event.get("privacy") or {}
            artifacts = event.get("artifacts") or {}
            if content.get("content_type") != "xiao_capture_visual":
                continue
            if privacy.get("allowed_to_upload") is not True:
                continue
            if str(privacy.get("review_status") or "") != "passed":
                continue
            if privacy.get("requires_user_confirmation") is True:
                continue
            session_id = str(artifacts.get("xiao_session_id") or "")
            frame_id = str(artifacts.get("representative_frame_id") or "")
            if not (
                OPAQUE_ID.fullmatch(session_id)
                and OPAQUE_ID.fullmatch(frame_id)
            ):
                continue
            by_session.setdefault(
                session_id,
                {
                    "session_id": session_id,
                    "frame_id": frame_id,
                    "created_at": str(event.get("created_at") or ""),
                },
            )
        return sorted(
            by_session.values(),
            key=lambda item: (item["created_at"], item["session_id"]),
        )

    @staticmethod
    def _representative_indices(item_count: int, limit: int) -> list[int]:
        if item_count <= 0 or limit <= 0:
            return []
        if item_count <= limit:
            return list(range(item_count))
        if limit == 1:
            return [item_count // 2]
        return sorted(
            {
                round(position * (item_count - 1) / (limit - 1))
                for position in range(limit)
            }
        )

    @staticmethod
    def _filename(candidate: dict[str, str]) -> str:
        timestamp = "".join(
            character
            for character in candidate["created_at"][:19]
            if character.isdigit()
        )
        return f"xiao-{timestamp or 'capture'}-{candidate['frame_id']}.jpg"
