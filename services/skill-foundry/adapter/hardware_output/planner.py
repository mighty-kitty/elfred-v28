from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adapter.hardware_output.models import ActionProposal, DeviceId, JournalSnapshot


@dataclass
class PlanningResult:
    actions: list[ActionProposal]
    effective_mode: str
    warnings: list[str] = field(default_factory=list)
    model_detail: dict[str, Any] = field(default_factory=dict)


class HardwareActionPlanner:
    """Create only actions executable by the PC; K3 owns the other devices."""

    def plan(self, journal: JournalSnapshot, requested_mode: str) -> PlanningResult:
        warnings = []
        if requested_mode == "model":
            warnings.append(
                "K3 owns base, arm, and printer; PC hardware model planning is disabled"
            )
        return PlanningResult(
            actions=[
                ActionProposal(
                    adapter_id=DeviceId.PENDANT,
                    command="notify",
                    preset="journal_ready",
                    parameters={"title": "今日日志已完成", "date": journal.date[:10]},
                    summary="通知 Elfred 悬浮件今日日志已完成",
                    rationale="K3 设备由本地运行时负责，PC 仅发送安全的语义通知。",
                )
            ],
            effective_mode="deterministic",
            warnings=warnings,
        )
