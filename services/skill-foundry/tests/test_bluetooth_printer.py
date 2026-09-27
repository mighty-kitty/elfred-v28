from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapter.config import Settings
from adapter.freetodo_client import InMemoryFreeTodoClient
from adapter.hardware_output.adapters import (
    AdapterCommand,
    BluetoothSppPrinterAdapter,
    HardwareAdapterRegistry,
)
from adapter.hardware_output.models import (
    AdapterResult,
    ExecutePlanRequest,
    JournalSnapshot,
    PlanCreateRequest,
)
from adapter.service import AdapterService


class FakeSerial:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.is_open = True
        self.writes: list[bytes] = []

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def write(self, payload: bytes) -> int:
        self.writes.append(bytes(payload))
        return len(payload)

    def flush(self) -> None:
        return None


def command(body: str) -> AdapterCommand:
    return AdapterCommand(
        run_id="run-printer",
        action_id="action-printer",
        adapter_id="printer",
        command="print_journal",
        preset="daily_journal",
        parameters={
            "document": {"title": "Elfred", "date": "2026-08-03", "body": body}
        },
    )


def test_printer_keeps_com_port_open_and_sanitizes_escapes() -> None:
    serial_port = FakeSerial()
    calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeSerial:
        calls.append(kwargs)
        return serial_port

    adapter = BluetoothSppPrinterAdapter(
        {"port": "COM7", "baudRate": 115200},
        serial_factory=factory,
    )
    assert adapter.probe().ok is True
    result = adapter.execute(command("Hello\x1b@OWNED\n你好"))
    assert result.ok is True
    assert result.status == "accepted"
    assert result.detail["physicalCompletionConfirmed"] is False
    assert len(calls) == 1
    assert serial_port.writes[0].startswith(b"\x1b@")
    assert b"\x1b@OWNED" not in serial_port.writes[0]


def test_printer_rejects_oversized_document_without_writing() -> None:
    serial_port = FakeSerial()
    adapter = BluetoothSppPrinterAdapter(
        {"port": "COM7", "maxCharacters": 256},
        serial_factory=lambda **kwargs: serial_port,
    )
    result = adapter.execute(command("x" * 300))
    assert result.ok is False
    assert "character limit" in str(result.error)
    assert serial_port.writes == []


def test_registry_limits_bluetooth_spp_to_printer(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {"devices": {"printer": {"transport": "bluetooth-spp", "port": "COM7"}}}
        ),
        encoding="utf-8",
    )
    registry = HardwareAdapterRegistry(valid)
    assert registry.get("printer").transport == "k3-local"

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            {"devices": {"base": {"transport": "bluetooth-spp", "port": "COM7"}}}
        ),
        encoding="utf-8",
    )
    assert HardwareAdapterRegistry(invalid).get("base").transport == "k3-local"


def test_k3_printer_is_never_executed_by_the_pc(tmp_path: Path) -> None:
    settings = Settings(
        tmp_path / "elfred_adapter.db",
        "http://fake",
        "http://observer",
        hardware_output_config_path=tmp_path / "hardware.local.json",
    )
    service = AdapterService(settings, InMemoryFreeTodoClient()).hardware_output
    printer = service.registry.get("printer")
    result = printer.execute(
        AdapterCommand(
            run_id="test",
            action_id="test",
            adapter_id="printer",
            command="print_journal",
            preset="daily_journal",
        )
    )
    assert result.status == "ownership_blocked"
