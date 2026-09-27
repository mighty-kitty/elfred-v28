from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import ipaddress
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from adapter.contracts import payload_hash
from adapter.hardware_output.models import (
    AdapterResult,
    DeviceId,
    K3_OWNED_DEVICE_IDS,
)


PROTOCOL_VERSION = "1.0"
XIAO_COMMAND_PROTOCOL_VERSION = "elfred-xiao-command-v1"
_PREVIOUS_XIAO_COMMAND_PROTOCOL_VERSION = (
    bytes.fromhex("616c66726564").decode("ascii") + "-xiao-command-v1"
)
XIAO_SUCCESS_STATES = {"completed", "succeeded", "stopped"}
XIAO_PENDING_STATES = {"accepted", "queued", "running"}
XIAO_FAILURE_STATES = {"failed", "rejected", "expired", "cancelled"}
DEVICE_CAPABILITIES: dict[str, list[str]] = {
    DeviceId.PENDANT: ["notify", "stop"],
    DeviceId.BASE: ["play_scene", "stop"],
    DeviceId.ARM: ["run_preset", "stop"],
    DeviceId.PRINTER: ["print_journal", "stop"],
}


@dataclass(frozen=True)
class AdapterCommand:
    run_id: str
    action_id: str
    adapter_id: str
    command: str
    preset: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "runId": self.run_id,
            "actionId": self.action_id,
            "adapterId": self.adapter_id,
            "command": self.command,
            "preset": self.preset,
            "parameters": self.parameters,
        }


class HardwareAdapter(Protocol):
    adapter_id: str
    transport: str
    capabilities: list[str]
    automatic_retry_safe: bool

    def probe(self) -> AdapterResult: ...

    def execute(self, command: AdapterCommand) -> AdapterResult: ...

    def stop(self) -> AdapterResult: ...


class MockHardwareAdapter:
    """Deterministic adapter used before physical hardware arrives."""

    transport = "mock"
    automatic_retry_safe = True

    def __init__(
        self,
        adapter_id: str,
        *,
        capabilities: list[str] | None = None,
        latency_ms: int = 0,
        fail_commands: list[str] | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.capabilities = capabilities or list(DEVICE_CAPABILITIES[adapter_id])
        self.latency_ms = max(0, min(int(latency_ms), 5000))
        self.fail_commands = set(fail_commands or [])

    def probe(self) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="ready",
            detail={
                "adapterId": self.adapter_id,
                "transport": self.transport,
                "simulated": True,
                "capabilities": self.capabilities,
                "protocolVersion": PROTOCOL_VERSION,
            },
        )

    def execute(self, command: AdapterCommand) -> AdapterResult:
        started = time.monotonic()
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)
        if command.command not in self.capabilities:
            return AdapterResult(
                ok=False,
                status="unsupported",
                error=f"{self.adapter_id} does not support {command.command}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        if command.command in self.fail_commands:
            return AdapterResult(
                ok=False,
                status="simulated_failure",
                error=f"mock failure requested for {command.command}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return AdapterResult(
            ok=True,
            status="completed",
            detail={
                "simulated": True,
                "accepted": command.payload(),
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def stop(self) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="stopped",
            detail={"adapterId": self.adapter_id, "simulated": True},
        )


class K3OwnedHardwareAdapter:
    """Read-only PC boundary for devices executed by the K3 runtime."""

    transport = "k3-local"
    capabilities: list[str] = []
    automatic_retry_safe = False

    def __init__(self, adapter_id: str) -> None:
        if adapter_id not in {item.value for item in K3_OWNED_DEVICE_IDS}:
            raise ValueError("adapter is not K3-owned")
        self.adapter_id = adapter_id

    def probe(self) -> AdapterResult:
        return AdapterResult(
            ok=True,
            status="externally_owned",
            detail={
                "adapterId": self.adapter_id,
                "owner": "k3",
                "pcExecutionAllowed": False,
            },
        )

    def execute(self, command: AdapterCommand) -> AdapterResult:
        return AdapterResult(
            ok=False,
            status="ownership_blocked",
            error=f"{self.adapter_id} is owned locally by K3; PC execution is forbidden",
        )

    def stop(self) -> AdapterResult:
        return AdapterResult(
            ok=False,
            status="ownership_blocked",
            error=f"use the K3-local {self.adapter_id} stop; PC stop commands are forbidden",
        )


SerialFactory = Callable[..., Any]


class PersistentSerialSession:
    """Lazy, persistent Windows virtual-COM connection."""

    _com_port = re.compile(r"^COM[1-9][0-9]{0,2}$", re.IGNORECASE)

    def __init__(
        self,
        *,
        port: str,
        baud_rate: int,
        timeout_seconds: float,
        write_timeout_seconds: float,
        serial_factory: SerialFactory | None = None,
    ) -> None:
        port = str(port).strip().upper()
        if not self._com_port.fullmatch(port):
            raise ValueError("serial port must be a Windows COM port such as COM7")
        self.port = port
        self.baud_rate = max(1200, min(int(baud_rate), 2_000_000))
        self.timeout_seconds = max(0.1, min(float(timeout_seconds), 10.0))
        self.write_timeout_seconds = max(
            0.1,
            min(float(write_timeout_seconds), 10.0),
        )
        self._serial_factory = serial_factory
        self._serial: Any | None = None
        self._lock = threading.RLock()

    def open(self) -> Any:
        with self._lock:
            if self._serial is not None and bool(self._serial.is_open):
                return self._serial
            factory = self._serial_factory
            if factory is None:
                try:
                    factory = importlib.import_module("serial").Serial
                except ModuleNotFoundError as error:
                    raise RuntimeError(
                        "pyserial is required for bluetooth-spp printer transport"
                    ) from error
            self._serial = factory(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout_seconds,
                write_timeout=self.write_timeout_seconds,
            )
            if not bool(self._serial.is_open):
                self._serial.open()
            return self._serial

    def close(self) -> None:
        with self._lock:
            if self._serial is not None and bool(self._serial.is_open):
                self._serial.close()

    def write(self, payload: bytes) -> int:
        with self._lock:
            serial_port = self.open()
            written = int(serial_port.write(payload))
            serial_port.flush()
            if written != len(payload):
                raise OSError(f"serial short write: {written}/{len(payload)} bytes")
            return written


class BluetoothSppPrinterAdapter:
    """ESC/POS printer over a Bluetooth-paired Windows virtual COM port."""

    adapter_id = DeviceId.PRINTER.value
    transport = "bluetooth-spp"
    capabilities = ["print_journal"]
    automatic_retry_safe = False

    def __init__(
        self,
        config: dict[str, Any],
        *,
        serial_factory: SerialFactory | None = None,
    ) -> None:
        self.encoding = str(config.get("encoding") or "gb18030")
        try:
            "".encode(self.encoding)
        except LookupError as error:
            raise ValueError(
                f"unknown printer encoding: {self.encoding}"
            ) from error
        self.line_width = max(16, min(int(config.get("lineWidth") or 32), 64))
        self.max_characters = max(
            256,
            min(int(config.get("maxCharacters") or 12_000), 50_000),
        )
        self._session = PersistentSerialSession(
            port=str(config.get("port") or ""),
            baud_rate=int(config.get("baudRate") or 115_200),
            timeout_seconds=float(config.get("timeoutSeconds") or 1.0),
            write_timeout_seconds=float(config.get("writeTimeoutSeconds") or 5.0),
            serial_factory=serial_factory,
        )

    def probe(self) -> AdapterResult:
        started = time.monotonic()
        try:
            self._session.open()
        except (OSError, RuntimeError, ValueError) as error:
            return AdapterResult(
                ok=False,
                status="unavailable",
                error=str(error),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return AdapterResult(
            ok=True,
            status="ready",
            detail={
                "transport": self.transport,
                "port": self._session.port,
                "pairedExternally": True,
                "connectionKeptOpen": True,
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def execute(self, command: AdapterCommand) -> AdapterResult:
        if command.adapter_id != self.adapter_id or command.command != "print_journal":
            return AdapterResult(
                ok=False,
                status="unsupported",
                error="printer only accepts print_journal commands",
            )
        started = time.monotonic()
        try:
            payload = self._build_print_job(command.parameters)
            written = self._session.write(payload)
        except (OSError, RuntimeError, UnicodeError, ValueError) as error:
            return AdapterResult(
                ok=False,
                status="unavailable",
                error=str(error),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return AdapterResult(
            ok=True,
            status="accepted",
            detail={
                "runId": command.run_id,
                "actionId": command.action_id,
                "transport": self.transport,
                "port": self._session.port,
                "bytesWritten": written,
                "physicalStartConfirmed": False,
                "physicalCompletionConfirmed": False,
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def stop(self) -> AdapterResult:
        self._session.close()
        return AdapterResult(
            ok=False,
            status="unsupported",
            detail={"connectionClosed": True, "bufferedDataMayStillPrint": True},
            error="buffered printer output cannot be reliably cancelled over SPP",
        )

    def _build_print_job(self, parameters: dict[str, Any]) -> bytes:
        document = parameters.get("document")
        if not isinstance(document, dict):
            raise ValueError("printer action requires a document object")
        title = self._sanitize(document.get("title") or "Elfred")
        date = self._sanitize(document.get("date") or "")
        body = self._sanitize(document.get("body") or "")
        if len(title) + len(date) + len(body) > self.max_characters:
            raise ValueError("print document exceeds configured character limit")
        chunks = [
            b"\x1b@",
            b"\x1ba\x01",
            b"\x1bE\x01",
            title.encode(self.encoding, errors="replace"),
            b"\n",
            b"\x1bE\x00",
            date.encode(self.encoding, errors="replace"),
            b"\n\x1ba\x00",
            self._wrap(body, self.line_width).encode(self.encoding, errors="replace"),
            b"\n\n\n",
        ]
        payload = b"".join(chunks)
        if len(payload) > 131_072:
            raise ValueError("encoded print job exceeds 128 KiB")
        return payload

    @staticmethod
    def _sanitize(value: Any) -> str:
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        return "".join(
            character
            for character in text
            if character in {"\n", "\t"} or ord(character) >= 0x20
        )

    @staticmethod
    def _columns(character: str) -> int:
        return 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1

    @classmethod
    def _wrap(cls, value: str, width: int) -> str:
        lines: list[str] = []
        for source_line in value.split("\n"):
            current: list[str] = []
            columns = 0
            for character in source_line.expandtabs(4):
                size = cls._columns(character)
                if current and columns + size > width:
                    lines.append("".join(current))
                    current = []
                    columns = 0
                current.append(character)
                columns += size
            lines.append("".join(current))
        return "\n".join(lines)


class HttpJsonHardwareAdapter:
    """Generic bridge for ESP32 firmware or a vendor SDK sidecar."""

    transport = "http"
    automatic_retry_safe = True

    def __init__(
        self,
        adapter_id: str,
        config: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> None:
        self.adapter_id = adapter_id
        self.capabilities = list(
            config.get("capabilities") or DEVICE_CAPABILITIES[adapter_id]
        )
        self.base_url = str(config.get("baseUrl") or "").rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"{adapter_id}.baseUrl must be an HTTP(S) URL")
        self.health_path = str(config.get("healthPath") or "/health")
        self.command_path = str(config.get("commandPath") or "/command")
        self.stop_path = str(config.get("stopPath") or "/stop")
        self.timeout_seconds = max(0.25, min(float(timeout_seconds), 60.0))
        self.headers = {
            str(key): str(value)
            for key, value in dict(config.get("headers") or {}).items()
        }

    def probe(self) -> AdapterResult:
        return self._request("GET", self.health_path)

    def execute(self, command: AdapterCommand) -> AdapterResult:
        if command.command not in self.capabilities:
            return AdapterResult(
                ok=False,
                status="unsupported",
                error=f"{self.adapter_id} does not support {command.command}",
            )
        return self._request("POST", self.command_path, command.payload())

    def stop(self) -> AdapterResult:
        return self._request(
            "POST",
            self.stop_path,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "adapterId": self.adapter_id,
                "command": "stop",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> AdapterResult:
        started = time.monotonic()
        data = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            self.base_url + "/" + path.lstrip("/"),
            data=data,
            method=method,
        )
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        for name, value in self.headers.items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read(65536).decode("utf-8", errors="replace")
                try:
                    detail = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    detail = {"body": raw[:4000]}
                return AdapterResult(
                    ok=200 <= response.status < 300,
                    status="ready" if method == "GET" else "completed",
                    detail=detail if isinstance(detail, dict) else {"response": detail},
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return AdapterResult(
                ok=False,
                status="unavailable",
                error=str(error),
                duration_ms=int((time.monotonic() - started) * 1000),
            )


class XiaoHardwareAdapter:
    """Reliable Elfred command bridge for XIAO ESP32-S3 firmware.

    The validated hardware-to-PC firmware already exposes an authenticated
    ``/api/status`` endpoint.  This adapter deliberately reserves separate
    hardware command endpoints so the existing ``/api/stop`` streaming control
    can never be mistaken for a physical emergency stop.
    """

    transport = "xiao"
    automatic_retry_safe = True
    _token_name = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(
        self,
        adapter_id: str,
        config: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> None:
        self.adapter_id = adapter_id
        # Keep the proxy-free opener scoped to one adapter instance.  Probe and
        # execution may run on different worker/API threads.
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )
        self.capabilities = list(
            config.get("capabilities") or DEVICE_CAPABILITIES[adapter_id]
        )
        self.base_url = self._validate_base_url(
            str(config.get("baseUrl") or ""),
            allow_public_host=bool(config.get("allowPublicHost", False)),
        )
        self.device_id = str(config.get("deviceId") or adapter_id).strip()
        if not self.device_id or len(self.device_id) > 100:
            raise ValueError(f"{adapter_id}.deviceId must be 1-100 characters")
        self.board_profile = str(
            config.get("boardProfile") or "xiao-esp32s3"
        ).strip()
        self.status_path = self._validate_path(
            str(config.get("statusPath") or "/api/status"),
            field="statusPath",
        )
        self.command_path = self._validate_path(
            str(config.get("commandPath") or "/api/hardware/command"),
            field="commandPath",
        )
        self.command_status_path = self._validate_path(
            str(
                config.get("commandStatusPath")
                or "/api/hardware/commands/{commandId}"
            ),
            field="commandStatusPath",
            template=True,
        )
        self.stop_path = self._validate_path(
            str(config.get("stopPath") or "/api/hardware/stop"),
            field="stopPath",
        )
        self.timeout_seconds = max(0.25, min(float(timeout_seconds), 60.0))
        self.completion_timeout_seconds = max(
            0.25,
            min(
                float(config.get("completionTimeoutSeconds") or 15.0),
                120.0,
            ),
        )
        self.poll_interval_seconds = max(
            0.05,
            min(float(config.get("pollIntervalMs") or 250) / 1000, 5.0),
        )
        self.command_ttl_seconds = max(
            5,
            min(int(config.get("commandTtlSeconds") or 300), 3600),
        )
        token_env = str(
            config.get("tokenEnv")
            or f"XIAO_{adapter_id.upper()}_TOKEN"
        ).strip()
        if not self._token_name.fullmatch(token_env):
            raise ValueError(f"{adapter_id}.tokenEnv is not a valid environment name")
        token = os.getenv(token_env, "")
        if not 12 <= len(token) <= 64:
            raise ValueError(
                f"{adapter_id} requires a 12-64 character token in {token_env}"
            )
        self._token = token
        self.token_env = token_env
        self._command_protocol_version = XIAO_COMMAND_PROTOCOL_VERSION

    def probe(self) -> AdapterResult:
        started = time.monotonic()
        status_code, detail, error = self._request_json(
            "GET",
            self.status_path,
        )
        duration = self._duration_ms(started)
        if error or status_code is None or not 200 <= status_code < 300:
            return AdapterResult(
                ok=False,
                status="unavailable",
                detail=self._probe_detail(detail, command_ready=False),
                error=error or f"XIAO status returned HTTP {status_code}",
                duration_ms=duration,
            )
        reported = str(
            detail.get("commandProtocolVersion")
            or detail.get("command_protocol_version")
            or ""
        )
        command_ready = reported in {
            XIAO_COMMAND_PROTOCOL_VERSION,
            _PREVIOUS_XIAO_COMMAND_PROTOCOL_VERSION,
        }
        if not command_ready:
            return AdapterResult(
                ok=False,
                status="firmware_incompatible",
                detail=self._probe_detail(detail, command_ready=False),
                error=(
                    "XIAO data streaming is reachable, but the Elfred hardware "
                    f"command protocol {XIAO_COMMAND_PROTOCOL_VERSION} is not installed"
                ),
                duration_ms=duration,
            )
        self._command_protocol_version = reported
        return AdapterResult(
            ok=True,
            status="ready",
            detail=self._probe_detail(detail, command_ready=True),
            duration_ms=duration,
        )

    def execute(self, command: AdapterCommand) -> AdapterResult:
        if command.command not in self.capabilities:
            return AdapterResult(
                ok=False,
                status="unsupported",
                error=f"{self.adapter_id} does not support {command.command}",
            )
        payload = self._command_payload(command)
        return self._send_and_wait(
            self.command_path,
            payload,
            command_id=command.action_id,
        )

    def stop(self) -> AdapterResult:
        issued = datetime.now(timezone.utc)
        command_id = "stop-" + uuid.uuid4().hex
        payload: dict[str, Any] = {
            "protocolVersion": self._command_protocol_version,
            "commandId": command_id,
            "idempotencyKey": command_id,
            "adapterId": self.adapter_id,
            "deviceId": self.device_id,
            "command": "stop",
            "preset": "emergency_stop",
            "parameters": {},
            "issuedAt": issued.isoformat(),
            "expiresAt": (
                issued + timedelta(seconds=self.command_ttl_seconds)
            ).isoformat(),
        }
        payload["payloadSha256"] = self._semantic_digest(payload)
        return self._send_and_wait(
            self.stop_path,
            payload,
            command_id=command_id,
        )

    def _command_payload(self, command: AdapterCommand) -> dict[str, Any]:
        issued = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "protocolVersion": self._command_protocol_version,
            "commandId": command.action_id,
            "idempotencyKey": command.action_id,
            "runId": command.run_id,
            "actionId": command.action_id,
            "adapterId": command.adapter_id,
            "deviceId": self.device_id,
            "command": command.command,
            "preset": command.preset,
            "parameters": command.parameters,
            "issuedAt": issued.isoformat(),
            "expiresAt": (
                issued + timedelta(seconds=self.command_ttl_seconds)
            ).isoformat(),
        }
        payload["payloadSha256"] = self._semantic_digest(payload)
        return payload

    @staticmethod
    def _semantic_digest(payload: dict[str, Any]) -> str:
        """Hash only physical intent so retries remain idempotent across runs."""

        return payload_hash(
            {
                key: payload.get(key)
                for key in (
                    "protocolVersion",
                    "commandId",
                    "idempotencyKey",
                    "actionId",
                    "adapterId",
                    "deviceId",
                    "command",
                    "preset",
                    "parameters",
                )
            }
        )

    def _send_and_wait(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        command_id: str,
    ) -> AdapterResult:
        started = time.monotonic()
        status_code, receipt, error = self._request_json(
            "POST",
            path,
            payload,
        )
        if error or status_code is None or not 200 <= status_code < 300:
            return AdapterResult(
                ok=False,
                status=str(receipt.get("status") or "unavailable"),
                detail=self._receipt_detail(receipt),
                error=error or f"XIAO command returned HTTP {status_code}",
                duration_ms=self._duration_ms(started),
            )

        while True:
            validation_error = self._validate_receipt(receipt, command_id)
            if validation_error:
                return AdapterResult(
                    ok=False,
                    status="protocol_error",
                    detail=self._receipt_detail(receipt),
                    error=validation_error,
                    duration_ms=self._duration_ms(started),
                )
            state = str(receipt["status"]).casefold()
            if state in XIAO_SUCCESS_STATES:
                return AdapterResult(
                    ok=True,
                    status="completed" if state != "stopped" else "stopped",
                    detail=self._receipt_detail(receipt),
                    duration_ms=self._duration_ms(started),
                )
            if state in XIAO_FAILURE_STATES:
                return AdapterResult(
                    ok=False,
                    status=state,
                    detail=self._receipt_detail(receipt),
                    error=str(receipt.get("error") or f"XIAO command {state}"),
                    duration_ms=self._duration_ms(started),
                )
            if time.monotonic() - started >= self.completion_timeout_seconds:
                return AdapterResult(
                    ok=False,
                    status="timeout",
                    detail=self._receipt_detail(receipt),
                    error="XIAO command did not reach a terminal state before timeout",
                    duration_ms=self._duration_ms(started),
                )
            time.sleep(self.poll_interval_seconds)
            receipt_path = self.command_status_path.replace(
                "{commandId}",
                urllib.parse.quote(command_id, safe=""),
            )
            status_code, receipt, error = self._request_json("GET", receipt_path)
            if error or status_code is None or not 200 <= status_code < 300:
                return AdapterResult(
                    ok=False,
                    status="unavailable",
                    detail=self._receipt_detail(receipt),
                    error=error or f"XIAO receipt returned HTTP {status_code}",
                    duration_ms=self._duration_ms(started),
                )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int | None, dict[str, Any], str | None]:
        data = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
        )
        request.add_header("Accept", "application/json")
        request.add_header("Cache-Control", "no-store")
        request.add_header("X-Xiao-Token", self._token)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    return response.status, {}, "XIAO response exceeds 64 KiB"
                return response.status, self._decode_json(raw), None
        except urllib.error.HTTPError as error:
            raw = error.read(65537)
            detail = self._decode_json(raw[:65536])
            return int(error.code), detail, (
                str(detail.get("error") or detail.get("detail") or f"HTTP {error.code}")
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return None, {}, str(error)

    def _probe_detail(
        self,
        device_status: dict[str, Any],
        *,
        command_ready: bool,
    ) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "deviceId": self.device_id,
            "boardProfile": self.board_profile,
            "transport": self.transport,
            "tokenEnv": self.token_env,
            "capabilities": self.capabilities,
            "commandProtocolVersion": XIAO_COMMAND_PROTOCOL_VERSION,
            "commandReady": command_ready,
            "deviceStatus": device_status,
        }

    def _receipt_detail(self, receipt: dict[str, Any]) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "deviceId": self.device_id,
            "boardProfile": self.board_profile,
            "transport": self.transport,
            "receipt": receipt,
        }

    @staticmethod
    def _validate_receipt(
        receipt: dict[str, Any],
        command_id: str,
    ) -> str | None:
        if receipt.get("protocolVersion") != XIAO_COMMAND_PROTOCOL_VERSION:
            return "XIAO receipt has an unsupported protocolVersion"
        if receipt.get("commandId") != command_id:
            return "XIAO receipt commandId does not match the request"
        state = str(receipt.get("status") or "").casefold()
        if state not in (
            XIAO_SUCCESS_STATES | XIAO_PENDING_STATES | XIAO_FAILURE_STATES
        ):
            return f"XIAO receipt has an unknown status {state!r}"
        return None

    @staticmethod
    def _decode_json(raw: bytes) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    @classmethod
    def _validate_path(
        cls,
        value: str,
        *,
        field: str,
        template: bool = False,
    ) -> str:
        value = value.strip()
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError(f"XIAO {field} must be an absolute HTTP path")
        if any(character in value for character in ("\r", "\n", "#")):
            raise ValueError(f"XIAO {field} contains an unsafe character")
        if template and value.count("{commandId}") != 1:
            raise ValueError(f"XIAO {field} must contain {{commandId}} once")
        return value

    @staticmethod
    def _validate_base_url(
        value: str,
        *,
        allow_public_host: bool,
    ) -> str:
        value = value.strip().rstrip("/")
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("XIAO baseUrl must be an HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("XIAO baseUrl cannot contain credentials, query, or fragment")
        hostname = parsed.hostname.casefold()
        local_host = (
            hostname == "localhost"
            or hostname.endswith(".local")
        )
        try:
            address = ipaddress.ip_address(hostname)
            local_host = (
                address.is_private
                or address.is_loopback
                or address.is_link_local
            )
        except ValueError:
            pass
        if not local_host and not allow_public_host:
            raise ValueError(
                "XIAO baseUrl must use localhost, a private IP, or a .local "
                "mDNS name"
            )
        return value


class UnavailableHardwareAdapter:
    transport = "invalid"
    automatic_retry_safe = False

    def __init__(self, adapter_id: str, error: str) -> None:
        self.adapter_id = adapter_id
        self.capabilities = list(DEVICE_CAPABILITIES[adapter_id])
        self.error = error

    def probe(self) -> AdapterResult:
        return AdapterResult(ok=False, status="misconfigured", error=self.error)

    def execute(self, command: AdapterCommand) -> AdapterResult:
        return AdapterResult(ok=False, status="misconfigured", error=self.error)

    def stop(self) -> AdapterResult:
        return AdapterResult(ok=False, status="misconfigured", error=self.error)


class HardwareAdapterRegistry:
    """Loads four logical adapters without coupling the core to device models."""

    def __init__(self, config_path: Path, *, timeout_seconds: float = 5.0) -> None:
        self.config_path = Path(config_path)
        self.timeout_seconds = timeout_seconds
        self.load_error: str | None = None
        self._adapters: dict[str, HardwareAdapter] = {}
        self._last_health: dict[str, AdapterResult] = {}
        self.reload()

    def reload(self) -> None:
        self.load_error = None
        self._last_health = {}
        config: dict[str, Any] = {}
        if self.config_path.exists():
            try:
                parsed = json.loads(self.config_path.read_text(encoding="utf-8"))
                config = dict(parsed.get("devices") or {})
            except (OSError, ValueError, TypeError) as error:
                self.load_error = str(error)
        adapters: dict[str, HardwareAdapter] = {}
        for device in DeviceId:
            if device in K3_OWNED_DEVICE_IDS:
                adapters[device.value] = K3OwnedHardwareAdapter(device.value)
                continue
            device_config = dict(config.get(device.value) or {})
            transport = str(device_config.get("transport") or "mock").casefold()
            try:
                if transport == "mock":
                    adapters[device.value] = MockHardwareAdapter(
                        device.value,
                        capabilities=device_config.get("capabilities"),
                        latency_ms=int(device_config.get("latencyMs") or 0),
                        fail_commands=device_config.get("failCommands"),
                    )
                elif transport == "http":
                    adapters[device.value] = HttpJsonHardwareAdapter(
                        device.value,
                        device_config,
                        timeout_seconds=self.timeout_seconds,
                    )
                elif transport == "xiao":
                    adapters[device.value] = XiaoHardwareAdapter(
                        device.value,
                        device_config,
                        timeout_seconds=self.timeout_seconds,
                    )
                elif transport == "bluetooth-spp":
                    if device is not DeviceId.PRINTER:
                        raise ValueError(
                            "bluetooth-spp transport is only valid for printer"
                        )
                    adapters[device.value] = BluetoothSppPrinterAdapter(device_config)
                else:
                    raise ValueError(
                        "unsupported transport "
                        f"{transport!r}; expected mock, http, xiao, or bluetooth-spp"
                    )
            except (TypeError, ValueError) as error:
                adapters[device.value] = UnavailableHardwareAdapter(
                    device.value,
                    str(error),
                )
        self._adapters = adapters

    def get(self, adapter_id: str) -> HardwareAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as error:
            raise KeyError(f"unknown hardware adapter: {adapter_id}") from error

    def describe(self, *, probe: bool = False) -> list[dict[str, Any]]:
        result = []
        for adapter_id, adapter in self._adapters.items():
            health = self._last_health.get(adapter_id)
            if probe:
                health = adapter.probe()
                self._last_health[adapter_id] = health
            result.append(
                {
                    "adapter_id": adapter_id,
                    "transport": adapter.transport,
                    "capabilities": adapter.capabilities,
                    "health": (
                        health.model_dump(mode="json", by_alias=False)
                        if health is not None
                        else None
                    ),
                }
            )
        return result
