from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from adapter.contracts import canonical_json
from adapter.hardware_output.repository import HardwareOutputRepository


class K3ExecutionLogSink:
    """Authenticated log-only HTTP client; payloads can never be executed."""

    def __init__(self, base_url: str, secret: str, timeout_seconds: float) -> None:
        self.base_url = self._validate_base_url(base_url)
        if not 16 <= len(secret) <= 128:
            raise ValueError("K3 log HMAC secret must contain 16-128 characters")
        self._secret = secret.encode("utf-8")
        self.timeout_seconds = max(0.25, min(float(timeout_seconds), 10.0))
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def send(self, payload: dict[str, Any]) -> tuple[bool, str | None]:
        if payload.get("executable") is not False:
            return False, "K3 log payload must explicitly be non-executable"
        path = "/api/hardware/execution-logs"
        body = canonical_json(payload)
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        digest = hashlib.sha256(body).hexdigest()
        signed = "\n".join(("POST", path, timestamp, nonce, digest)).encode()
        signature = hmac.new(self._secret, signed, hashlib.sha256).hexdigest()
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method="POST",
        )
        for name, value in {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "X-Elfred-Timestamp": timestamp,
            "X-Elfred-Nonce": nonce,
            "X-Elfred-Content-SHA256": digest,
            "X-Elfred-Log-Signature": signature,
        }.items():
            request.add_header(name, value)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(65_537)
                if len(raw) > 65_536:
                    return False, "K3 log response exceeds 64 KiB"
                detail = json.loads(raw.decode("utf-8")) if raw else {}
                ok = (
                    200 <= response.status < 300
                    and isinstance(detail, dict)
                    and detail.get("logId") == payload.get("logId")
                    and str(detail.get("status") or "").casefold()
                    in {"stored", "duplicate"}
                )
                return ok, None if ok else "K3 returned an invalid log receipt"
        except urllib.error.HTTPError as error:
            return False, f"K3 log endpoint returned HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            return False, str(error)

    @staticmethod
    def _validate_base_url(value: str) -> str:
        value = str(value).strip().rstrip("/")
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("K3 log URL must be HTTP(S)")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("K3 log URL cannot contain credentials, query, or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("K3 log URL must not contain a path")
        hostname = parsed.hostname.casefold()
        local = hostname == "localhost" or hostname.endswith(".local")
        try:
            address = ipaddress.ip_address(hostname)
            local = address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            pass
        if not local:
            raise ValueError("K3 log URL must use a private IP, localhost, or .local")
        return value


class K3ExecutionLogReplicator:
    def __init__(
        self,
        repository: HardwareOutputRepository,
        sink: K3ExecutionLogSink | None,
    ) -> None:
        self.repository = repository
        self.sink = sink

    @property
    def enabled(self) -> bool:
        return self.sink is not None

    def flush_once(self, limit: int = 20) -> dict[str, int]:
        if self.sink is None:
            return {"sent": 0, "failed": 0}
        sent = 0
        failed = 0
        for item in self.repository.pending_k3_logs(limit):
            ok, error = self.sink.send(item["payload"])
            if ok:
                self.repository.mark_k3_log_sent(item["log_id"])
                sent += 1
                continue
            attempts = int(item["send_attempts"]) + 1
            delay_seconds = min(300, 2 ** min(attempts, 8))
            retry_at = (datetime.now().astimezone() + timedelta(seconds=delay_seconds)).isoformat()
            self.repository.mark_k3_log_failed(
                item["log_id"],
                error or "K3 log send failed",
                retry_at,
            )
            failed += 1
        return {"sent": sent, "failed": failed}
