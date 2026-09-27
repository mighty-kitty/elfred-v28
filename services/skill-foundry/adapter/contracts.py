from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class ContextEvent(BaseModel):
    """Forward-compatible copy of Observer's real event contract."""

    model_config = ConfigDict(extra="allow")

    event_id: str = Field(min_length=1)
    created_at: datetime
    source: str = "desktop_observer"
    app: dict[str, Any] = Field(default_factory=dict)
    trigger: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    privacy: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    suggestions: dict[str, Any] = Field(default_factory=dict)
    status: str = "temporary_context"

    @field_validator("event_id", "source", "status")
    @classmethod
    def strip_strings(cls, value: str) -> str:
        return value.strip()


class ContextEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    producer: str = "elfred_desktop_observer"
    received_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    event: ContextEvent


def normalize_event_payload(payload: dict[str, Any]) -> tuple[ContextEventEnvelope, dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise ValueError("ContextEvent payload must be a JSON object")
    if isinstance(payload.get("event"), dict):
        raw = dict(payload)
    else:
        raw = {
            "schema_version": "1.0",
            "producer": str(payload.get("source") or "elfred_desktop_observer"),
            "received_at": datetime.now().astimezone().isoformat(),
            "event": payload,
        }
    envelope = ContextEventEnvelope.model_validate(raw)
    canonical = envelope.model_dump(mode="json", exclude_none=False)
    # Transport receipt time is not event identity. Excluding it keeps bare retries idempotent.
    stable = {
        "schema_version": canonical["schema_version"],
        "producer": canonical["producer"],
        "event": canonical["event"],
    }
    return envelope, canonical, payload_hash(stable)


class SyncResult(BaseModel):
    event_id: str
    status: str
    payload_hash: str
    job_id: str | None = None
    todo_ids: list[int] = Field(default_factory=list)
    journal_ids: list[int] = Field(default_factory=list)
    activity_state: str | None = None
    outbox_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
