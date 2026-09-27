# -*- coding: utf-8 -*-
"""Runtime configuration.

load_env() runs once from app/__init__.py, i.e. before any submodule reads its
environment at import time (db path, planner choice, connector URLs).
Secrets live in .env, which is gitignored (execution book WP-00).
"""
from __future__ import annotations
import os

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional
        return
    gateway_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(gateway_dir, ".env"), override=False)
