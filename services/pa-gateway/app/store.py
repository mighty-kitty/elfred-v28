# -*- coding: utf-8 -*-
"""In-memory store for v0. A real DB migration is second-batch (per execution book DoD)."""
from __future__ import annotations
import time
from typing import Optional
from .models import PAProfile, Run


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class InMemoryStore:
    def __init__(self) -> None:
        self._profiles: dict[str, PAProfile] = {}
        self._runs: dict[str, Run] = {}

    def create_profile(self, user_id: str, **kw) -> PAProfile:
        pa_id = f"pa_{len(self._profiles) + 1:03d}"
        p = PAProfile(pa_id=pa_id, user_id=user_id, created_at=_now(), updated_at=_now(), **kw)
        self._profiles[pa_id] = p
        return p

    def get_profile(self, pa_id: str) -> Optional[PAProfile]:
        return self._profiles.get(pa_id)

    def create_run(self, pa_id: str, query: str) -> Run:
        run_id = f"run_{len(self._runs) + 1:03d}"
        r = Run(run_id=run_id, pa_id=pa_id, query_summary=query, created_at=_now(), updated_at=_now())
        self._runs[run_id] = r
        return r

    def get_run(self, run_id: str) -> Optional[Run]:
        return self._runs.get(run_id)

    def save_run(self, run: Run) -> Run:
        run.updated_at = _now()
        self._runs[run.run_id] = run
        return run

    def delete_run(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
