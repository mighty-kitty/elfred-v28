from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class ObserverAutoSync:
    """Persistently backfill and follow Observer ContextEvents in feed order."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.interval = max(0.25, service.settings.observer_auto_sync_interval_seconds)
        self.limit = max(1, min(1000, service.settings.observer_auto_sync_limit))
        self.backfill = bool(getattr(service.settings, "observer_auto_sync_backfill", False))
        self._cursor_key = "observer_auto_sync.feed_cursor.v1"
        self._cursor: str | None = None
        if self.backfill and hasattr(service, "store"):
            self._cursor = service.store.get_setting(self._cursor_key)
        self._known_event_ids: set[str] = set()
        self._initialized = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "created",
            "baseline_events": 0,
            "processed_events": 0,
            "last_error": None,
            "last_poll_at": None,
            "last_event_id": None,
            "mode": "feed_backfill" if self.backfill else "recent_only",
            "cursor": self._cursor,
            "has_more": None,
            "source_total": None,
            "source_generation": None,
            "cursor_reset": False,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="elfred-observer-auto-sync",
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

    def poll_once(self) -> dict[str, Any]:
        if self.backfill:
            return self._poll_feed_once()
        return self._poll_recent_once()

    def _poll_recent_once(self) -> dict[str, Any]:
        events = self._fetch_events()
        event_ids = {
            str(event.get("event_id"))
            for event in events
            if isinstance(event, dict) and event.get("event_id")
        }
        if not self._initialized:
            self._known_event_ids.update(event_ids)
            self._initialized = True
            self._update(
                state="watching",
                baseline_events=len(event_ids),
                last_error=None,
                last_poll_at=_now(),
            )
            return {"baseline": len(event_ids), "processed": 0}

        new_events = [
            event
            for event in reversed(events)
            if isinstance(event, dict)
            and event.get("event_id")
            and str(event["event_id"]) not in self._known_event_ids
        ]
        processed = 0
        processor = getattr(self.service, "enqueue_payload", self.service.process_payload)
        for event in new_events:
            event_id = str(event["event_id"])
            try:
                processor(event)
            except Exception as error:  # keep the watcher alive; API/job logs carry event detail
                self._update(state="degraded", last_error=f"{event_id}: {error}", last_poll_at=_now())
                continue
            self._known_event_ids.add(event_id)
            processed += 1
            current = self.status()["processed_events"]
            self._update(
                state="watching",
                processed_events=current + 1,
                last_event_id=event_id,
                last_error=None,
                last_poll_at=_now(),
            )
        if not new_events:
            self._update(state="watching", last_error=None, last_poll_at=_now())
        return {"baseline": 0, "processed": processed}

    def _poll_feed_once(self) -> dict[str, Any]:
        payload = self._fetch_feed()
        events = payload.get("events") or []
        if not isinstance(events, list):
            raise RuntimeError("Observer feed response has no events array")
        processor = getattr(self.service, "enqueue_payload", self.service.process_payload)
        processed = 0
        last_event_id: str | None = None
        for event in events:
            if not isinstance(event, dict) or not event.get("event_id"):
                continue
            processor(event)
            processed += 1
            last_event_id = str(event["event_id"])

        next_cursor = payload.get("next_cursor") or self._cursor
        if next_cursor != self._cursor:
            self._cursor = str(next_cursor) if next_cursor else None
            if hasattr(self.service, "store"):
                self.service.store.set_setting(self._cursor_key, self._cursor)
        current = self.status()["processed_events"]
        self._initialized = True
        self._update(
            state="backfilling" if payload.get("has_more") else "watching",
            processed_events=current + processed,
            last_event_id=last_event_id or self.status().get("last_event_id"),
            last_error=None,
            last_poll_at=_now(),
            cursor=self._cursor,
            has_more=bool(payload.get("has_more")),
            source_total=payload.get("total"),
            source_generation=payload.get("source_generation"),
            cursor_reset=bool(payload.get("cursor_reset")),
        )
        return {
            "baseline": 0,
            "processed": processed,
            "has_more": bool(payload.get("has_more")),
        }

    def _fetch_events(self) -> list[dict[str, Any]]:
        url = self.service.settings.observer_base_url + "/events/recent?" + urllib.parse.urlencode(
            {"limit": self.limit}
        )
        try:
            with urllib.request.urlopen(
                url, timeout=self.service.settings.request_timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Observer auto-sync failed: {error}") from error
        events = payload.get("events") if isinstance(payload, dict) else payload
        if not isinstance(events, list):
            raise RuntimeError("Observer auto-sync response has no events array")
        return events

    def _fetch_feed(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": min(200, self.limit),
            "include_total": "true",
        }
        if self._cursor:
            params["cursor"] = self._cursor
        url = self.service.settings.observer_base_url + "/events/feed?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(
                url, timeout=self.service.settings.request_timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Observer feed sync failed: {error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("Observer feed returned a non-object response")
        return payload

    def _run(self) -> None:
        self._update(state="starting")
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as error:
                self._update(state="degraded", last_error=str(error), last_poll_at=_now())
            self._stop.wait(self.interval)
        self._update(state="stopped")

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._status.update(values)
