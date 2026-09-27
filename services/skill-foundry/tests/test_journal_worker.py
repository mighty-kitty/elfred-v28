from __future__ import annotations

from adapter.journal.models import GenerateResponse
from adapter.journal.worker import JournalWorker


class StubCoordinator:
    def __init__(self, response: GenerateResponse | None) -> None:
        self.response = response
        self.ready_values: list[bool] = []

    def process_next(self, *, source_ready: bool):
        self.ready_values.append(source_ready)
        return self.response

    def status(self) -> dict:
        return {
            "latest": {
                "journal_date": "2026-07-30",
                "status": self.response.status if self.response else "idle",
            }
        }


def test_worker_forwards_source_readiness_and_records_success() -> None:
    coordinator = StubCoordinator(GenerateResponse(status="llm_generated"))
    worker = JournalWorker(
        coordinator,  # type: ignore[arg-type]
        source_ready=lambda: True,
    )

    result = worker.process_once()

    assert result.status == "llm_generated"
    assert coordinator.ready_values == [True]
    assert worker.status()["state"] == "watching"
    assert worker.status()["last_day"] == "2026-07-30"


def test_worker_keeps_retryable_failure_for_automatic_recovery() -> None:
    coordinator = StubCoordinator(
        GenerateResponse(
            status="retry_pending",
            warnings=["temporary source outage"],
        )
    )
    worker = JournalWorker(
        coordinator,  # type: ignore[arg-type]
        source_ready=lambda: False,
    )

    result = worker.process_once()

    assert result.status == "retry_pending"
    assert coordinator.ready_values == [False]
    assert worker.status()["state"] == "degraded"
    assert worker.status()["last_error"] == "temporary source outage"
