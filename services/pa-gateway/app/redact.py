# -*- coding: utf-8 -*-
"""Minimalization / redaction for context before it reaches the model."""
from __future__ import annotations
import re

SENSITIVE_KEYS = {"api_key", "token", "secret", "password", "authorization", "cookie"}
URL_RE = re.compile(r"https?://[^\s]+")


def redact(obj, depth: int = 0) -> object:
    if depth > 3:
        return "<max-depth>"
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k.lower() in SENSITIVE_KEYS else redact(v, depth + 1))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, depth + 1) for v in obj]
    if isinstance(obj, str):
        if len(obj) > 800:
            obj = obj[:800] + "...<truncated>"
        if URL_RE.search(obj):
            obj = URL_RE.sub("<url-redacted>", obj)
        return obj
    return obj
