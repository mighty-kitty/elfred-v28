# -*- coding: utf-8 -*-
"""Context Manifest (execution book 7.3): minimal, auditable, redacted context bundle."""
from __future__ import annotations
import time


def build_manifest(run_id: str, query_summary: str, profile, ctx: dict, redaction_log: list,
                   token_budget: int = 12000) -> dict:
    return {
        "run_id": run_id,
        "query_summary": query_summary,
        "profile_version": getattr(profile, "profile_version", 1),
        "consent_version": getattr(profile, "consent_version", 0),
        "memory_refs": ctx.get("memory_refs", []),
        # WP-04: which retrieval produced the recall, the affective tag if EMOS
        # attached one, the always-on blocks, and how they reach the agent.
        "memory_retrieval": ctx.get("memory_retrieval", {}),
        "memory_emotion": ctx.get("memory_emotion", {}),
        "core_memory_blocks": ctx.get("core_memory_blocks", []),
        "letta_mirror": ctx.get("letta_mirror", {}),
        "knowledge_refs": ctx.get("knowledge_refs", []),
        # Chunk-level citations: which passage, not just which file.
        "knowledge_citations": ctx.get("knowledge_citations", []),
        "observer_event_refs": ctx.get("observer_event_refs", []),
        # The projected desktop context itself, so "how did you know?" is
        # answerable from the manifest alone. Sensitive events never get here.
        "observer_events": ctx.get("observer_events", []),
        "observer_gate": ctx.get("observer_gate", {}),
        "organizer_refs": ctx.get("organizer_refs", []),
        "task_refs": ctx.get("task_refs", []),
        "skill_refs": ctx.get("skill_refs", []),
        "redaction_log": redaction_log,
        "token_budget": token_budget,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
