from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(item[:1].upper() + item[1:] for item in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class DeviceId(StrEnum):
    PENDANT = "pendant"
    BASE = "base"
    ARM = "arm"
    PRINTER = "printer"


K3_OWNED_DEVICE_IDS = frozenset({DeviceId.BASE, DeviceId.ARM, DeviceId.PRINTER})
K3_OWNED_ADAPTER_IDS = frozenset(item.value for item in K3_OWNED_DEVICE_IDS)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JournalSnapshot(ApiModel):
    """Stable input boundary between Journal generation and hardware output."""

    journal_id: str | int
    journal_version: str | None = None
    date: str
    title: str = "Elfred Personal Journal"
    content: str = ""
    content_objective: str = ""
    content_ai: str = ""
    user_notes: str = ""
    mood: str | None = None
    energy: int | None = Field(default=None, ge=0, le=10)
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("date must contain an ISO calendar date")
        return value.strip()

    def combined_text(self) -> str:
        sections = [
            self.content,
            self.content_objective,
            self.content_ai,
            self.user_notes,
        ]
        return "\n\n".join(item.strip() for item in sections if item and item.strip())


class PlanCreateRequest(ApiModel):
    journal: JournalSnapshot
    planning_mode: str = Field(default="auto", pattern="^(auto|deterministic|model)$")
    force: bool = False


class JournalReadyRequest(ApiModel):
    journal: JournalSnapshot
    planning_mode: str = Field(default="auto", pattern="^(auto|deterministic|model)$")
    execute_safe_actions: bool = False
    idempotency_key: str | None = Field(default=None, max_length=200)


class ExecutePlanRequest(ApiModel):
    action_ids: list[str] = Field(default_factory=list)
    confirmed_action_ids: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=200)
    force: bool = False


class AdapterTestRequest(ApiModel):
    confirm: bool = False


class ActionProposal(ApiModel):
    adapter_id: DeviceId
    command: str
    preset: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    summary: str
    rationale: str
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False


class AdapterResult(ApiModel):
    ok: bool
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
