# -*- coding: utf-8 -*-
"""Observer intake gate (execution book WP-05).

The Observer (:8781) is the desktop intake layer: it decides whether a capture is
allowed, screenshots and OCRs locally, and stores a ContextEvent plus a
MemoryWriteSuggestion. It never writes long-term memory itself.

This module is the *second* gate, on the gateway side, and it is deliberately
conservative:

* a ContextEvent the Observer marked sensitive, blocked or deny-listed never
  enters a Context Manifest, so it never reaches a model;
* a MemoryWriteSuggestion is only promoted into EMOS when the user confirmed it
  and the suggestion carries no privacy flag; everything else stays in the
  Observer outbox and is reported as held or blocked rather than silently
  dropped.

Both rules are pure functions here so they can be tested without the desktop.
"""
from __future__ import annotations

# Actions the Observer may attach to a capture. `allow` is the only one that
# produces context the PA is allowed to see.
BLOCKED_ACTIONS = {"block", "blocked", "deny", "denied", "reject", "rejected"}

# Categories whose content is a private conversation or an identity credential.
# The Observer already handles these; repeating the check here is defence in
# depth, because a mis-configured Observer must not become a PA leak.
NEVER_IN_CONTEXT_CATEGORIES = {"credential", "identity", "payment", "medical"}

DEFAULT_EVENT_LIMIT = 5
MAX_TEXT_CHARS = 320


def _text(value, limit: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def event_is_sensitive(event) -> bool:
    """True when the Observer flagged this event as private in any way."""
    if not isinstance(event, dict):
        return True
    privacy = event.get("privacy")
    if not isinstance(privacy, dict):
        privacy = {}
    if privacy.get("is_sensitive"):
        return True
    if str(privacy.get("action") or "").lower() in BLOCKED_ACTIONS:
        return True
    if privacy.get("sensitivity_types"):
        return True
    app = event.get("app") if isinstance(event.get("app"), dict) else {}
    if str(app.get("category") or "").lower() in NEVER_IN_CONTEXT_CATEGORIES:
        return True
    return False


def project_event(event) -> dict:
    """Shrink a raw ContextEvent to the fields a manifest may carry.

    The projection keeps enough for the PA to answer "why do you know what I am
    working on?" - which app, which window, when, and what was read - and nothing
    else: no screenshot path, no OCR box coordinates, no raw OCR dump.
    """
    event = event if isinstance(event, dict) else {}
    app = event.get("app") if isinstance(event.get("app"), dict) else {}
    content = event.get("content") if isinstance(event.get("content"), dict) else {}
    trigger = event.get("trigger") if isinstance(event.get("trigger"), dict) else {}
    app_name = _text(app.get("name"), 80) or "unknown"
    window_title = _text(app.get("window_title"), 120)
    summary = _text(content.get("summary") or content.get("clean_text"), MAX_TEXT_CHARS)
    captured_at = _text(event.get("created_at"), 40)
    return {
        "event_id": _text(event.get("event_id"), 64),
        "captured_at": captured_at,
        "app": app_name,
        "category": _text(app.get("category"), 40),
        "window_title": window_title,
        "trigger": _text(trigger.get("type"), 40),
        "retention": _text(event.get("status"), 40),
        "summary": summary,
        # This is the sentence the PA can quote when the user asks how it knew.
        "why": f"observer saw {app_name}" + (f" - {window_title}" if window_title else "")
               + (f" at {captured_at}" if captured_at else "")
               + " (temporary desktop context, not long-term memory)",
    }


def gate_events(events, limit: int = DEFAULT_EVENT_LIMIT) -> tuple[list, list]:
    """Split Observer events into (kept, dropped) for one Context Manifest.

    Dropped entries carry the reason so a later "why is this missing" question is
    answerable instead of mysterious.
    """
    kept: list = []
    dropped: list = []
    for event in events or []:
        event_id = _text((event or {}).get("event_id") if isinstance(event, dict) else "", 64)
        if event_is_sensitive(event):
            dropped.append({"event_id": event_id, "reason": "sensitive"})
            continue
        if not event_id:
            dropped.append({"event_id": "", "reason": "malformed"})
            continue
        kept.append(project_event(event))
    # Truncation is a drop too. Before this, a manifest could report
    # considered=20 / included=5 / dropped=1 with 14 events in no bucket at all -
    # the audit trail has to add up, so the ones cut by the limit say so.
    if len(kept) > limit:
        for item in kept[limit:]:
            dropped.append({"event_id": item.get("event_id", ""), "reason": "over_limit"})
        kept = kept[:limit]
    return kept, dropped


def build_observer_context(events, limit: int = DEFAULT_EVENT_LIMIT) -> dict:
    """The `observer` block of a Context Manifest, with its audit trail."""
    considered = list(events or [])
    kept, dropped = gate_events(considered, limit=limit)
    reasons: dict = {}
    for item in dropped:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {
        "gate": {
            "considered": len(considered),
            "included": len(kept),
            "dropped": len(dropped),
            "dropped_reasons": reasons,
            "policy": "sensitive desktop context never enters a manifest",
        },
        "events": kept,
    }


def suggestion_action(payload, confirmed: bool) -> tuple[str, str]:
    """Decide what to do with one Observer memory-write suggestion.

    Returns (action, reason) where action is one of:

    * ``write``   - safe and user-confirmed, promote into long-term memory;
    * ``hold``    - safe, but the Observer asked for confirmation and none was
                    given, so it stays in the outbox;
    * ``blocked`` - privacy flagged; never written, record the block and drop it.
    """
    payload = payload if isinstance(payload, dict) else {}
    # Fail closed: a payload that says nothing about privacy or confirmation is
    # not a payload this gate understands, so it must not become memory.
    if not {"suggestion_type", "privacy_flags", "memory_cycle",
            "requires_user_confirmation"} & set(payload.keys()):
        return "blocked", "unrecognised suggestion payload"
    suggestion_type = str(payload.get("suggestion_type") or "").lower()
    if suggestion_type == "ignore":
        return "blocked", "observer marked this capture as ignore"
    if payload.get("privacy_flags"):
        return "blocked", "privacy_flags: " + ",".join(str(f) for f in payload["privacy_flags"])
    if payload.get("memory_cycle") == "temporary":
        return "blocked", "capture is temporary context only"
    if payload.get("requires_user_confirmation") and not confirmed:
        return "hold", "waiting for the user to confirm this memory"
    return "write", "confirmed, no privacy flag"
