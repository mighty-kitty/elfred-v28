from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from adapter.contracts import payload_hash
from adapter.freetodo_client import FreeTodoError
from adapter.journal.legacy import is_unmodified_legacy_fallback
from adapter.journal.models import GenerateRequest, GenerateResponse
from adapter.journal.prompt import PROMPT_VERSION
from adapter.journal.service import JournalService
from adapter.transform import daily_digest


logger = logging.getLogger("elfred.journal.coordinator")
PRIVACY_VERSION = "journal-auto-v1"


class JournalLeaseLost(RuntimeError):
    pass


class JournalCoordinator:
    """Single durable orchestration path for every daily Journal trigger."""

    def __init__(
        self,
        journal: JournalService,
        store: Any,
        publisher: Any,
        *,
        max_events: int = 30,
        max_attempts: int = 6,
        retry_base_seconds: float = 10.0,
        lease_seconds: float = 600.0,
        on_published: Callable[[GenerateResponse], None] | None = None,
    ) -> None:
        self.journal = journal
        self.store = store
        self.publisher = publisher
        self.max_events = max(1, int(max_events))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_base_seconds = max(0.0, float(retry_base_seconds))
        self.lease_seconds = max(1.0, float(lease_seconds))
        self.on_published = on_published
        self._source_ready: Callable[[], bool] = lambda: True

    @property
    def enabled(self) -> bool:
        return self.journal.enabled

    def enqueue(self, day: str, *, trigger: str) -> dict[str, Any]:
        self._validate_day(day)
        return self.store.enqueue_journal_day(day, trigger)

    def set_source_ready_provider(self, provider: Callable[[], bool]) -> None:
        self._source_ready = provider

    def sync(
        self,
        request: GenerateRequest,
        *,
        trigger: str = "manual",
        source_ready: bool | None = None,
    ) -> GenerateResponse:
        self._validate_day(request.date)
        if request.dry_run:
            records = self.store.events_for_day(request.date)
            return self.journal.generate(
                GenerateRequest(
                    date=request.date,
                    dry_run=True,
                    max_events=min(
                        max(1, int(request.max_events)),
                        self.max_events,
                    ),
                ),
                events=self._raw_events(records),
                todo_ids=self._todo_ids(records),
                topic_names=self._topic_names(records),
            )

        self.enqueue(request.date, trigger=trigger)
        claimed = self.store.claim_journal_day(
            request.date,
            lease_seconds=self.lease_seconds,
        )
        if claimed is None:
            return GenerateResponse(status="busy")
        ready = bool(self._source_ready()) if source_ready is None else source_ready
        try:
            if not ready:
                return self._defer_source(request.date, claimed)
            return self._sync_claimed(request, claimed)
        except JournalLeaseLost:
            return self._lease_lost_response(claimed)
        except Exception as error:
            logger.exception("Unexpected Journal synchronization failure")
            try:
                return self._defer_failure(request.date, claimed, error)
            except JournalLeaseLost:
                return self._lease_lost_response(claimed)

    def process_next(self, *, source_ready: bool = True) -> GenerateResponse | None:
        claimed = self.store.claim_next_journal_day(
            lease_seconds=self.lease_seconds,
        )
        if claimed is None:
            return None
        day = str(claimed["journal_date"])
        try:
            if not source_ready:
                return self._defer_source(day, claimed)
            return self._sync_claimed(
                GenerateRequest(date=day, max_events=self.max_events),
                claimed,
            )
        except JournalLeaseLost:
            return self._lease_lost_response(claimed)
        except Exception as error:
            logger.exception("Unexpected Journal worker failure for %s", day)
            try:
                return self._defer_failure(day, claimed, error)
            except JournalLeaseLost:
                return self._lease_lost_response(claimed)

    def status(self) -> dict[str, Any]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT status,COUNT(*) AS count FROM journal_sync_state
                GROUP BY status"""
            ).fetchall()
            latest = connection.execute(
                """SELECT journal_date,status,attempt_count,next_attempt_at,
                last_error,updated_at,hardware_status,hardware_error
                FROM journal_sync_state ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
        return {
            "enabled": self.enabled,
            "states": {str(row["status"]): int(row["count"]) for row in rows},
            "latest": dict(latest) if latest else None,
        }

    def _sync_claimed(
        self,
        request: GenerateRequest,
        state: dict[str, Any],
    ) -> GenerateResponse:
        day = request.date
        self._lease_token(state)
        records = self.store.events_for_day(day)
        raw_events = self._raw_events(records)
        safe_events, excluded_count = self.journal.privacy_safe_events(raw_events)
        safe_ids = {str(event["event_id"]) for event in safe_events}
        eligible_records = [
            record for record in records if str(record["event_id"]) in safe_ids
        ]
        todo_ids = self._todo_ids(eligible_records)
        topic_names = self._topic_names(eligible_records)
        source_hash = payload_hash(
            {
                "events": safe_events,
                "todo_ids": todo_ids,
                "topic_names": topic_names,
                "prompt_version": PROMPT_VERSION,
                "privacy_version": PRIVACY_VERSION,
            }
        )
        prompt_limit = min(
            max(1, int(request.max_events or self.max_events)),
            self.max_events,
        )

        try:
            remotes = [
                item
                for item in self.publisher.list_journals()
                if item.get("uid") == f"elfred-daily-{day}"
            ]
        except FreeTodoError as error:
            return self._defer_failure(day, state, error)

        if len(remotes) > 1:
            self._finalize(
                day,
                state,
                status="duplicate_uid",
                source_hash=source_hash,
                source_event_count=len(safe_events),
                excluded_event_count=excluded_count,
                next_attempt_at=None,
                last_error="multiple FreeTodo journals use the same Elfred uid",
            )
            return GenerateResponse(
                status="duplicate_uid",
                warnings=["multiple_journals_with_same_uid"],
                excluded_event_count=excluded_count,
            )

        remote = remotes[0] if remotes else None
        if not safe_events:
            return self._sync_without_safe_events(
                day,
                state,
                remote,
                source_hash,
                excluded_count,
            )

        remote_hash = self._remote_hash(remote) if remote else None
        baseline_hash = state.get("last_remote_hash")
        candidate = state.get("candidate")
        candidate_same_source = bool(
            candidate and state.get("source_hash") == source_hash
        )

        if (
            remote is not None
            and not baseline_hash
            and is_unmodified_legacy_fallback(
                remote,
                day,
                self.store.legacy_events_for_day(day),
                prompt_limit,
            )
        ):
            self._update_claimed(
                day,
                state,
                last_remote_hash=remote_hash,
                last_remote_json=remote,
                remote_id=int(remote["id"]),
                remote_managed=1,
            )
            baseline_hash = remote_hash
            state["last_remote_hash"] = remote_hash
            state["remote_managed"] = 1

        if remote is not None and not baseline_hash:
            if candidate_same_source and self._remote_matches(remote, candidate):
                return self._recover_published(
                    request,
                    state,
                    remote,
                    eligible_records,
                    source_hash,
                    excluded_count,
                )
            self._finalize(
                day,
                state,
                status="adopted_existing",
                source_hash=source_hash,
                remote_id=int(remote["id"]),
                last_remote_hash=remote_hash,
                last_remote_json=remote,
                remote_managed=0,
                source_event_count=len(safe_events),
                included_event_count=0,
                excluded_event_count=excluded_count,
                attempt_count=0,
                next_attempt_at=None,
                last_error=None,
                hardware_status="disabled",
            )
            self._record_remote_links(eligible_records, remote, day, "synced")
            return GenerateResponse(
                status="adopted_existing",
                journal_id=int(remote["id"]),
                excluded_event_count=excluded_count,
            )

        if remote is not None and baseline_hash and remote_hash != baseline_hash:
            if candidate_same_source and self._remote_matches(remote, candidate):
                return self._recover_published(
                    request,
                    state,
                    remote,
                    eligible_records,
                    source_hash,
                    excluded_count,
                )
            return self._preserve_manual_modification(
                day,
                state,
                remote,
                eligible_records,
                source_hash,
                len(safe_events),
                excluded_count,
            )

        if state.get("source_hash") == source_hash:
            if candidate_same_source and remote is not None:
                response = self._response_from_state(state, remote)
                response.status = "noop_unchanged"
                hold_for_hardware = self._needs_hardware(response)
                finalized = self._finalize(
                    day,
                    state,
                    status="succeeded",
                    next_attempt_at=None,
                    last_error=None,
                    release_lease=not hold_for_hardware,
                )
                if finalized.get("status") == "succeeded" and hold_for_hardware:
                    self._ensure_hardware(day, state, response)
                return response
            if candidate is None and remote is not None:
                self._finalize(
                    day,
                    state,
                    status="adopted_existing",
                    next_attempt_at=None,
                    last_error=None,
                )
                return GenerateResponse(
                    status="noop_unchanged",
                    journal_id=int(remote["id"]),
                    excluded_event_count=excluded_count,
                )

        response: GenerateResponse
        if candidate_same_source:
            response = self._response_from_state(state, remote)
        elif not self.journal.enabled:
            response = GenerateResponse(
                status="fallback",
                payload=daily_digest(
                    day,
                    eligible_records,
                    todo_ids,
                    topic_names,
                ),
                used_fallback=True,
                excluded_event_count=excluded_count,
            )
        else:
            response = self.journal.generate(
                GenerateRequest(
                    date=day,
                    dry_run=False,
                    max_events=prompt_limit,
                ),
                events=raw_events,
                todo_ids=todo_ids,
                topic_names=topic_names,
                fallback_on_error=False,
            )
            if response.status == "generation_failed":
                attempts = int(state.get("attempt_count") or 0) + 1
                if attempts < self.max_attempts or remote is not None:
                    return self._defer_failure(
                        day,
                        state,
                        response.warnings[-1]
                        if response.warnings
                        else "generation failed",
                    )
                response = GenerateResponse(
                    status="fallback",
                    payload=daily_digest(
                        day,
                        eligible_records,
                        todo_ids,
                        topic_names,
                    ),
                    used_fallback=True,
                    excluded_event_count=excluded_count,
                )
                response.warnings.append("journal_generation_retries_exhausted")

        if not candidate_same_source:
            if response.payload is None:
                self._finalize(
                    day,
                    state,
                    status=response.status,
                    next_attempt_at=None,
                )
                return response
            candidate = response.payload
            group = self.journal.grouper.build(
                safe_events,
                day,
                todo_ids,
                topic_names,
                prompt_limit,
            )
            self._update_claimed(
                day,
                state,
                status="running",
                source_hash=source_hash,
                candidate_hash=payload_hash(candidate),
                candidate_status=response.status,
                candidate_json=candidate,
                source_event_count=len(safe_events),
                included_event_count=group.included_event_count,
                excluded_event_count=excluded_count,
                prompt_version=PROMPT_VERSION,
                privacy_version=PRIVACY_VERSION,
            )
            state["candidate"] = candidate
            state["candidate_status"] = response.status
            state["source_hash"] = source_hash

        self._renew_lease(day, state)
        if remote is not None:
            try:
                latest_remote = self.publisher.get_journal(int(remote["id"]))
            except FreeTodoError as error:
                return self._defer_failure(day, state, error)
            if self._remote_hash(latest_remote) != remote_hash:
                return self._preserve_manual_modification(
                    day,
                    state,
                    latest_remote,
                    eligible_records,
                    source_hash,
                    len(safe_events),
                    excluded_count,
                )
            remote = latest_remote
        try:
            if remote is None:
                remote = self.publisher.create_journal(candidate)
                operation = "journal_create"
            else:
                remote = self.publisher.update_journal(
                    int(remote["id"]),
                    {key: value for key, value in candidate.items() if key != "uid"},
                )
                operation = "journal_update"
        except FreeTodoError as error:
            return self._defer_failure(day, state, error)

        response.journal_id = int(remote["id"])
        hold_for_hardware = self._needs_hardware(response)
        finalized = self._finalize(
            day,
            state,
            status="succeeded",
            remote_id=int(remote["id"]),
            last_remote_hash=self._remote_hash(remote),
            last_remote_json=remote,
            remote_managed=1,
            attempt_count=0,
            next_attempt_at=None,
            last_error=None,
            hardware_status=("pending" if self.on_published else "disabled"),
            hardware_error=None,
            release_lease=not hold_for_hardware,
        )
        logger.info("%s succeeded for %s", operation, day)
        self._record_remote_links(eligible_records, remote, day, "synced")
        if finalized.get("status") == "succeeded":
            if hold_for_hardware:
                self._ensure_hardware(day, state, response)
        return response

    def _preserve_manual_modification(
        self,
        day: str,
        state: dict[str, Any],
        remote: dict[str, Any],
        records: list[dict[str, Any]],
        source_hash: str,
        source_event_count: int,
        excluded_count: int,
    ) -> GenerateResponse:
        self._finalize(
            day,
            state,
            status="manual_modified",
            source_hash=source_hash,
            remote_id=int(remote["id"]),
            source_event_count=source_event_count,
            excluded_event_count=excluded_count,
            next_attempt_at=None,
            last_error=None,
            hardware_status="disabled",
        )
        self._record_remote_links(records, remote, day, "manual_modified")
        return GenerateResponse(
            status="manual_modified",
            journal_id=int(remote["id"]),
            warnings=["journal_manual_modification_preserved"],
            excluded_event_count=excluded_count,
        )

    def _sync_without_safe_events(
        self,
        day: str,
        state: dict[str, Any],
        remote: dict[str, Any] | None,
        source_hash: str,
        excluded_count: int,
    ) -> GenerateResponse:
        status = "skipped_privacy" if excluded_count else "skipped_no_events"
        common = {
            "source_hash": source_hash,
            "source_event_count": 0,
            "included_event_count": 0,
            "excluded_event_count": excluded_count,
            "attempt_count": 0,
            "next_attempt_at": None,
            "last_error": None,
            "prompt_version": PROMPT_VERSION,
            "privacy_version": PRIVACY_VERSION,
            "hardware_status": "disabled",
            "hardware_error": None,
        }
        if remote is None:
            self._finalize(
                day,
                state,
                status=status,
                candidate_hash=None,
                candidate_status=None,
                candidate_json=None,
                remote_id=None,
                last_remote_hash=None,
                last_remote_json=None,
                remote_managed=0,
                **common,
            )
            return GenerateResponse(
                status=status,
                excluded_event_count=excluded_count,
            )

        remote_hash = self._remote_hash(remote)
        baseline_hash = state.get("last_remote_hash")
        managed = bool(state.get("remote_managed"))
        if managed and baseline_hash and remote_hash == baseline_hash:
            self._renew_lease(day, state)
            try:
                self.publisher.delete_journal(int(remote["id"]))
            except FreeTodoError as error:
                return self._defer_failure(day, state, error)
            self._finalize(
                day,
                state,
                status=status,
                candidate_hash=None,
                candidate_status=None,
                candidate_json=None,
                remote_id=None,
                last_remote_hash=None,
                last_remote_json=None,
                remote_managed=0,
                **common,
            )
            return GenerateResponse(
                status=status,
                warnings=["elfred_managed_journal_removed"],
                excluded_event_count=excluded_count,
            )

        if managed:
            self._finalize(
                day,
                state,
                status="manual_modified",
                remote_id=int(remote["id"]),
                **common,
            )
            return GenerateResponse(
                status="manual_modified",
                journal_id=int(remote["id"]),
                warnings=["journal_manual_modification_preserved"],
                excluded_event_count=excluded_count,
            )

        self._finalize(
            day,
            state,
            status="adopted_existing",
            remote_id=int(remote["id"]),
            last_remote_hash=remote_hash,
            last_remote_json=remote,
            remote_managed=0,
            **common,
        )
        return GenerateResponse(
            status="adopted_existing",
            journal_id=int(remote["id"]),
            warnings=["unmanaged_journal_preserved"],
            excluded_event_count=excluded_count,
        )

    def _recover_published(
        self,
        request: GenerateRequest,
        state: dict[str, Any],
        remote: dict[str, Any],
        records: list[dict[str, Any]],
        source_hash: str,
        excluded_count: int,
    ) -> GenerateResponse:
        response = self._response_from_state(state, remote)
        hold_for_hardware = self._needs_hardware(response)
        finalized = self._finalize(
            request.date,
            state,
            status="succeeded",
            source_hash=source_hash,
            remote_id=int(remote["id"]),
            last_remote_hash=self._remote_hash(remote),
            last_remote_json=remote,
            remote_managed=1,
            excluded_event_count=excluded_count,
            attempt_count=0,
            next_attempt_at=None,
            last_error=None,
            hardware_status=("pending" if self.on_published else "disabled"),
            release_lease=not hold_for_hardware,
        )
        self._record_remote_links(records, remote, request.date, "synced")
        if finalized.get("status") == "succeeded" and hold_for_hardware:
            self._ensure_hardware(request.date, state, response)
        return response

    def _ensure_hardware(
        self,
        day: str,
        state: dict[str, Any],
        response: GenerateResponse,
    ) -> None:
        if self.on_published is None or response.payload is None:
            return
        current = self.store.journal_sync_state(day) or {}
        if current.get("hardware_status") == "succeeded":
            self._finalize(
                day,
                state,
                status="succeeded",
                hardware_status="succeeded",
                next_attempt_at=None,
            )
            return
        self._renew_lease(day, state)
        try:
            self.on_published(response)
        except Exception as error:
            logger.exception("Journal published, but hardware planning failed")
            retry_at = self._retry_delay(int(current.get("attempt_count") or 0))
            self._finalize(
                day,
                state,
                status="succeeded",
                hardware_status="retry_pending",
                hardware_error=str(error)[:2000],
                next_attempt_at=self._next_attempt_iso(retry_at),
            )
            response.warnings.append("hardware_plan_retry_pending")
            return
        self._finalize(
            day,
            state,
            status="succeeded",
            hardware_status="succeeded",
            hardware_error=None,
            next_attempt_at=None,
        )

    def _defer_source(
        self,
        day: str,
        state: dict[str, Any],
    ) -> GenerateResponse:
        deferred = self.store.defer_journal_day(
            day,
            "journal_source_not_ready",
            lease_token=self._lease_token(state),
            retry_after_seconds=max(1.0, self.retry_base_seconds),
            count_attempt=False,
        )
        if deferred is None:
            raise JournalLeaseLost(day)
        return GenerateResponse(
            status="pending_source",
            warnings=["journal_source_not_ready"],
        )

    def _defer_failure(
        self,
        day: str,
        state: dict[str, Any],
        error: Exception | str,
    ) -> GenerateResponse:
        attempts = int(state.get("attempt_count") or 0) + 1
        deferred = self.store.defer_journal_day(
            day,
            str(error),
            lease_token=self._lease_token(state),
            retry_after_seconds=self._retry_delay(attempts),
        )
        if deferred is None:
            raise JournalLeaseLost(day)
        return GenerateResponse(
            status="retry_pending",
            payload=state.get("candidate"),
            warnings=[str(error)],
        )

    def _response_from_state(
        self,
        state: dict[str, Any],
        remote: dict[str, Any] | None,
    ) -> GenerateResponse:
        candidate_status = str(state.get("candidate_status") or "llm_generated")
        return GenerateResponse(
            status=candidate_status,
            journal_id=int(remote["id"]) if remote else state.get("remote_id"),
            payload=state.get("candidate"),
            used_fallback=candidate_status == "fallback",
            excluded_event_count=int(state.get("excluded_event_count") or 0),
        )

    def _record_remote_links(
        self,
        records: list[dict[str, Any]],
        remote: dict[str, Any],
        day: str,
        status: str,
    ) -> None:
        uid = f"elfred-daily-{day}"
        for record in records:
            self.store.upsert_remote_link(
                "journal",
                str(record["event_id"]),
                day,
                int(remote["id"]),
                uid,
                status,
                remote,
            )

    def _finalize(
        self,
        day: str,
        state: dict[str, Any],
        *,
        release_lease: bool = True,
        **values: Any,
    ) -> dict[str, Any]:
        finalized = self.store.finalize_journal_day(
            day,
            int(state.get("requested_generation") or 1),
            self._lease_token(state),
            release_lease=release_lease,
            **values,
        )
        if finalized is None:
            raise JournalLeaseLost(day)
        return finalized

    def _update_claimed(
        self,
        day: str,
        state: dict[str, Any],
        **values: Any,
    ) -> dict[str, Any]:
        updated = self.store.update_claimed_journal_state(
            day,
            self._lease_token(state),
            **values,
        )
        if updated is None:
            raise JournalLeaseLost(day)
        return updated

    def _renew_lease(self, day: str, state: dict[str, Any]) -> None:
        renewed = self.store.renew_journal_lease(
            day,
            self._lease_token(state),
            lease_seconds=max(30.0, self.lease_seconds),
        )
        if renewed is None:
            raise JournalLeaseLost(day)

    @staticmethod
    def _lease_token(state: dict[str, Any]) -> str:
        token = str(state.get("lease_token") or "")
        if not token:
            raise JournalLeaseLost(str(state.get("journal_date") or "unknown"))
        return token

    @staticmethod
    def _lease_lost_response(state: dict[str, Any]) -> GenerateResponse:
        return GenerateResponse(
            status="busy",
            payload=state.get("candidate"),
            warnings=["journal_lease_lost"],
        )

    def _needs_hardware(self, response: GenerateResponse) -> bool:
        return self.on_published is not None and response.payload is not None

    @staticmethod
    def _raw_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [record["payload"]["event"] for record in records]

    def _todo_ids(self, records: list[dict[str, Any]]) -> list[int]:
        values: set[int] = set()
        for record in records:
            links = self.store.remote_links(str(record["event_id"]), "todo")["todo"]
            values.update(
                int(link["freetodo_todo_id"])
                for link in links
                if link.get("freetodo_todo_id") and link.get("status") == "synced"
            )
        return sorted(values)

    def _topic_names(self, records: list[dict[str, Any]]) -> list[str]:
        values = {
            str(topic["display_name"])
            for record in records
            for topic in self.store.topics_for_event(str(record["event_id"]))
            if topic.get("display_name")
        }
        return sorted(values, key=str.casefold)

    def _remote_hash(self, remote: dict[str, Any]) -> str:
        return payload_hash(
            self._normalize_semantic(self.store.remote_semantic(remote))
        )

    def _remote_matches(
        self,
        remote: dict[str, Any],
        candidate: dict[str, Any],
    ) -> bool:
        normalized_remote = self._normalize_semantic(remote)
        normalized_candidate = self._normalize_semantic(candidate)
        return all(
            normalized_remote.get(key) == value
            for key, value in normalized_candidate.items()
        )

    @staticmethod
    def _normalize_semantic(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "tags" in normalized:
            tags = []
            for tag in normalized.get("tags") or []:
                if isinstance(tag, dict):
                    value = tag.get("tag_name") or tag.get("name") or tag.get("tag")
                else:
                    value = tag
                if value is not None:
                    tags.append(str(value))
            normalized["tags"] = sorted(set(tags), key=str.casefold)
        for key in ("related_todo_ids", "related_activity_ids"):
            if key in normalized:
                values = normalized.get(key) or []
                normalized[key] = sorted(
                    int(value.get("id") if isinstance(value, dict) else value)
                    for value in values
                    if (value.get("id") if isinstance(value, dict) else value)
                    is not None
                )
        return normalized

    def _retry_delay(self, attempts: int) -> float:
        return min(3600.0, self.retry_base_seconds * (2 ** max(0, attempts - 1)))

    @staticmethod
    def _next_attempt_iso(seconds: float) -> str:
        from datetime import datetime, timedelta

        return (datetime.now().astimezone() + timedelta(seconds=seconds)).isoformat()

    @staticmethod
    def _validate_day(value: str) -> None:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Journal date must use YYYY-MM-DD") from error
        if parsed.isoformat() != value:
            raise ValueError("Journal date must use YYYY-MM-DD")
