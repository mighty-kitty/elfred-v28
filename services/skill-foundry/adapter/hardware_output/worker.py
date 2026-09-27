from __future__ import annotations

import threading
from typing import Any

from adapter.storage.store import now_iso


class HardwareOutputWorker:
    """Consumes durable hardware runs without blocking API requests."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.interval = max(
            0.1,
            service.settings.hardware_output_worker_interval_seconds,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "created",
            "processed_runs": 0,
            "failed_runs": 0,
            "last_run_id": None,
            "last_error": None,
            "last_run_at": None,
            "k3_logs_sent": 0,
            "k3_log_failures": 0,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="elfred-hardware-output-worker",
            daemon=True,
        )
        self._thread.start()
        if self.service.k3_log_replicator.enabled:
            self._log_thread = threading.Thread(
                target=self._run_log_replication,
                name="elfred-k3-log-replication-worker",
                daemon=True,
            )
            self._log_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        if self._log_thread:
            self._log_thread.join(timeout=5.0)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def process_once(self) -> dict[str, Any] | None:
        result = self.service.execute_next()
        if result is None:
            self._update(state="watching", last_run_at=now_iso())
            return None
        failure_count = int((result.get("result") or {}).get("failure_count") or 0)
        failed = result["status"] == "failed" or failure_count > 0
        current = self.status()
        self._update(
            state="degraded" if failed else "watching",
            processed_runs=current["processed_runs"] + (0 if failed else 1),
            failed_runs=current["failed_runs"] + int(failed),
            last_run_id=result["run_id"],
            last_error=result.get("error") if failed else None,
            last_run_at=now_iso(),
        )
        return result

    def flush_logs_once(self) -> dict[str, int]:
        result = self.service.k3_log_replicator.flush_once(limit=1)
        current = self.status()
        self._update(
            k3_logs_sent=current["k3_logs_sent"] + result["sent"],
            k3_log_failures=current["k3_log_failures"] + result["failed"],
        )
        return result

    def _run(self) -> None:
        self._update(state="starting")
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception as error:
                current = self.status()
                self._update(
                    state="degraded",
                    failed_runs=current["failed_runs"] + 1,
                    last_error=str(error),
                    last_run_at=now_iso(),
                )
            self._stop.wait(self.interval)
        self._update(state="stopped")

    def _run_log_replication(self) -> None:
        while not self._stop.is_set():
            try:
                self.flush_logs_once()
            except Exception as error:
                current = self.status()
                self._update(
                    k3_log_failures=current["k3_log_failures"] + 1,
                    last_error=f"K3 log replication: {error}",
                )
            self._stop.wait(max(1.0, self.interval))

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)
