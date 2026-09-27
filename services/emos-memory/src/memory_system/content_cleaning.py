from __future__ import annotations

import re


LEADING_SPEAKER_RE = re.compile(r"^\[[^]]+\]\s*[A-Za-z]+:\s*")
TRAILING_META_RE = re.compile(r"\s+(?:image:|query:).*$", re.IGNORECASE)


def extract_core_content(text: str) -> str:
    value = text.strip()
    value = LEADING_SPEAKER_RE.sub("", value)
    value = TRAILING_META_RE.sub("", value)
    return value.strip()
