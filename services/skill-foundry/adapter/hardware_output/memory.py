from __future__ import annotations

from typing import Any, Protocol

from adapter.hardware_output.models import JournalSnapshot


class HardwareMemoryPort(Protocol):
    """Future seam for personalization and execution learning.

    The Journal-to-hardware demo deliberately does not require an implementation.
    """

    def get_device_preferences(
        self,
        journal: JournalSnapshot,
    ) -> list[dict[str, Any]]: ...

    def record_execution_feedback(self, event: dict[str, Any]) -> None: ...


class NullHardwareMemoryPort:
    """No-op default that keeps Hardware Output independent from Memory."""

    def get_device_preferences(
        self,
        journal: JournalSnapshot,
    ) -> list[dict[str, Any]]:
        return []

    def record_execution_feedback(self, event: dict[str, Any]) -> None:
        return None
