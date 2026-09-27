from __future__ import annotations

import re


SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?!。！？])\s+")


def extract_evidence_spans(text: str, max_spans: int = 3) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    candidates: list[str] = []
    if " | " in stripped:
        candidates.extend(part.strip() for part in stripped.split(" | ") if part.strip())

    if not candidates:
        candidates.extend(part.strip() for part in SENTENCE_SPLIT_RE.split(stripped) if part.strip())

    refined: list[str] = []
    for candidate in candidates:
        if len(candidate) < 28:
            continue
        refined.append(candidate)

    deduped = list(dict.fromkeys(refined))
    if not deduped and len(stripped) >= 28:
        deduped = [stripped]
    return deduped[:max_spans]
