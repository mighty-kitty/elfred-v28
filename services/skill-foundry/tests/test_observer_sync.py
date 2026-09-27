"""observer_sync 单元测试 — 状态管理 + 去重逻辑"""

from __future__ import annotations

from datetime import datetime
from unittest import mock

from adapter.observer_sync import ObserverAutoSync, _now


# ── _now() ──

def test_now_returns_iso_string():
    result = _now()
    assert isinstance(result, str)
    assert "T" in result  # ISO 8601 包含 T
    # 可解析
    datetime.fromisoformat(result.replace("Z", "+00:00"))


# ── status() ──

def test_status_returns_dict_copy():
    class FakeService:
        settings = mock.Mock(
            observer_auto_sync_interval_seconds=2.0,
            observer_auto_sync_limit=50,
            observer_auto_sync_backfill=False,
        )

    sync = ObserverAutoSync(FakeService())
    status = sync.status()
    assert status["state"] == "created"
    assert status["processed_events"] == 0
    # 副本，修改不影响内部状态
    status["state"] = "modified"
    assert sync.status()["state"] == "created"


# ── _poll_recent_once: 去重 ──

def test_poll_recent_baseline_populates_known_ids():
    events = [
        {"event_id": "e1", "content": {"summary": "a"}},
        {"event_id": "e2", "content": {"summary": "b"}},
    ]

    class FakeService:
        settings = mock.Mock(
            observer_auto_sync_interval_seconds=2.0,
            observer_auto_sync_limit=50,
            observer_auto_sync_backfill=False,
            request_timeout_seconds=8.0,
            observer_base_url="http://localhost",
        )

    sync = ObserverAutoSync(FakeService())
    sync._fetch_events = lambda: events

    result = sync.poll_once()
    assert result["baseline"] == 2
    assert result["processed"] == 0
    assert sync.status()["state"] == "watching"


def test_poll_recent_filters_duplicates():
    events = [
        {"event_id": "e1", "content": {"summary": "a"}},
        {"event_id": "e2", "content": {"summary": "b"}},
    ]

    class FakeService:
        settings = mock.Mock(
            observer_auto_sync_interval_seconds=2.0,
            observer_auto_sync_limit=50,
            observer_auto_sync_backfill=False,
            request_timeout_seconds=8.0,
            observer_base_url="http://localhost",
        )
        def process_payload(self, payload):
            return None

    sync = ObserverAutoSync(FakeService())
    sync._fetch_events = lambda: events

    # first poll: baseline
    sync.poll_once()
    # second poll: duplicates filtered
    result = sync.poll_once()
    assert result["processed"] == 0  # no new events


def test_poll_recent_processes_new_events():
    class FakeService:
        settings = mock.Mock(
            observer_auto_sync_interval_seconds=2.0,
            observer_auto_sync_limit=50,
            observer_auto_sync_backfill=False,
            request_timeout_seconds=8.0,
            observer_base_url="http://localhost",
        )
        def process_payload(self, payload):
            return None

    sync = ObserverAutoSync(FakeService())
    sync._fetch_events = lambda: [{"event_id": "e1"}]
    sync.poll_once()  # baseline

    sync._fetch_events = lambda: [{"event_id": "e2"}, {"event_id": "e3"}]
    result = sync.poll_once()
    assert result["processed"] == 2


# ── backfill mode ──

def test_backfill_mode_loads_cursor():
    fake_store = mock.Mock()
    fake_store.get_setting = lambda k: "cursor-v1-test"

    class FakeService:
        settings = mock.Mock(
            observer_auto_sync_interval_seconds=2.0,
            observer_auto_sync_limit=50,
            observer_auto_sync_backfill=True,
            request_timeout_seconds=8.0,
            observer_base_url="http://localhost",
        )
        store = fake_store

    sync = ObserverAutoSync(FakeService())
    assert sync._cursor == "cursor-v1-test"
    assert sync.status()["mode"] == "feed_backfill"
