from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


HARD_SENSITIVE = {
    "credential", "credentials", "password", "token", "secret", "api_key",
    "payment", "bank_card", "medical", "legal", "private_chat",
}

PATTERNS = [
    ("email", re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    ("token", re.compile(r"(?i)\b(?:api[_ -]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"), "[REDACTED_SECRET]"),
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)"), "[REDACTED_CARD]"),
]

CREDENTIAL_PATTERNS = [
    (
        "provider_token",
        re.compile(r"(?i)(?<![A-Za-z0-9])sk[-_][A-Za-z0-9_-]{16,}(?![A-Za-z0-9_-])"),
    ),
    (
        "bearer_token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    ),
    (
        "github_token",
        re.compile(r"(?i)(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})(?![A-Za-z0-9_])"),
    ),
    (
        "slack_token",
        re.compile(r"(?i)(?<![A-Za-z0-9])xox[baprs]-[A-Za-z0-9-]{16,}(?![A-Za-z0-9-])"),
    ),
    (
        "aws_access_key",
        re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
    ),
    (
        "google_api_key",
        re.compile(r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"),
    ),
]

_XIAO_OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class PrivacyDecision:
    local_allowed: bool
    cloud_allowed: bool
    reason: str
    redactions: list[str]


def decide(event: dict[str, Any]) -> PrivacyDecision:
    privacy = event.get("privacy") or {}
    flags = {str(value).casefold() for value in privacy.get("sensitivity_types") or []}
    action = str(privacy.get("action") or "allow").casefold()
    hard = sorted(flags & HARD_SENSITIVE)
    if action == "block":
        return PrivacyDecision(False, False, "privacy_action_block", hard)
    if privacy.get("is_sensitive") is True or hard:
        return PrivacyDecision(False, False, "sensitive_event", hard or ["is_sensitive"])
    credential_hits = credential_types(
        " ".join(
            [
                str((event.get("app") or {}).get("window_title") or ""),
                str(event.get("content") or ""),
                str(event.get("suggestions") or ""),
            ]
        )
    )
    if credential_hits:
        return PrivacyDecision(False, False, "credential_pattern", credential_hits)
    cloud_allowed = privacy.get("allowed_to_upload") is True
    return PrivacyDecision(True, cloud_allowed, "local_only" if not cloud_allowed else "allowed", [])


def redact_text(value: str) -> tuple[str, list[str]]:
    output = value
    redactions: list[str] = []
    for name, pattern, replacement in PATTERNS:
        output, count = pattern.subn(replacement, output)
        if count:
            redactions.extend([name] * count)
    for name, pattern in CREDENTIAL_PATTERNS:
        output, count = pattern.subn("[REDACTED_SECRET]", output)
        if count:
            redactions.extend([name] * count)
    return output, redactions


def credential_types(value: str) -> list[str]:
    text = str(value or "")
    return sorted(
        {
            name
            for name, pattern in CREDENTIAL_PATTERNS
            if pattern.search(text)
        }
        | {
            name
            for name, pattern, _ in PATTERNS
            if name in {"token", "card"} and pattern.search(text)
        }
    )


def safe_event_view(event: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    content = event.get("content") or {}
    app = event.get("app") or {}
    redactions: list[str] = []

    def clean(value: Any) -> str:
        text, found = redact_text(str(value or ""))
        redactions.extend(found)
        return text

    tasks = []
    for raw in (content.get("tasks") or (event.get("suggestions") or {}).get("task_card_suggestions") or []):
        if not isinstance(raw, dict):
            continue
        task = dict(raw)
        for field in ("task", "title", "description", "assignee", "project"):
            if field in task:
                task[field] = clean(task[field])
        tasks.append(task)
    entities = []
    for raw in content.get("entities") or []:
        if isinstance(raw, dict):
            item = dict(raw)
            item["text"] = clean(item.get("text"))
            entities.append(item)
    view = {
        "event_id": event["event_id"],
        "created_at": event["created_at"],
        "source": event.get("source"),
        "app": {
            "name": clean(app.get("name")),
            "category": clean(app.get("category")),
            "window_title": clean(app.get("window_title")),
        },
        "content": {
            "content_type": clean(content.get("content_type")),
            "summary": clean(content.get("summary")),
            "clean_text": clean(content.get("clean_text") or content.get("raw_text")),
            "entities": entities,
            "tasks": tasks,
        },
        "privacy": {
            "requires_user_confirmation": bool((event.get("privacy") or {}).get("requires_user_confirmation")),
            "allowed_to_write_long_term_memory": bool((event.get("privacy") or {}).get("allowed_to_write_long_term_memory")),
        },
    }
    artifacts = _safe_xiao_artifacts(event)
    if artifacts:
        privacy = event.get("privacy") or {}
        view["artifacts"] = artifacts
        view["privacy"]["allowed_to_upload"] = bool(
            privacy.get("allowed_to_upload")
        )
        view["privacy"]["review_status"] = clean(
            privacy.get("review_status")
        )
    return view, sorted(set(redactions))


def _safe_xiao_artifacts(event: dict[str, Any]) -> dict[str, Any]:
    if str(event.get("source") or "") != "xiao_pendant":
        return {}
    content_type = str((event.get("content") or {}).get("content_type") or "")
    if content_type != "xiao_capture_visual":
        return {}
    raw = event.get("artifacts") or {}
    session_id = str(raw.get("xiao_session_id") or "")
    frame_id = str(raw.get("representative_frame_id") or "")
    if not (_XIAO_OPAQUE_ID.fullmatch(session_id) and _XIAO_OPAQUE_ID.fullmatch(frame_id)):
        return {}
    try:
        frame_count = min(max(int(raw.get("frame_count") or 0), 0), 100_000)
    except (TypeError, ValueError, OverflowError):
        frame_count = 0
    return {
        "xiao_session_id": session_id,
        "representative_frame_id": frame_id,
        "frame_count": frame_count,
    }

