from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from adapter.journal.coordinator import JournalCoordinator


logger = logging.getLogger("elfred.journal.worker")


class JournalWorker:
    """Continuously drains durable day-level Journal work."""

    def __init__(
        self,
        coordinator: JournalCoordinator,
        *,
        interval_seconds: float = 2.0,
        source_ready: Callable[[], bool] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.interval = max(0.1, float(interval_seconds))
        self.source_ready = source_ready or (lambda: True)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "created",
            "processed_days": 0,
            "last_day": None,
            "last_result": None,
            "last_error": None,
            "last_run_at": None,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="elfred-journal-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=min(5.0, self.interval + 1.0))

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def process_once(self):
        result = self.coordinator.process_next(
            source_ready=bool(self.source_ready()),
        )
        if result is None:
            self._update(state="watching", last_error=None)
            return None
        latest = self.coordinator.status().get("latest") or {}
        self._update(
            state=(
                "degraded"
                if result.status in {"retry_pending", "failed_terminal"}
                else "watching"
            ),
            processed_days=int(self.status()["processed_days"]) + 1,
            last_result=result.status,
            last_day=latest.get("journal_date"),
            last_error=(result.warnings[-1] if result.warnings else None),
            last_run_at=datetime.now().astimezone().isoformat(),
        )
        return result

    def _run(self) -> None:
        self._update(state="starting")
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception as error:
                logger.exception("Journal worker iteration failed")
                self._update(
                    state="degraded",
                    last_error=str(error),
                    last_run_at=datetime.now().astimezone().isoformat(),
                )
            self._stop.wait(self.interval)
        self._update(state="stopped")

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)
