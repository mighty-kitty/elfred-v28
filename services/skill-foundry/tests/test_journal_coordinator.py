from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

from adapter.contracts import normalize_event_payload
from adapter.freetodo_client import FreeTodoError, InMemoryFreeTodoClient
from adapter.journal.coordinator import JournalCoordinator
from adapter.journal.legacy import build_legacy_group
from adapter.journal.models import GenerateRequest
from adapter.journal.parser import JournalParser
from adapter.journal.service import JournalService
from adapter.storage.store import SQLiteStore


class CapturingGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "summary_line": "summary",
                "main_thread": "thread",
                "key_progress": ["progress"],
                "task_changes": "",
                "ideas_and_insights": [],
                "decisions": [],
                "risks_and_blockers": [],
                "waiting_on": [],
                "next_steps": [],
                "mood_and_energy": None,
            }
        )


class FailFirstCreateClient(InMemoryFreeTodoClient):
    def __init__(self) -> None:
        super().__init__()
        self.remaining_failures = 1

    def create_journal(self, payload: dict) -> dict:
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise FreeTodoError("temporary FreeTodo outage")
        return super().create_journal(payload)


class BlockingGenerator(CapturingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.resume = threading.Event()

    def generate(self, prompt: str) -> str:
        self.started.set()
        if not self.resume.wait(5):
            raise RuntimeError("test generator was not resumed")
        return super().generate(prompt)


class CallbackGenerator(CapturingGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.callback = None

    def generate(self, prompt: str) -> str:
        callback, self.callback = self.callback, None
        if callback is not None:
            callback()
        return super().generate(prompt)


class CommitThenLoseResponseClient(InMemoryFreeTodoClient):
    def __init__(self) -> None:
        super().__init__()
        self.lose_response = True

    def create_journal(self, payload: dict) -> dict:
        created = super().create_journal(payload)
        if self.lose_response:
            self.lose_response = False
            stored = self.journals[int(created["id"])]
            stored["tags"] = [
                {"id": index, "tag_name": tag}
                for index, tag in enumerate(stored.get("tags") or [], start=1)
            ]
            raise FreeTodoError("connection lost after commit")
        return created


class AlwaysFailCreateClient(InMemoryFreeTodoClient):
    def create_journal(self, payload: dict) -> dict:
        raise FreeTodoError("temporary FreeTodo outage")


class FailFirstDeleteClient(InMemoryFreeTodoClient):
    def __init__(self) -> None:
        super().__init__()
        self.remaining_delete_failures = 1

    def delete_journal(self, journal_id: int) -> None:
        if self.remaining_delete_failures:
            self.remaining_delete_failures -= 1
            raise FreeTodoError("delete response unavailable")
        super().delete_journal(journal_id)


class InvalidGenerator(CapturingGenerator):
    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "not-json"


def _event(event_id: str, minute: int = 0, text: str | None = None, **privacy) -> dict:
    return {
        "event_id": event_id,
        "created_at": f"2026-07-30T09:{minute:02d}:00+08:00",
        "source": "desktop_observer",
        "app": {"name": "Code", "category": "development"},
        "content": {
            "summary": text or f"event {event_id}",
            "clean_text": text or f"event {event_id}",
            "tasks": [],
        },
        "privacy": {
            "is_sensitive": False,
            "sensitivity_types": [],
            "action": "allow",
            "requires_user_confirmation": False,
            "allowed_to_upload": False,
            **privacy,
        },
    }


def _ingest(store: SQLiteStore, event: dict) -> None:
    _, canonical, digest = normalize_event_payload(event)
    store.ingest_event(canonical, digest)


def _coordinator(
    tmp_path: Path,
    *,
    client: InMemoryFreeTodoClient | None = None,
    generator: CapturingGenerator | None = None,
    on_published=None,
) -> tuple[JournalCoordinator, SQLiteStore, InMemoryFreeTodoClient, CapturingGenerator]:
    store = SQLiteStore(tmp_path / "adapter.db")
    actual_client = client or InMemoryFreeTodoClient()
    actual_generator = generator or CapturingGenerator()
    coordinator = JournalCoordinator(
        JournalService(actual_generator),  # type: ignore[arg-type]
        store,
        actual_client,
        max_events=12,
        max_attempts=3,
        retry_base_seconds=0,
        on_published=on_published,
    )
    return coordinator, store, actual_client, actual_generator


def test_same_full_day_source_is_generated_and_published_once(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    for index in range(40):
        _ingest(store, _event(str(index), index))

    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    second = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert first.status == "llm_generated"
    assert second.status == "noop_unchanged"
    assert len(generator.prompts) == 1
    assert len(client.journals) == 1
    assert generator.prompts[0].count("事件摘要(JSON)") == 1
    assert "共 40 条事件" in generator.prompts[0]
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["status"] == "succeeded"
    assert state["source_event_count"] == 40
    assert state["included_event_count"] == 12


def test_manual_remote_change_is_checked_before_regeneration(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    assert first.journal_id is not None
    client.journals[first.journal_id]["content_ai"] = "用户自己的日记"
    _ingest(store, _event("second", 1))

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "manual_modified"
    assert len(generator.prompts) == 1
    assert client.journals[first.journal_id]["content_ai"] == "用户自己的日记"


def test_manual_remote_change_during_generation_is_preserved(tmp_path: Path) -> None:
    generator = CallbackGenerator()
    coordinator, store, client, _ = _coordinator(tmp_path, generator=generator)
    _ingest(store, _event("first"))
    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    assert first.journal_id is not None
    _ingest(store, _event("second", 1))

    def edit_remote() -> None:
        client.journals[first.journal_id]["content_ai"] = "用户在生成期间写下的内容"

    generator.callback = edit_remote
    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "manual_modified"
    assert len(generator.prompts) == 2
    assert client.journals[first.journal_id]["content_ai"] == "用户在生成期间写下的内容"
    assert ("PUT", f"/api/journals/{first.journal_id}") not in client.calls


def test_existing_unmanaged_uid_is_adopted_without_overwrite(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    remote = client.create_journal(
        {
            "uid": "elfred-daily-2026-07-30",
            "name": "existing",
            "date": "2026-07-30T12:00:00+08:00",
            "content_ai": "keep me",
        }
    )

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "adopted_existing"
    assert generator.prompts == []
    assert client.get_journal(remote["id"])["content_ai"] == "keep me"


def test_unmodified_legacy_fallback_is_regenerated(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    events = [_event(f"event-{index}", index) for index in range(20)]
    for event in events:
        _ingest(store, event)
    fallback = asdict(
        JournalParser().fallback(
            build_legacy_group(
                list(reversed(events)),
                "2026-07-30",
                max_events=12,
            )
        )
    )
    remote = client.create_journal(fallback)

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "llm_generated"
    assert len(generator.prompts) == 1
    assert client.get_journal(remote["id"])["content_ai"] != fallback["content_ai"]
    state = store.journal_sync_state("2026-07-30")
    assert state is not None and state["remote_managed"] == 1


def test_modified_legacy_fallback_is_preserved(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    events = [_event(f"event-{index}", index) for index in range(4)]
    for event in events:
        _ingest(store, event)
    fallback = asdict(
        JournalParser().fallback(
            build_legacy_group(
                list(reversed(events)),
                "2026-07-30",
                max_events=12,
            )
        )
    )
    fallback["content_objective"] += "\n\nUser addition"
    remote = client.create_journal(fallback)

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "adopted_existing"
    assert generator.prompts == []
    assert client.get_journal(remote["id"])["content_objective"].endswith(
        "User addition"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tags", ["Elfred", "manual"]),
        ("related_todo_ids", [42]),
        ("mood", "focused"),
        ("energy", 8),
    ],
)
def test_legacy_metadata_edits_are_preserved(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    events = [_event("first")]
    _ingest(store, events[0])
    fallback = asdict(
        JournalParser().fallback(
            build_legacy_group(events, "2026-07-30", max_events=12)
        )
    )
    fallback[field] = value
    client.create_journal(fallback)

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "adopted_existing"
    assert generator.prompts == []


def test_persisted_candidate_is_reused_after_transient_publish_failure(
    tmp_path: Path,
) -> None:
    client = FailFirstCreateClient()
    coordinator, store, _, generator = _coordinator(tmp_path, client=client)
    _ingest(store, _event("first"))

    failed = coordinator.sync(GenerateRequest(date="2026-07-30"))
    recovered = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert failed.status == "retry_pending"
    assert recovered.status == "llm_generated"
    assert len(generator.prompts) == 1
    assert len(client.journals) == 1
    assert store.journal_sync_state("2026-07-30")["attempt_count"] == 0


def test_source_unavailable_is_retryable_not_no_events(tmp_path: Path) -> None:
    coordinator, store, _, _ = _coordinator(tmp_path)
    coordinator.enqueue("2026-07-30", trigger="startup")

    result = coordinator.process_next(source_ready=False)

    assert result is not None
    assert result.status == "pending_source"
    state = store.journal_sync_state("2026-07-30")
    assert state["status"] == "retry_pending"
    assert state["last_error"] == "journal_source_not_ready"


def test_manual_sync_uses_shared_source_readiness_provider(tmp_path: Path) -> None:
    coordinator, store, _, generator = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    coordinator.set_source_ready_provider(lambda: False)

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "pending_source"
    assert generator.prompts == []
    assert store.journal_sync_state("2026-07-30")["status"] == "retry_pending"


def test_duplicate_remote_uid_stops_without_generation(tmp_path: Path) -> None:
    coordinator, store, client, generator = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    payload = {
        "uid": "elfred-daily-2026-07-30",
        "name": "duplicate",
        "date": "2026-07-30T12:00:00+08:00",
    }
    client.create_journal(payload)
    client.create_journal(payload)

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "duplicate_uid"
    assert generator.prompts == []


def test_hardware_hook_runs_once_and_only_after_publish(tmp_path: Path) -> None:
    calls: list[tuple[int | None, int]] = []
    client = InMemoryFreeTodoClient()

    def hook(response) -> None:
        calls.append((response.journal_id, len(client.journals)))

    coordinator, store, _, _ = _coordinator(
        tmp_path,
        client=client,
        on_published=hook,
    )
    _ingest(store, _event("first"))

    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    second = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert first.status == "llm_generated"
    assert second.status == "noop_unchanged"
    assert calls == [(first.journal_id, 1)]


def test_day_lease_blocks_parallel_work_and_recovers_after_expiry(
    tmp_path: Path,
) -> None:
    coordinator, store, _, _ = _coordinator(tmp_path)
    coordinator.enqueue("2026-07-30", trigger="event")

    first = store.claim_journal_day("2026-07-30", lease_seconds=60)
    blocked = store.claim_journal_day("2026-07-30", lease_seconds=60)
    store.update_journal_sync_state(
        "2026-07-30",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    recovered = store.claim_next_journal_day(lease_seconds=60)

    assert first is not None
    assert blocked is None
    assert recovered is not None
    assert recovered["journal_date"] == "2026-07-30"
    assert recovered["lease_token"] != first["lease_token"]


def test_legacy_terminal_failure_is_recovered_without_user_action(
    tmp_path: Path,
) -> None:
    coordinator, store, client, _ = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    coordinator.enqueue("2026-07-30", trigger="event")
    store.update_journal_sync_state(
        "2026-07-30",
        status="failed_terminal",
        next_attempt_at="2000-01-01T00:00:00+00:00",
        last_error="legacy retry limit reached",
    )

    result = coordinator.process_next()

    assert result is not None
    assert result.status == "llm_generated"
    assert len(client.journals) == 1
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["status"] == "succeeded"
    assert state["last_error"] is None


def test_stale_worker_cannot_persist_or_publish_after_takeover(tmp_path: Path) -> None:
    generator = BlockingGenerator()
    coordinator, store, client, _ = _coordinator(tmp_path, generator=generator)
    _ingest(store, _event("first"))
    results = []

    worker = threading.Thread(
        target=lambda: results.append(
            coordinator.sync(GenerateRequest(date="2026-07-30"))
        )
    )
    worker.start()
    assert generator.started.wait(5)
    stale = store.journal_sync_state("2026-07-30")
    assert stale is not None
    store.update_journal_sync_state(
        "2026-07-30",
        lease_until="2000-01-01T00:00:00+00:00",
    )
    takeover = store.claim_journal_day("2026-07-30", lease_seconds=60)
    assert takeover is not None
    generator.resume.set()
    worker.join(5)

    assert not worker.is_alive()
    assert results[0].status == "busy"
    assert results[0].warnings == ["journal_lease_lost"]
    assert client.journals == {}
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["lease_token"] == takeover["lease_token"]
    assert state["lease_token"] != stale["lease_token"]
    assert state["candidate"] is None


def test_stale_worker_cannot_trigger_hardware_after_takeover(tmp_path: Path) -> None:
    calls = []
    store = SQLiteStore(tmp_path / "adapter.db")
    client = InMemoryFreeTodoClient()
    generator = CapturingGenerator()

    class TakeoverBeforeHardwareCoordinator(JournalCoordinator):
        def _ensure_hardware(self, day, state, response) -> None:
            self.store.update_journal_sync_state(
                day,
                lease_until="2000-01-01T00:00:00+00:00",
            )
            assert self.store.claim_journal_day(day, lease_seconds=60) is not None
            super()._ensure_hardware(day, state, response)

    coordinator = TakeoverBeforeHardwareCoordinator(
        JournalService(generator),  # type: ignore[arg-type]
        store,
        client,
        retry_base_seconds=0,
        on_published=lambda response: calls.append(response.journal_id),
    )
    _ingest(store, _event("first"))

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "busy"
    assert result.warnings == ["journal_lease_lost"]
    assert calls == []
    assert len(client.journals) == 1


def test_pending_hardware_is_recovered_after_worker_crash(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    client = InMemoryFreeTodoClient()
    generator = CapturingGenerator()

    class CrashBeforeHardwareCoordinator(JournalCoordinator):
        def _ensure_hardware(self, day, state, response) -> None:
            raise SystemExit("simulated process crash")

    crashing = CrashBeforeHardwareCoordinator(
        JournalService(generator),  # type: ignore[arg-type]
        store,
        client,
        retry_base_seconds=0,
        on_published=lambda response: None,
    )
    _ingest(store, _event("first"))
    with pytest.raises(SystemExit, match="simulated process crash"):
        crashing.sync(GenerateRequest(date="2026-07-30"))
    pending = store.journal_sync_state("2026-07-30")
    assert pending is not None
    assert pending["status"] == "succeeded"
    assert pending["hardware_status"] == "pending"
    store.update_journal_sync_state(
        "2026-07-30",
        lease_until="2000-01-01T00:00:00+00:00",
    )

    calls = []
    recovered = JournalCoordinator(
        JournalService(generator),  # type: ignore[arg-type]
        store,
        client,
        retry_base_seconds=0,
        on_published=lambda response: calls.append(response.journal_id),
    ).process_next()

    assert recovered is not None
    assert recovered.status == "noop_unchanged"
    assert calls == [recovered.journal_id]
    final = store.journal_sync_state("2026-07-30")
    assert final is not None
    assert final["hardware_status"] == "succeeded"


def test_enqueue_during_hardware_keeps_new_generation_pending(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "adapter.db")
    client = InMemoryFreeTodoClient()
    generator = CapturingGenerator()
    enqueue_once = True

    def hook(response) -> None:
        nonlocal enqueue_once
        if enqueue_once:
            enqueue_once = False
            coordinator.enqueue("2026-07-30", trigger="event_during_hardware")

    coordinator = JournalCoordinator(
        JournalService(generator),  # type: ignore[arg-type]
        store,
        client,
        retry_base_seconds=0,
        on_published=hook,
    )
    _ingest(store, _event("first"))

    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    pending = store.journal_sync_state("2026-07-30")
    second = coordinator.process_next()
    final = store.journal_sync_state("2026-07-30")

    assert first.status == "llm_generated"
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["requested_generation"] == 2
    assert pending["processed_generation"] == 1
    assert second is not None
    assert second.status == "noop_unchanged"
    assert final is not None
    assert final["status"] == "succeeded"
    assert final["processed_generation"] == 2


def test_enqueue_during_generation_preserves_new_generation(tmp_path: Path) -> None:
    generator = CallbackGenerator()
    coordinator, store, client, _ = _coordinator(tmp_path, generator=generator)
    _ingest(store, _event("first"))
    generator.callback = lambda: coordinator.enqueue(
        "2026-07-30",
        trigger="event_during_generation",
    )

    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    pending = store.journal_sync_state("2026-07-30")
    second = coordinator.process_next()
    final = store.journal_sync_state("2026-07-30")

    assert first.status == "llm_generated"
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["requested_generation"] == 2
    assert pending["processed_generation"] == 1
    assert second is not None
    assert second.status == "noop_unchanged"
    assert final is not None
    assert final["status"] == "succeeded"
    assert final["requested_generation"] == 2
    assert final["processed_generation"] == 2
    assert len(generator.prompts) == 1
    assert len(client.journals) == 1


def test_committed_create_with_lost_response_is_recovered_semantically(
    tmp_path: Path,
) -> None:
    client = CommitThenLoseResponseClient()
    coordinator, store, _, generator = _coordinator(tmp_path, client=client)
    _ingest(store, _event("first"))

    failed = coordinator.sync(GenerateRequest(date="2026-07-30"))
    recovered = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert failed.status == "retry_pending"
    assert recovered.status == "llm_generated"
    assert len(generator.prompts) == 1
    assert len(client.journals) == 1
    assert client.calls.count(("POST", "/api/journals")) == 1
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["status"] == "succeeded"
    assert state["remote_managed"] == 1


def test_transient_publish_failures_never_become_terminal(tmp_path: Path) -> None:
    client = AlwaysFailCreateClient()
    coordinator, store, _, generator = _coordinator(tmp_path, client=client)
    _ingest(store, _event("first"))

    results = [coordinator.sync(GenerateRequest(date="2026-07-30")) for _ in range(5)]

    assert [result.status for result in results] == ["retry_pending"] * 5
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["status"] == "retry_pending"
    assert state["attempt_count"] == 5
    assert state["next_attempt_at"] is not None
    assert len(generator.prompts) == 1


def test_generation_retries_still_fall_back_without_remote(tmp_path: Path) -> None:
    generator = InvalidGenerator()
    coordinator, store, client, _ = _coordinator(tmp_path, generator=generator)
    _ingest(store, _event("first"))

    first = coordinator.sync(GenerateRequest(date="2026-07-30"))
    second = coordinator.sync(GenerateRequest(date="2026-07-30"))
    third = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert first.status == "retry_pending"
    assert second.status == "retry_pending"
    assert third.status == "fallback"
    assert third.used_fallback is True
    assert len(generator.prompts) == 3
    assert len(client.journals) == 1
    assert store.journal_sync_state("2026-07-30")["status"] == "succeeded"


def test_no_safe_events_delete_only_unchanged_managed_remote(tmp_path: Path) -> None:
    coordinator, store, client, _ = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    published = coordinator.sync(GenerateRequest(date="2026-07-30"))
    assert published.journal_id is not None
    assert store.soft_delete_event("first")
    _ingest(
        store,
        _event("secret", 1, "token=secret-value", is_sensitive=True, action="block"),
    )

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "skipped_privacy"
    assert result.warnings == ["elfred_managed_journal_removed"]
    assert client.journals == {}
    state = store.journal_sync_state("2026-07-30")
    assert state is not None
    assert state["remote_id"] is None
    assert state["remote_managed"] == 0


def test_no_safe_events_preserve_manual_modified_remote(tmp_path: Path) -> None:
    coordinator, store, client, _ = _coordinator(tmp_path)
    _ingest(store, _event("first"))
    published = coordinator.sync(GenerateRequest(date="2026-07-30"))
    assert published.journal_id is not None
    client.journals[published.journal_id]["content_ai"] = "manual edit"
    assert store.soft_delete_event("first")

    result = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert result.status == "manual_modified"
    assert client.get_journal(published.journal_id)["content_ai"] == "manual edit"


def test_no_events_preserve_unmanaged_uid_and_detect_duplicates(tmp_path: Path) -> None:
    coordinator, _, client, generator = _coordinator(tmp_path)
    payload = {
        "uid": "elfred-daily-2026-07-30",
        "name": "manual journal",
        "date": "2026-07-30T12:00:00+08:00",
    }
    remote = client.create_journal(payload)

    adopted = coordinator.sync(GenerateRequest(date="2026-07-30"))
    client.create_journal(payload)
    duplicate = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert adopted.status == "adopted_existing"
    assert duplicate.status == "duplicate_uid"
    assert client.get_journal(remote["id"])["name"] == "manual journal"
    assert generator.prompts == []


def test_managed_delete_error_retries_and_recovers(tmp_path: Path) -> None:
    client = FailFirstDeleteClient()
    coordinator, store, _, _ = _coordinator(tmp_path, client=client)
    _ingest(store, _event("first"))
    coordinator.sync(GenerateRequest(date="2026-07-30"))
    assert store.soft_delete_event("first")

    failed = coordinator.sync(GenerateRequest(date="2026-07-30"))
    recovered = coordinator.sync(GenerateRequest(date="2026-07-30"))

    assert failed.status == "retry_pending"
    assert recovered.status == "skipped_no_events"
    assert client.journals == {}
