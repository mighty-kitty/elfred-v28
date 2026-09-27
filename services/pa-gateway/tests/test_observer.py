# -*- coding: utf-8 -*-
"""WP-05 desktop intake gate: what the PA may see and what it may keep.

The Observer is a real local service (existing/alfred-observer). These tests use
fakes so the rules are pinned down without a desktop; the live run against the
real Observer is covered by tests/observer_full_test.py in the repo root.
"""
import app.main as main_mod
from fastapi.testclient import TestClient

from app.main import app
from app.manifest import build_manifest
from app.models import Run
from app.observer import build_observer_context, event_is_sensitive, suggestion_action

c = TestClient(app)


def _event(event_id="ev_1", app_name="ChatGPT", title="Elfred roadmap", **privacy):
    return {
        "event_id": event_id,
        "created_at": "2026-09-11T14:48:28+08:00",
        "app": {"name": app_name, "category": "ai_tool", "window_title": title},
        "trigger": {"type": "manual_hotkey"},
        "content": {"summary": f"working on {title}"},
        "privacy": {"is_sensitive": False, "action": "allow", **privacy},
        "status": "temporary_context",
    }


def _new_run(run_id):
    return Run(run_id=run_id, pa_id="pa_redact", query_summary="what am I working on",
               created_at="now", updated_at="now")


def _suggestion(**kw):
    payload = {
        "suggestion_id": "sug_1",
        "event_id": "ev_1",
        "suggestion_type": "confirm_required",
        "memory_cycle": "short_term",
        "title": "Elfred roadmap",
        "summary": "user was reading the Elfred roadmap in ChatGPT",
        "requires_user_confirmation": True,
        "privacy_flags": [],
    }
    payload.update(kw)
    return {"item_id": "item_1", "item_type": "memory_write_suggestion",
            "status": "pending", "payload": payload}


class _FakeObserver:
    def __init__(self, events=None, outbox=None, health_ok=True):
        self.events = list(events or [])
        self.outbox_items = list(outbox or [])
        self.sent = []
        self.deleted = []
        self.health_ok = health_ok

    def health(self):
        if not self.health_ok:
            raise RuntimeError("observer down")
        return {"ok": True, "service": "elfred_desktop_observer", "mode": "real",
                "ocr_engine": "fallback", "asr": {"available": False}}

    def recent_events(self, limit=10):
        return self.events[:limit]

    def outbox(self, status=""):
        return [i for i in self.outbox_items if i.get("status", "pending") == "pending"]

    def mark_outbox_sent(self, item_id):
        self.sent.append(item_id)
        return {"marked_sent": True, "item_id": item_id}

    def delete_event(self, event_id):
        self.deleted.append(("event", event_id))
        return {"deleted": True, "event_id": event_id}

    def delete_app_data(self, app_name):
        self.deleted.append(("app", app_name))
        return {"deleted_events": 2, "app_name": app_name}

    def clear_temporary_context(self):
        self.deleted.append(("temporary", ""))
        return {"deleted_events": 3}


class _FakeEmos:
    def __init__(self, write_ok=True):
        self.write_ok = write_ok
        self.writes = []

    def recall(self, user_id, query_text, **kw):
        return {"payload": {"recalled_memory": None, "evidence": []}}

    def write(self, user_id, session_id, text, **kw):
        self.writes.append((user_id, session_id, text))
        if not self.write_ok:
            return {"payload": {"memory_written": False, "memory_id": None}}
        return {"payload": {"memory_written": True, "memory_id": "mem_desktop_1"}}


def _engine(monkeypatch, observer, emos=None):
    engine = main_mod.engine
    monkeypatch.setattr(engine, "observer", observer)
    if emos is not None:
        monkeypatch.setattr(engine, "emos", emos)
    return engine


def _pa():
    return c.post("/v1/pa/profiles", json={"user_id": "u_observer",
                                           "consent_version": 1}).json()["pa_id"]


# ------------------------------------------------------------- the gate itself


def test_sensitive_event_is_detected_by_flag_action_or_type():
    assert event_is_sensitive(_event(is_sensitive=True))
    assert event_is_sensitive(_event(action="block"))
    assert event_is_sensitive(_event(sensitivity_types=["password"]))
    assert event_is_sensitive({"app": {"category": "payment"}})
    assert not event_is_sensitive(_event())


def test_context_block_keeps_safe_events_and_records_the_drop():
    block = build_observer_context([
        _event("ev_ok", title="Elfred roadmap"),
        _event("ev_secret", title="bank transfer", is_sensitive=True,
               sensitivity_types=["payment"]),
    ])
    assert [e["event_id"] for e in block["events"]] == ["ev_ok"]
    assert block["gate"]["considered"] == 2
    assert block["gate"]["included"] == 1
    assert block["gate"]["dropped"] == 1
    assert block["gate"]["dropped_reasons"] == {"sensitive": 1}


def test_projected_event_explains_why_the_pa_knows():
    kept = build_observer_context([_event("ev_ok", title="Elfred roadmap")])["events"][0]
    assert kept["app"] == "ChatGPT"
    assert kept["window_title"] == "Elfred roadmap"
    assert "observer saw ChatGPT" in kept["why"]
    assert "not long-term memory" in kept["why"]
    # the raw OCR dump and the screenshot paths stay out of the manifest
    assert "detail" not in kept and "screenshot_path" not in kept


def test_manifest_carries_observer_events_and_the_gate():
    block = build_observer_context([_event("ev_ok"), _event("ev_bad", is_sensitive=True)])
    ctx = {"observer_events": block["events"], "observer_gate": block["gate"],
           "observer_event_refs": [e["event_id"] for e in block["events"]]}
    manifest = build_manifest("run_1", "what am I working on", None, ctx, [])
    assert manifest["observer_event_refs"] == ["ev_ok"]
    assert manifest["observer_events"][0]["why"]
    assert manifest["observer_gate"]["dropped"] == 1


def test_redaction_does_not_flatten_projected_events():
    """The observer block must survive redact() as real values, not <max-depth>."""
    engine = main_mod.engine
    original = engine.observer
    engine.observer = _FakeObserver([_event("ev_ok", title="Elfred roadmap")])
    try:
        run = main_mod.store.save_run(_new_run("run_redact"))
        ctx, _log = engine._build_context(run)
    finally:
        engine.observer = original
    assert ctx["observer_event_refs"] == ["ev_ok"]
    assert ctx["observer_events"][0]["summary"] == "working on Elfred roadmap"
    assert ctx["observer_gate"]["included"] == 1


# ----------------------------------------------------------- outbox decisions


def test_suggestion_gate_writes_holds_and_blocks():
    def action(**kw):
        return suggestion_action(_suggestion(**kw)["payload"], False)[0]

    assert action(requires_user_confirmation=False) == "write"
    assert action() == "hold"
    assert suggestion_action(_suggestion()["payload"], True)[0] == "write"
    assert action(privacy_flags=["payment"]) == "blocked"
    assert action(suggestion_type="ignore") == "blocked"
    assert action(memory_cycle="temporary") == "blocked"
    # fail closed: a payload the gate cannot read is not memory
    assert suggestion_action({}, True)[0] == "blocked"


def test_drain_holds_unconfirmed_captures(monkeypatch):
    obs = _FakeObserver(outbox=[_suggestion()])
    emos = _FakeEmos()
    engine = _engine(monkeypatch, obs, emos)
    report = engine.drain_observer_outbox(_pa(), confirmed=False)
    assert report["summary"] == {"written": 0, "held": 1, "blocked": 0, "errors": 0}
    assert emos.writes == []
    assert obs.sent == [], "a held suggestion must stay in the outbox"


def test_drain_writes_a_confirmed_capture_and_clears_it(monkeypatch):
    obs = _FakeObserver(outbox=[_suggestion()])
    emos = _FakeEmos()
    engine = _engine(monkeypatch, obs, emos)
    pa = _pa()
    report = engine.drain_observer_outbox(pa, confirmed=True)
    assert report["summary"]["written"] == 1
    assert report["written"][0]["memory_id"] == "mem_desktop_1"
    assert obs.sent == ["item_1"]
    assert emos.writes[0][0] == pa
    assert "ev_1" in emos.writes[0][2], "the memory keeps its provenance in-band"


def test_drain_blocks_privacy_flagged_captures_even_when_confirmed(monkeypatch):
    obs = _FakeObserver(outbox=[_suggestion(privacy_flags=["payment"])])
    emos = _FakeEmos()
    engine = _engine(monkeypatch, obs, emos)
    report = engine.drain_observer_outbox(_pa(), confirmed=True)
    assert report["summary"]["blocked"] == 1
    assert emos.writes == []
    assert obs.sent == ["item_1"], "a terminal block must not stay pending forever"


def test_drain_reports_an_emos_refusal_instead_of_losing_it(monkeypatch):
    obs = _FakeObserver(outbox=[_suggestion(requires_user_confirmation=False)])
    engine = _engine(monkeypatch, obs, _FakeEmos(write_ok=False))
    report = engine.drain_observer_outbox(_pa(), confirmed=True)
    assert report["summary"]["errors"] == 1
    assert obs.sent == [], "an unwritten capture stays queued so it can be retried"


def test_drain_rejects_an_unknown_pa(monkeypatch):
    _engine(monkeypatch, _FakeObserver(), _FakeEmos())
    assert c.post("/v1/observer/outbox/drain", json={"pa_id": "pa_nope"}).status_code == 404


def test_drain_needs_a_pa_because_memory_is_namespaced(monkeypatch):
    _engine(monkeypatch, _FakeObserver(), _FakeEmos())
    assert c.post("/v1/observer/outbox/drain", json={}).status_code == 422


# --------------------------------------------------------------------- forget


def test_forget_by_event_app_and_temporary(monkeypatch):
    obs = _FakeObserver()
    engine = _engine(monkeypatch, obs)
    assert engine.forget_observer(event_id="ev_1")["observer"]["deleted"] is True
    assert engine.forget_observer(app_name="ChatGPT")["observer"]["deleted_events"] == 2
    assert engine.forget_observer(temporary=True)["observer"]["deleted_events"] == 3
    assert obs.deleted == [("event", "ev_1"), ("app", "ChatGPT"), ("temporary", "")]


def test_forget_without_a_scope_is_rejected(monkeypatch):
    _engine(monkeypatch, _FakeObserver())
    assert c.post("/v1/observer/forget", json={}).status_code == 422


def test_forget_makes_the_refs_disappear_from_the_next_manifest(monkeypatch):
    """After forget the event is gone, so a new run cannot cite it."""
    obs = _FakeObserver([_event("ev_1")])
    engine = _engine(monkeypatch, obs)
    run = main_mod.store.save_run(_new_run("run_forget_before"))
    before, _ = engine._build_context(run)
    assert before["observer_event_refs"] == ["ev_1"]
    obs.events = []
    after, _ = engine._build_context(run)
    assert after["observer_event_refs"] == []
    assert after["observer_gate"]["included"] == 0


# --------------------------------------------------------------- capture state


def test_observer_health_reports_a_dead_service_as_unreachable(monkeypatch):
    _engine(monkeypatch, _FakeObserver(health_ok=False))
    body = c.get("/v1/observer/health").json()
    assert body["configured"] is True and body["reachable"] is False


def test_observer_health_reports_capture_mode_and_pending_queue(monkeypatch):
    _engine(monkeypatch, _FakeObserver(outbox=[_suggestion()]))
    body = c.get("/v1/observer/health").json()
    assert body["mode"] == "real"
    assert body["pending_outbox"] == 1
    assert body["asr"]["available"] is False, "a degraded channel must be visible"


def test_observer_events_endpoint_annotates_the_gate(monkeypatch):
    _engine(monkeypatch, _FakeObserver([_event("ev_ok"), _event("ev_bad", is_sensitive=True)]))
    body = c.get("/v1/observer/events").json()
    assert [e["event_id"] for e in body["events"]] == ["ev_ok"]
    assert body["gate"]["considered"] == 2
    assert body["total_recorded"] == 2
