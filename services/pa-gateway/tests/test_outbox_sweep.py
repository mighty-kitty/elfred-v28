# -*- coding: utf-8 -*-
"""The observer outbox must be bounded, and expiring must never write memory."""
import time

import pytest

from app.engine import RunEngine


class _FakeObserver:
    def __init__(self, items):
        self.items = list(items)
        self.sent = []

    def outbox(self, status=""):
        return [i for i in self.items if i.get("status", "pending") == "pending"]

    def mark_outbox_sent(self, item_id):
        self.sent.append(item_id)
        for item in self.items:
            if item["item_id"] == item_id:
                item["status"] = "sent"
        return {"marked_sent": True}


class _FakeEmos:
    def __init__(self):
        self.writes = []

    def write(self, *args, **kwargs):  # pragma: no cover - must never be called
        self.writes.append(args)
        return {"payload": {"memory_written": True, "memory_id": "nope"}}


def _item(index, age_days):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S",
                          time.gmtime(time.time() - age_days * 86400))
    return {"item_id": f"item_{index}", "item_type": "memory_write_suggestion",
            "status": "pending", "created_at": stamp,
            "payload": {"event_id": f"ev_{index}", "suggestion_type": "confirm_required",
                        "requires_user_confirmation": True, "memory_cycle": "short_term"}}


def _engine(items):
    observer = _FakeObserver(items)
    emos = _FakeEmos()
    engine = RunEngine(store=None, emos=emos, observer=observer)
    return engine, observer, emos


def test_sweep_keeps_the_newest_and_expires_the_rest_by_count():
    engine, observer, emos = _engine([_item(i, 0.1) for i in range(12)])
    report = engine.sweep_observer_outbox(max_age_days=7, keep_newest=5)
    assert report["summary"]["kept"] == 5
    assert report["summary"]["expired"] == 7
    assert len(observer.sent) == 7
    assert emos.writes == [], "expiring a suggestion must never write memory"
    assert len(observer.outbox()) == 5


def test_sweep_expires_by_age_even_under_the_count_cap():
    items = [_item(1, 0.2), _item(2, 0.3), _item(3, 30.0)]
    engine, observer, _emos = _engine(items)
    report = engine.sweep_observer_outbox(max_age_days=7, keep_newest=100)
    assert report["expired_by_age"] == ["item_3"]
    assert set(report["kept"]) == {"item_1", "item_2"}
    assert observer.sent == ["item_3"]


def test_an_empty_outbox_is_not_an_error():
    engine, _observer, _emos = _engine([])
    report = engine.sweep_observer_outbox()
    assert report["summary"] == {"expired": 0, "kept": 0}


def test_an_unparsable_timestamp_does_not_expire_data():
    broken = _item(9, 0.1)
    broken["created_at"] = "not-a-date"
    engine, observer, _emos = _engine([broken])
    report = engine.sweep_observer_outbox(max_age_days=0.001, keep_newest=100)
    assert report["kept"] == ["item_9"] and observer.sent == []


def test_sweeper_does_not_start_without_an_observer():
    engine = RunEngine(store=None, observer=None)
    assert engine.start_observer_outbox_sweeper(0.1) is False
