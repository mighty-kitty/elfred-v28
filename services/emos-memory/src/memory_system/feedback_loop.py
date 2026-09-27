from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MemoryEntry, RetrievalCandidate, utc_now
from .utils.io import read_json, write_json


SCHEMA_VERSION = 2
FEEDBACK_HALF_LIFE_DAYS = 30.0
MAX_FEEDBACK_BONUS = 0.6
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
QUESTION_RE = re.compile(r"[?？]|^(what|when|where|who|why|how|did|does|do|is|are|was|were)\b", re.IGNORECASE)
CORRECTION_MARKERS = (
    "不是这个",
    "不是那个",
    "不对",
    "不太对",
    "记错",
    "搞错",
    "不是我说的",
    "not that",
    "that's wrong",
    "you got it wrong",
    "wrong memory",
)
AFFIRMATION_MARKERS = (
    "对，就是",
    "没错",
    "就是这个",
    "是的",
    "对的",
    "exactly",
    "that's right",
    "correct",
)
DEFAULT_FEEDBACK_STATE: dict[str, Any] = {
    "version": SCHEMA_VERSION,
    "events": [],
    "user_profiles": {},
}

FEEDBACK_DELTAS = {
    "correct": 1.0,
    "incorrect": -1.0,
    "irrelevant": -0.6,
}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bucket(score: float = 0.0, support: float = 0.0) -> dict[str, float]:
    return {"score": float(score), "support": float(support)}


def _normalize_bucket_map(value: Any) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, float]] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            normalized[str(key)] = _bucket(item.get("score", 0.0), item.get("support", 0.0))
        else:
            normalized[str(key)] = _bucket(item, 1.0 if item else 0.0)
    return normalized


def _normalize_feedback_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    events = payload.get("events", [])
    profiles = payload.get("user_profiles", {})
    normalized_profiles: dict[str, Any] = {}
    if isinstance(profiles, dict):
        for user_id, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            normalized_profiles[str(user_id)] = {
                "memory_scores": _normalize_bucket_map(profile.get("memory_scores", {})),
                "tag_scores": _normalize_bucket_map(profile.get("tag_scores", {})),
                "attribute_scores": _normalize_bucket_map(profile.get("attribute_scores", {})),
                "backend_scores": _normalize_bucket_map(profile.get("backend_scores", {})),
                "query_scores": _normalize_bucket_map(profile.get("query_scores", {})),
                "last_feedback_at": profile.get("last_feedback_at"),
                "total_events": int(profile.get("total_events", 0)),
            }
    return {
        "version": SCHEMA_VERSION,
        "events": [item for item in events if isinstance(item, dict)],
        "user_profiles": normalized_profiles,
    }


def _query_signature(query_text: str | None) -> str | None:
    if not query_text:
        return None
    normalized = " ".join(query_text.strip().lower().split())
    if not normalized:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _stable_event_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _token_set(text: str | None) -> set[str]:
    if not text:
        return set()
    return {item.lower() for item in TOKEN_RE.findall(text)}


def _infer_language_hint(text: str | None) -> str:
    if not text:
        return "unknown"
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in text)
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "zh"
    if has_latin:
        return "en"
    return "unknown"


def _looks_like_question(text: str | None) -> bool:
    if not text:
        return False
    return bool(QUESTION_RE.search(text.strip()))


def _overlap_ratio(left: str | None, right: str | None) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union if union else 0.0


def _apply_decay(profile: dict[str, Any], *, as_of: datetime) -> None:
    previous = _parse_timestamp(profile.get("last_feedback_at"))
    if previous is None:
        return
    elapsed_days = max(0.0, (as_of - previous).total_seconds() / 86400.0)
    if elapsed_days <= 0:
        return
    decay_factor = math.exp(-math.log(2) * elapsed_days / FEEDBACK_HALF_LIFE_DAYS)
    for key in ("memory_scores", "tag_scores", "attribute_scores", "backend_scores", "query_scores"):
        bucket_map = profile.get(key, {})
        if not isinstance(bucket_map, dict):
            continue
        for item in bucket_map.values():
            if isinstance(item, dict):
                item["score"] = round(float(item.get("score", 0.0)) * decay_factor, 6)
                item["support"] = round(float(item.get("support", 0.0)) * decay_factor, 6)


def _update_bucket(bucket_map: dict[str, dict[str, float]], key: str, delta: float, weight: float) -> None:
    bucket = bucket_map.setdefault(key, _bucket())
    bucket["score"] = round(float(bucket.get("score", 0.0)) + delta * weight, 6)
    bucket["support"] = round(float(bucket.get("support", 0.0)) + abs(weight), 6)


def _bucket_bonus(bucket_map: dict[str, dict[str, float]], key: str | None, scale: float) -> float:
    if not key:
        return 0.0
    bucket = bucket_map.get(key)
    if not isinstance(bucket, dict):
        return 0.0
    support = max(0.0, float(bucket.get("support", 0.0)))
    confidence = support / (support + 2.0)
    return float(bucket.get("score", 0.0)) * confidence * scale


def _top_bucket_items(bucket_map: dict[str, dict[str, float]], *, limit: int = 5) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for key, bucket in bucket_map.items():
        if not isinstance(bucket, dict):
            continue
        items.append(
            {
                "key": key,
                "score": round(float(bucket.get("score", 0.0)), 4),
                "support": round(float(bucket.get("support", 0.0)), 4),
            }
        )
    items.sort(key=lambda item: (item["score"], item["support"]), reverse=True)
    return items[:limit]


def load_feedback_state(path: Path) -> dict[str, Any]:
    payload = read_json(path, default=DEFAULT_FEEDBACK_STATE)
    return _normalize_feedback_state(payload)


def save_feedback_state(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, _normalize_feedback_state(payload))


def record_feedback_event(
    state: dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    memory_id: str,
    feedback_type: str,
    entry: MemoryEntry | None,
    candidate: RetrievalCandidate | None,
    query_text: str | None = None,
    notes: str | None = None,
    signal_weight: float = 1.0,
    interaction_id: str | None = None,
    shown_rank: int | None = None,
    feedback_origin: str = "explicit",
    passive_reason: str | None = None,
) -> dict[str, Any]:
    normalized_feedback = feedback_type.strip().lower()
    if normalized_feedback not in FEEDBACK_DELTAS:
        raise ValueError(f"Unsupported feedback_type: {feedback_type}")

    normalized_state = _normalize_feedback_state(state)
    state.clear()
    state.update(normalized_state)

    effective_weight = max(0.25, min(2.0, float(signal_weight)))
    delta = FEEDBACK_DELTAS[normalized_feedback] * effective_weight
    created_at = utc_now()
    created_at_dt = _parse_timestamp(created_at) or datetime.now(timezone.utc)
    query_sig = _query_signature(query_text)

    events = state.setdefault("events", [])
    profiles = state.setdefault("user_profiles", {})
    user_profile = profiles.setdefault(
        user_id,
        {
            "memory_scores": {},
            "tag_scores": {},
            "attribute_scores": {},
            "backend_scores": {},
            "query_scores": {},
            "last_feedback_at": None,
            "total_events": 0,
        },
    )
    _apply_decay(user_profile, as_of=created_at_dt)

    metadata = entry.metadata if entry is not None and isinstance(entry.metadata, dict) else {}
    attributes = sorted(
        {
            *[str(item) for item in metadata.get("attributes", []) if item],
            *([str(item) for item in candidate.attribute_hits] if candidate is not None else []),
        }
    )
    tags = sorted({str(item) for item in (entry.tags if entry is not None else []) if item})
    event = {
        "event_id": _stable_event_id(
            "fb",
            created_at,
            user_id,
            session_id,
            memory_id,
            normalized_feedback,
            query_sig or "",
        ),
        "created_at": created_at,
        "user_id": user_id,
        "session_id": session_id,
        "memory_id": memory_id,
        "feedback_type": normalized_feedback,
        "delta": round(delta, 6),
        "signal_weight": effective_weight,
        "query_text": query_text,
        "query_signature": query_sig,
        "notes": notes,
        "interaction_id": interaction_id,
        "shown_rank": shown_rank,
        "feedback_origin": feedback_origin,
        "passive_reason": passive_reason,
        "backend": candidate.backend if candidate is not None else None,
        "candidate_score": candidate.score if candidate is not None else None,
        "tags": tags,
        "attributes": attributes,
    }
    events.append(event)

    _update_bucket(user_profile.setdefault("memory_scores", {}), memory_id, delta, 1.0)
    for tag in tags:
        _update_bucket(user_profile.setdefault("tag_scores", {}), tag, delta, 0.35)
    for attribute in attributes:
        _update_bucket(user_profile.setdefault("attribute_scores", {}), attribute, delta, 0.45)
    backend_name = event["backend"]
    if backend_name:
        _update_bucket(user_profile.setdefault("backend_scores", {}), str(backend_name), delta, 0.15)
    if query_sig:
        _update_bucket(user_profile.setdefault("query_scores", {}), query_sig, delta, 0.20)

    user_profile["last_feedback_at"] = created_at
    user_profile["total_events"] = int(user_profile.get("total_events", 0)) + 1
    return event


def compute_feedback_bonus(
    state: dict[str, Any],
    *,
    user_id: str,
    entry: MemoryEntry,
    candidate: RetrievalCandidate,
    query_text: str | None = None,
) -> float:
    profiles = _normalize_feedback_state(state).get("user_profiles", {})
    user_profile = profiles.get(user_id)
    if not isinstance(user_profile, dict):
        return 0.0

    memory_bonus = _bucket_bonus(user_profile.get("memory_scores", {}), entry.memory_id, 0.18)
    tag_bonus = sum(_bucket_bonus(user_profile.get("tag_scores", {}), tag, 0.05) for tag in entry.tags)
    attribute_bonus = sum(
        _bucket_bonus(user_profile.get("attribute_scores", {}), attribute, 0.06)
        for attribute in candidate.attribute_hits
    )
    backend_bonus = _bucket_bonus(user_profile.get("backend_scores", {}), candidate.backend, 0.03)
    query_bonus = _bucket_bonus(user_profile.get("query_scores", {}), _query_signature(query_text), 0.04)
    total = memory_bonus + tag_bonus + attribute_bonus + backend_bonus + query_bonus
    return max(-MAX_FEEDBACK_BONUS, min(MAX_FEEDBACK_BONUS, total))


def build_feedback_report(state: dict[str, Any], user_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    normalized_state = _normalize_feedback_state(state)
    events = normalized_state.get("events", [])
    if user_id:
        scoped_events = [event for event in events if event.get("user_id") == user_id]
        profile = normalized_state.get("user_profiles", {}).get(user_id, {})
    else:
        scoped_events = list(events)
        profile = None

    recent_events = list(reversed(scoped_events[-limit:]))
    summary = {
        "total_events": len(scoped_events),
        "correct": sum(1 for event in scoped_events if event.get("feedback_type") == "correct"),
        "incorrect": sum(1 for event in scoped_events if event.get("feedback_type") == "incorrect"),
        "irrelevant": sum(1 for event in scoped_events if event.get("feedback_type") == "irrelevant"),
        "explicit": sum(1 for event in scoped_events if event.get("feedback_origin") == "explicit"),
        "passive": sum(1 for event in scoped_events if event.get("feedback_origin") == "passive"),
    }
    profile_insights = None
    if isinstance(profile, dict):
        profile_insights = {
            "last_feedback_at": profile.get("last_feedback_at"),
            "total_events": profile.get("total_events", 0),
            "top_memories": _top_bucket_items(profile.get("memory_scores", {})),
            "top_tags": _top_bucket_items(profile.get("tag_scores", {})),
            "top_attributes": _top_bucket_items(profile.get("attribute_scores", {})),
            "top_backends": _top_bucket_items(profile.get("backend_scores", {})),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "summary": summary,
        "profile": profile,
        "profile_insights": profile_insights,
        "recent_events": recent_events,
    }


def append_interaction_log(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    created_at = str(payload.get("created_at") or utc_now())
    query_text = str(payload.get("query_text") or "")
    interaction_id = str(
        payload.get("interaction_id")
        or _stable_event_id("int", created_at, payload.get("user_id"), payload.get("session_id"), query_text)
    )
    normalized_candidates: list[dict[str, Any]] = []
    for rank, item in enumerate(payload.get("retrieval_candidates", [])[:10], start=1):
        candidate = dict(item)
        candidate["rank"] = rank
        normalized_candidates.append(candidate)

    enriched = dict(payload)
    enriched.update(
        {
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "interaction_id": interaction_id,
            "query_signature": _query_signature(query_text),
            "language_hint": _infer_language_hint(query_text),
            "retrieval_candidates": normalized_candidates,
            "top_candidate_id": normalized_candidates[0]["memory_id"] if normalized_candidates else None,
            "shown_candidate_ids": [candidate["memory_id"] for candidate in normalized_candidates],
            "shown_set_size": len(normalized_candidates),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = _last_interaction_log_hash(path)
    record_hash = _interaction_log_record_hash(enriched, previous_hash)
    enriched["audit_log_chain"] = {
        "surface_version": "audit-log-hash-chain.v1",
        "hash_algorithm": "sha256",
        "previous_record_hash": previous_hash,
        "record_hash": record_hash,
        "chain_scope": "local_interaction_log_file",
        "tamper_evidence_scope": "local_hash_chain_not_external_attestation",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(enriched, ensure_ascii=False))
        handle.write("\n")
    return enriched


def _last_interaction_log_hash(path: Path) -> str:
    if not path.exists():
        return "GENESIS"
    last_line = ""
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                last_line = line
    if not last_line:
        return "GENESIS"
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError:
        return hashlib.sha256(last_line.encode("utf-8")).hexdigest()
    chain = payload.get("audit_log_chain")
    if isinstance(chain, dict) and chain.get("record_hash"):
        return str(chain["record_hash"])
    return hashlib.sha256(last_line.encode("utf-8")).hexdigest()


def _interaction_log_record_hash(payload: dict[str, Any], previous_hash: str) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{previous_hash}\n{canonical}".encode("utf-8")).hexdigest()


def export_offline_review_dataset(
    log_path: Path,
    output_path: Path,
    *,
    limit: int = 500,
    user_id: str | None = None,
    feedback_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if log_path.exists():
        with log_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if user_id and payload.get("user_id") != user_id:
                    continue
                records.append(payload)

    selected = records[-limit:]
    normalized_feedback = _normalize_feedback_state(feedback_state or DEFAULT_FEEDBACK_STATE)
    feedback_events = normalized_feedback.get("events", [])
    feedback_index: dict[tuple[str, str | None, str | None], list[dict[str, Any]]] = {}
    for event in feedback_events:
        key = (
            str(event.get("user_id")),
            event.get("session_id"),
            event.get("query_signature"),
        )
        feedback_index.setdefault(key, []).append(event)

    samples: list[dict[str, Any]] = []
    feedback_labeled_count = 0
    protocol_labeled_count = 0
    backends: set[str] = set()
    language_counts: dict[str, int] = {}
    judgment_counts: dict[str, int] = {}
    training_signal_status_counts: dict[str, int] = {}
    record_type_counts: dict[str, int] = {}
    operation_counts: dict[str, int] = {}
    decision_protocol_versions: dict[str, int] = {}
    guardrailed_sample_count = 0
    response_contract_sample_count = 0
    ux_guided_sample_count = 0
    response_plan_sample_count = 0
    for item in selected:
        key = (
            str(item.get("user_id")),
            item.get("session_id"),
            item.get("query_signature"),
        )
        linked_feedback = feedback_index.get(key, [])
        positive_ids = sorted(
            {
                str(event.get("memory_id"))
                for event in linked_feedback
                if event.get("feedback_type") == "correct" and event.get("memory_id")
            }
        )
        negative_ids = sorted(
            {
                str(event.get("memory_id"))
                for event in linked_feedback
                if event.get("feedback_type") in {"incorrect", "irrelevant"} and event.get("memory_id")
            }
        )
        if positive_ids and negative_ids:
            judgment_status = "mixed"
        elif positive_ids:
            judgment_status = "positive"
        elif negative_ids:
            judgment_status = "negative"
        else:
            judgment_status = "unlabeled"
        backend_name = str(item.get("retrieval_backend") or "unknown")
        backends.add(backend_name)
        language_hint = str(item.get("language_hint") or "unknown")
        language_counts[language_hint] = language_counts.get(language_hint, 0) + 1
        judgment_counts[judgment_status] = judgment_counts.get(judgment_status, 0) + 1
        record_type = str(item.get("record_type") or "interaction")
        operation = str(item.get("operation") or "process_turn")
        record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
        service_payload = item.get("service_payload", {}) if isinstance(item.get("service_payload", {}), dict) else {}
        training_protocol = item.get("training_protocol", {}) if isinstance(item.get("training_protocol", {}), dict) else {}
        decision_protocol = service_payload.get("decision_protocol", {}) if isinstance(service_payload.get("decision_protocol", {}), dict) else {}
        protocol_version = str(
            training_protocol.get("decision_protocol_version")
            or decision_protocol.get("protocol_version")
            or "none"
        )
        decision_protocol_versions[protocol_version] = decision_protocol_versions.get(protocol_version, 0) + 1
        has_guardrails = bool(
            training_protocol.get("has_execution_guardrails")
            or isinstance(service_payload.get("execution_guardrails"), dict)
            or isinstance(service_payload.get("response_guardrails"), dict)
        )
        if has_guardrails:
            guardrailed_sample_count += 1
        has_response_contract = bool(
            training_protocol.get("has_response_contract")
            or isinstance(service_payload.get("response_contract"), dict)
        )
        if has_response_contract:
            response_contract_sample_count += 1
        has_ux_guidance = isinstance(service_payload.get("user_experience_guidance"), dict)
        if has_ux_guidance:
            ux_guided_sample_count += 1
        has_response_plan = bool(
            training_protocol.get("has_response_plan")
            or isinstance(service_payload.get("agent_response_plan"), dict)
        )
        if has_response_plan:
            response_plan_sample_count += 1
        has_protocol_signal = bool(
            protocol_version != "none"
            and (
                bool(decision_protocol)
                or has_guardrails
                or has_response_contract
                or has_response_plan
                or isinstance(service_payload.get("consistency_plan"), dict)
            )
        )
        if linked_feedback:
            label_status = "feedback_attached"
            training_signal_status = "feedback_labeled"
            feedback_labeled_count += 1
        elif has_protocol_signal:
            label_status = "protocol_labeled"
            training_signal_status = "protocol_labeled"
            protocol_labeled_count += 1
        else:
            label_status = "unlabeled"
            training_signal_status = "unlabeled"
        training_signal_status_counts[training_signal_status] = training_signal_status_counts.get(training_signal_status, 0) + 1
        samples.append(
            {
                "sample_id": item.get("interaction_id"),
                "created_at": item.get("created_at"),
                "user_id": item.get("user_id"),
                "session_id": item.get("session_id"),
                "record_type": record_type,
                "operation": operation,
                "query_text": item.get("query_text"),
                "query_signature": item.get("query_signature"),
                "language_hint": language_hint,
                "emotion": item.get("emotion"),
                "task_goal": service_payload.get("task_goal"),
                "context_summary": service_payload.get("context_summary"),
                "working_memory": service_payload.get("working_memory", []),
                "decision_protocol": decision_protocol,
                "consistency_plan": service_payload.get("consistency_plan"),
                "execution_guardrails": service_payload.get("execution_guardrails") or service_payload.get("response_guardrails"),
                "response_contract": service_payload.get("response_contract"),
                "user_experience_guidance": service_payload.get("user_experience_guidance"),
                "agent_response_plan": service_payload.get("agent_response_plan"),
                "training_protocol": training_protocol,
                "retrieval_backend": backend_name,
                "retrieval_pipeline": item.get("retrieval_pipeline", {}),
                "recalled_memory_id": item.get("recalled_memory_id"),
                "memory_committed": item.get("memory_committed"),
                "label_status": label_status,
                "judgment_status": judgment_status,
                "training_signal_status": training_signal_status,
                "shown_set_size": item.get("shown_set_size", len(item.get("retrieval_candidates", []))),
                "shown_candidate_ids": item.get("shown_candidate_ids", []),
                "exposure": {
                    "top_candidate_id": item.get("top_candidate_id"),
                    "shown_set_size": item.get("shown_set_size", len(item.get("retrieval_candidates", []))),
                },
                "preferred_memory_ids": positive_ids,
                "rejected_memory_ids": negative_ids,
                "pairwise_preferences": [
                    {
                        "preferred": preferred_id,
                        "rejected": rejected_id,
                    }
                    for preferred_id in positive_ids
                    for rejected_id in negative_ids
                ],
                "feedback_events": [
                    {
                        "event_id": event.get("event_id"),
                        "memory_id": event.get("memory_id"),
                        "feedback_type": event.get("feedback_type"),
                        "delta": event.get("delta"),
                    }
                    for event in linked_feedback
                ],
                "candidate_training_rows": [
                    {
                        "memory_id": candidate.get("memory_id"),
                        "rank": candidate.get("rank"),
                        "backend": candidate.get("backend"),
                        "score": candidate.get("score"),
                        "target_label": (
                            1
                            if candidate.get("memory_id") in positive_ids
                            else -1
                            if candidate.get("memory_id") in negative_ids
                            else 0
                        ),
                        "label": (
                            "preferred"
                            if candidate.get("memory_id") in positive_ids
                            else "rejected"
                            if candidate.get("memory_id") in negative_ids
                            else "unlabeled"
                        ),
                        "exposed": True,
                        "features": {
                            "lexical_score": candidate.get("lexical_score", 0.0),
                            "semantic_score": candidate.get("semantic_score", 0.0),
                            "fuzzy_score": candidate.get("fuzzy_score", 0.0),
                            "embedding_score": candidate.get("embedding_score", 0.0),
                            "emotion_bonus": candidate.get("emotion_bonus", 0.0),
                            "recency_bonus": candidate.get("recency_bonus", 0.0),
                            "profile_bonus": candidate.get("profile_bonus", 0.0),
                            "abstraction_bonus": candidate.get("abstraction_bonus", 0.0),
                            "attribute_bonus": candidate.get("attribute_bonus", 0.0),
                            "summary_bonus": candidate.get("summary_bonus", 0.0),
                            "graph_bonus": candidate.get("graph_bonus", 0.0),
                            "rerank_bonus": candidate.get("rerank_bonus", 0.0),
                            "feedback_bonus": candidate.get("feedback_bonus", 0.0),
                            "keyword_count": len(candidate.get("keyword_hits", [])),
                            "concept_count": len(candidate.get("concept_hits", [])),
                            "relation_count": len(candidate.get("relation_hits", [])),
                            "attribute_count": len(candidate.get("attribute_hits", [])),
                        },
                    }
                    for candidate in item.get("retrieval_candidates", [])
                ],
                "candidates": item.get("retrieval_candidates", []),
            }
        )

    effective_labeled_count = feedback_labeled_count + protocol_labeled_count
    dataset = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "source_path": str(log_path),
        "user_id": user_id,
        "count": len(samples),
        "manifest": {
            "labeled_samples": effective_labeled_count,
            "feedback_labeled_samples": feedback_labeled_count,
            "protocol_labeled_samples": protocol_labeled_count,
            "unlabeled_samples": len(samples) - effective_labeled_count,
            "backends": sorted(backends),
            "languages": language_counts,
            "judgment_status": judgment_counts,
            "training_signal_status": training_signal_status_counts,
            "record_types": record_type_counts,
            "operations": operation_counts,
            "decision_protocol_versions": decision_protocol_versions,
            "guardrailed_samples": guardrailed_sample_count,
            "response_contract_samples": response_contract_sample_count,
            "ux_guided_samples": ux_guided_sample_count,
            "response_plan_samples": response_plan_sample_count,
        },
        "samples": samples,
    }

    write_json(output_path, dataset)
    return {
        "created_at": dataset["exported_at"],
        "path": str(output_path),
        "count": dataset["count"],
        "user_id": user_id,
        "manifest": dataset["manifest"],
    }


def infer_passive_feedback_signal(previous_interaction: dict[str, Any] | None, current_text: str) -> dict[str, Any] | None:
    if not previous_interaction:
        return None
    top_candidate_id = previous_interaction.get("top_candidate_id") or previous_interaction.get("recalled_memory_id")
    if not isinstance(top_candidate_id, str) or not top_candidate_id:
        return None

    normalized_text = current_text.strip().lower()
    if not normalized_text:
        return None

    previous_query = str(previous_interaction.get("query_text") or "")
    overlap = _overlap_ratio(previous_query, current_text)
    if any(marker in normalized_text for marker in CORRECTION_MARKERS):
        return {
            "memory_id": top_candidate_id,
            "feedback_type": "incorrect",
            "signal_weight": 1.2,
            "reason": "user_correction",
            "query_text": previous_query or current_text,
            "notes": "Passive correction inferred from the next user turn.",
        }

    if any(marker in normalized_text for marker in AFFIRMATION_MARKERS):
        return {
            "memory_id": top_candidate_id,
            "feedback_type": "correct",
            "signal_weight": 0.45,
            "reason": "user_affirmation",
            "query_text": previous_query or current_text,
            "notes": "Passive positive feedback inferred from the next user turn.",
        }

    if _looks_like_question(current_text) and overlap >= 0.45:
        return {
            "memory_id": top_candidate_id,
            "feedback_type": "irrelevant",
            "signal_weight": 0.7,
            "reason": "repeated_question",
            "query_text": previous_query or current_text,
            "notes": "Passive weak negative feedback inferred from repeated questioning.",
        }

    return None
