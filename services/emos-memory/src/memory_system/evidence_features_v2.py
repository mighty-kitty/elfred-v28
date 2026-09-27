from __future__ import annotations

import re


SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?!。！？])\s+")
CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:,|，|;|；| - | — | and | but | because | so | which | that )\s*",
    re.IGNORECASE,
)
LEADING_SPEAKER_RE = re.compile(r"^\[[^]]+\]\s*[A-Za-z]+:\s*")
TRAILING_META_RE = re.compile(r"\s+(?:image:|query:).*$", re.IGNORECASE)
REASON_MARKERS = (
    "because",
    "since",
    "so that",
    "so i can",
    "so we can",
    "it's been a dream",
    "it made me",
    "it reminds me",
    "it stands for",
    "important",
    "support",
    "help",
    "love",
    "dream",
)


def extract_core_content(text: str) -> str:
    value = text.strip()
    value = LEADING_SPEAKER_RE.sub("", value)
    value = TRAILING_META_RE.sub("", value)
    return value.strip()


def extract_reason_spans(text: str) -> list[str]:
    lowered = text.lower()
    spans: list[str] = []
    for marker in REASON_MARKERS:
        index = lowered.find(marker)
        if index == -1:
            continue
        span = text[index:].strip(" ,.;")
        if len(span) >= 18:
            spans.append(span)
    return list(dict.fromkeys(spans))


def extract_evidence_spans_v2(text: str, max_spans: int = 4) -> list[str]:
    stripped = extract_core_content(text)
    if not stripped:
        return []

    candidates: list[str] = []
    if " | " in stripped:
        candidates.extend(part.strip() for part in stripped.split(" | ") if part.strip())

    if not candidates:
        candidates.extend(part.strip() for part in SENTENCE_SPLIT_RE.split(stripped) if part.strip())

    clause_candidates: list[str] = []
    for candidate in candidates:
        clause_candidates.extend(extract_reason_spans(candidate))
        parts = [part.strip() for part in CLAUSE_SPLIT_RE.split(candidate) if part.strip()]
        if len(parts) >= 2:
            clause_candidates.extend(parts)
    candidates.extend(clause_candidates)

    refined: list[str] = []
    for candidate in candidates:
        if len(candidate) < 18:
            continue
        if candidate.endswith("?") or candidate.endswith("？"):
            continue
        refined.append(candidate)

    deduped = list(dict.fromkeys(refined))
    if not deduped and len(stripped) >= 18:
        deduped = [stripped]
    return deduped[:max_spans]
