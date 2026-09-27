"""Journal-to-hardware orchestration for Elfred Home."""

from adapter.hardware_output.memory import (
    HardwareMemoryPort,
    NullHardwareMemoryPort,
)
from adapter.hardware_output.service import HardwareOutputService

__all__ = [
    "HardwareMemoryPort",
    "HardwareOutputService",
    "NullHardwareMemoryPort",
]
