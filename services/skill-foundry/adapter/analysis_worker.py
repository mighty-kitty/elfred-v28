from __future__ import annotations

import threading
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class AnalysisWorker:
    """Consume durable model-analysis jobs without blocking capture or HTTP ingest."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.interval = max(0.25, service.settings.analysis_worker_interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "created",
            "processed_events": 0,
            "failed_events": 0,
            "last_event_id": None,
            "last_result": None,
            "last_error": None,
            "last_run_at": None,
            "last_success_at": None,
            "last_failure_at": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="elfred-context-analysis-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def process_once(self) -> dict[str, Any] | None:
        """Claim the currently available work without delaying a lone event."""
        batch: list[dict[str, Any]] = []
        while len(batch) < 30:
            claimed = self.service.store.claim_task_analysis(
                lease_seconds=self.service.settings.analysis_lease_seconds
            )
            if claimed is None:
                break
            batch.append(claimed)

        if not batch:
            now = _now()
            current = self.status()
            self._update(
                state="degraded" if current.get("last_error") else "watching",
                last_run_at=now,
            )
            return None

        # One Codex thread handles the claimed batch.
        self.service.process_analysis_batch(batch)
        now = _now()
        current = self.status()
        self._update(
            state="watching",
            processed_events=current["processed_events"] + len(batch),
            last_run_at=now,
            last_success_at=now,
        )
        return {"batch_size": len(batch), "status": "processed"}

    def _run(self) -> None:
        self._update(state="starting")
        try:
            self.service.repair_task_projections()
        except Exception as error:
            self._update(state="degraded", last_error=str(error), last_failure_at=_now())
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception as error:  # keep the durable worker alive across one bad job
                current = self.status()
                self._update(
                    state="degraded",
                    failed_events=current["failed_events"] + 1,
                    last_error=str(error),
                    last_run_at=_now(),
                    last_failure_at=_now(),
                )
            self._stop.wait(self.interval)
        self._update(state="stopped")

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)
