# -*- coding: utf-8 -*-
"""Run engine (execution-book state order):
created -> admitted -> contextualizing -> planning -> waiting_approval
-> (approve) executing -> verifying -> delivering -> completed.
Tools run AFTER approval; reject -> cancelled."""
from __future__ import annotations
import logging
import os
import re
import shlex
import subprocess
import threading
import time
import uuid
from typing import Optional
from .models import Feedback, Run, RunEvent, RunState, ToolEnvelope
from .db import DbStore
from .errors import ApiError
from .redact import redact
from .manifest import build_manifest
from .observer import build_observer_context, suggestion_action
from .policy import Policy
from .planners import DeterministicPlan


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


logger = logging.getLogger("elfred.pa-gateway.engine")


def approval_mode() -> str:
    """`async` executes an approved run on a worker thread (the product default);
    `sync` executes inline, which the test suite uses so its assertions stay simple."""
    return os.environ.get("PA_APPROVAL_MODE", "async").lower()


class RunEngine:
    def __init__(self, store: DbStore, emos=None, organizer=None, knowledge=None, freetodo=None,
                 skill=None, observer=None, planner: Optional[object] = None):
        self.store = store
        self.emos = emos
        self.organizer = organizer
        self.knowledge = knowledge
        self.freetodo = freetodo
        self.skill = skill
        self.observer = observer
        # Live delegation handles, keyed by run_id, so a cancel can kill the
        # harness instead of leaving an orphan behind.
        self.delegates: dict = {}
        self.planner = planner or DeterministicPlan()

    def _emit(self, run: Run, type_: str, payload: dict) -> None:
        run.seq += 1
        run.events.append(RunEvent(event_id=f"ev_{run.seq}", event_seq=run.seq, run_id=run.run_id,
                                   pa_id=run.pa_id, timestamp=_now(), type=type_, payload=payload))
        self.store.save_run(run)

    @staticmethod
    def _safe(fn, timeout=15.0):
        try:
            return fn(timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _policy_for(self, pa_id: str) -> Policy:
        profile = self.store.get_profile(pa_id)
        return Policy(profile.tool_scopes if profile else [], profile.boundaries if profile else {})

    @staticmethod
    def _memory_refs(payload) -> list:
        """EMOS returns recalled_memory / evidence / core_memory_blocks — the manifest
        must carry their ids so every claim stays auditable (execution book 7.3)."""
        if not isinstance(payload, dict):
            return []
        refs: list = []
        recalled = payload.get("recalled_memory")
        if isinstance(recalled, dict) and recalled.get("memory_id"):
            refs.append(recalled["memory_id"])
        for item in payload.get("evidence") or []:
            if isinstance(item, dict) and item.get("memory_id"):
                refs.append(item["memory_id"])
        for block in payload.get("core_memory_blocks") or []:
            if isinstance(block, dict) and block.get("label"):
                refs.append(f"block:{block['label']}")
        unique: list = []
        for ref in refs:
            if ref not in unique:
                unique.append(ref)
        return unique

    def _to(self, run: Run, state: RunState) -> None:
        """Advance the run state machine and record the transition as an event."""
        run.state = state
        self._emit(run, "run.status_changed", {"state": state.value})

    @staticmethod
    def _pipeline_view(pipeline) -> dict:
        """EMOS describes its retrieval pipeline in a deeply nested tree; keep the
        part that answers 'how did this recall happen' without the nesting that
        redaction would flatten into <max-depth>."""
        if not isinstance(pipeline, dict):
            return {}
        return {
            "backend_name": pipeline.get("backend_name"),
            "family": pipeline.get("family"),
            # joined, not nested: redaction flattens anything four levels deep
            "stages": ", ".join(pipeline.get("recall_stages") or []),
            "components": ", ".join(pipeline.get("recall_components") or []),
            "fusion": pipeline.get("fusion_strategy"),
            "rerank_stage": pipeline.get("rerank_stage"),
            "rerank_components": ", ".join(pipeline.get("rerank_components") or []),
        }

    @staticmethod
    def _candidate_count(candidates) -> int:
        """EMOS has reported candidates as both a list and a count."""
        if isinstance(candidates, list):
            return len(candidates)
        if isinstance(candidates, int) and not isinstance(candidates, bool):
            return candidates
        return 0

    @staticmethod
    def _block_view(payload) -> list:
        """The core memory blocks an agent must see, trimmed to what matters."""
        blocks = payload.get("core_memory_blocks") if isinstance(payload, dict) else None
        view = []
        for block in blocks or []:
            if not isinstance(block, dict) or not block.get("label"):
                continue
            view.append({"label": block["label"],
                         "value": str(block.get("value") or "")[:400],
                         "read_only": bool(block.get("read_only")),
                         "source": block.get("source") or ""})
        return view

    @staticmethod
    def _emotion_of(payload) -> dict:
        """EMOS tags affect on write; a recall may carry it on the recalled row."""
        if not isinstance(payload, dict):
            return {}
        emotion = payload.get("emotion")
        if isinstance(emotion, dict) and emotion.get("label"):
            return {"label": emotion["label"], "score": emotion.get("score")}
        recalled = payload.get("recalled_memory")
        if isinstance(recalled, dict):
            tagged = recalled.get("emotion") or (recalled.get("metadata") or {}).get("emotion")
            if isinstance(tagged, dict) and tagged.get("label"):
                return {"label": tagged["label"], "score": tagged.get("score")}
        return {}

    def _build_context(self, run: Run) -> tuple[dict, list]:
        ctx: dict = {}
        redaction_log: list = []
        if self.emos:
            mem = self._safe(lambda timeout: self.emos.recall(run.pa_id, run.query_summary))
            if isinstance(mem, dict) and "error" not in mem:
                payload = mem.get("payload", {})
                ctx["memory"] = payload
                ctx["memory_refs"] = self._memory_refs(payload)
                # WP-04: say which retrieval produced the recall (EMOS fuses
                # embedding + rerank server-side) and carry the blocks that the
                # agent must see on every request, since the App Server exposes no
                # way to edit an agent's own core memory.
                ctx["memory_retrieval"] = {
                    "backend": payload.get("retrieval_backend") or "unknown",
                    "candidate_count": self._candidate_count(
                        payload.get("retrieval_candidates")),
                    "pipeline": self._pipeline_view(payload.get("retrieval_pipeline")),
                    "fallback_reason": payload.get("fallback_reason"),
                }
                ctx["core_memory_blocks"] = self._block_view(payload)
                ctx["letta_mirror"] = {
                    "mode": "request_context",
                    "note": "Letta App Server exposes no block API; blocks are "
                            "injected into every planner request instead",
                }
                emotion = self._emotion_of(payload)
                if emotion:
                    ctx["memory_emotion"] = emotion
        if self.organizer:
            org = self._safe(lambda timeout: self.organizer.topics(limit=3))
            # The Organizer answers /v1/topics with a bare JSON array while other
            # services wrap theirs in an object. Assuming the wrapped shape meant
            # this whole branch was skipped and organizer_refs stayed empty in
            # every run (0 of the last 60) - measured against the live service, not
            # inferred from its health endpoint.
            if isinstance(org, list):
                topics = org
            elif isinstance(org, dict) and "error" not in org:
                topics = org.get("topics") or org.get("items") or []
            else:
                topics = []
            topics = [t for t in topics if isinstance(t, dict)]
            if topics:
                ctx["organizer"] = topics
                ctx["organizer_refs"] = [t.get("topic_id") or t.get("display_name")
                                         for t in topics if t.get("topic_id") or t.get("display_name")]
        if self.knowledge:
            kn = self._safe(lambda timeout: self._knowledge_hits(run))
            if isinstance(kn, dict) and "error" not in kn and kn.get("found"):
                ctx["knowledge"] = kn.get("hits", [])
                ctx["knowledge_refs"] = [h.get("document", {}).get("id") for h in kn.get("hits", [])]
                ctx["knowledge_citations"] = [h.get("chunk_id") for h in kn.get("hits", [])
                                              if h.get("chunk_id")]
                # The manifest says which passage was used; the citation row is
                # what makes that claim queryable after the run.
                for hit in kn.get("hits", []):
                    if hit.get("chunk_id"):
                        self.store.add_citation(run.run_id, run.pa_id,
                                                hit.get("document_id") or "",
                                                hit.get("chunk_id") or "",
                                                (hit.get("text") or "")[:200])
        if self.observer:
            # WP-05: desktop context the Observer allowed through its own privacy
            # gate, projected down to what a manifest may carry. Sensitive events
            # are dropped here and the drop is recorded, never silently ignored.
            ev = self._safe(lambda timeout: self.observer.recent_events(limit=20))
            if isinstance(ev, list):
                block = build_observer_context(ev)
                # Kept flat on purpose: redaction walks the context a few levels
                # deep and must not turn real fields into "<max-depth>".
                ctx["observer_gate"] = block["gate"]
                ctx["observer_events"] = block["events"]
                ctx["observer_event_refs"] = [e["event_id"] for e in block["events"]]
        redaction_log.append("applied redaction: sensitive keys/urls/truncation")
        return redact(ctx), redaction_log

    # ------------------------------------------------------------------ WP-05
    # Desktop intake: the Observer owns capture and its own privacy gate; these
    # methods only report what it really did and move its outbox forward.

    def observer_status(self) -> dict:
        """Capture state as it is, including the parts that are degraded."""
        if not self.observer:
            return {"configured": False, "reachable": False,
                    "note": "observer connector is not configured"}
        health = self._safe(lambda timeout: self.observer.health())
        if not isinstance(health, dict) or "error" in health:
            return {"configured": True, "reachable": False, "error": str(health)}
        pending = self._safe(lambda timeout: self.observer.outbox(status="pending"))
        return {
            "configured": True,
            "reachable": True,
            "service": health.get("service"),
            "mode": health.get("mode"),
            "ocr_engine": health.get("ocr_engine"),
            "asr": health.get("asr") or {},
            "pending_outbox": len(pending) if isinstance(pending, list) else None,
        }

    def observer_events(self, limit: int = 10) -> dict:
        """Recent desktop events plus the gate decision for each one."""
        if not self.observer:
            raise ApiError("SERVICE_UNAVAILABLE", "observer connector is not configured")
        events = self._safe(lambda timeout: self.observer.recent_events(limit=limit))
        if not isinstance(events, list):
            raise ApiError("SERVICE_UNAVAILABLE", f"observer events unreadable: {events}")
        block = build_observer_context(events, limit=limit)
        return {"gate": block["gate"], "events": block["events"],
                "total_recorded": len(events)}

    def observer_outbox(self) -> list:
        """Pending memory-write suggestions, before the gate decides anything."""
        if not self.observer:
            raise ApiError("SERVICE_UNAVAILABLE", "observer connector is not configured")
        items = self._safe(lambda timeout: self.observer.outbox(status="pending"))
        if not isinstance(items, list):
            raise ApiError("SERVICE_UNAVAILABLE", f"observer outbox unreadable: {items}")
        return items

    def sweep_observer_outbox(self, max_age_days: float = 7.0,
                              keep_newest: int = 100) -> dict:
        """Bound the observer outbox: nothing here may grow without limit.

        Unconfirmed captures are *not* memory (WP-05 gate), so an old or excess
        suggestion is expired rather than silently written. Two caps apply: age,
        and how many remain pending for the user to confirm.
        """
        items = self.observer_outbox()
        report = {"considered": len(items), "expired_by_age": [], "expired_by_count": [],
                  "kept": [], "errors": []}
        if not items:
            report["summary"] = {"expired": 0, "kept": 0}
            return report

        def _age_days(item) -> float:
            created = str((item or {}).get("created_at") or "")
            if not created:
                return 0.0
            try:
                parsed = created.replace("Z", "+00:00")
                stamp = time.mktime(time.strptime(parsed[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:  # noqa: BLE001 - an unparsable stamp must not expire data
                return 0.0
            return max(0.0, (time.time() - stamp) / 86400.0)

        # newest first, so "keep the newest N" is a slice
        ordered = sorted(items, key=lambda item: str((item or {}).get("created_at") or ""),
                         reverse=True)
        keep_ids = {str((item or {}).get("item_id") or "") for item in ordered[:keep_newest]}
        for item in ordered:
            item_id = str((item or {}).get("item_id") or "")
            if item_id not in keep_ids:
                report["expired_by_count"].append(item_id)
            elif _age_days(item) > max_age_days:
                report["expired_by_age"].append(item_id)
            else:
                report["kept"].append(item_id)
        expiring = report["expired_by_count"] + report["expired_by_age"]
        if expiring:
            # The observer API marks one item per call, and a real backlog runs to
            # hundreds of items (308 when this was written): sequentially that
            # outlives any sane request timeout, so mark in parallel.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(self._mark_outbox_sent, expiring))
        report["summary"] = {"expired": len(report["expired_by_count"])
                             + len(report["expired_by_age"]),
                             "kept": len(report["kept"]),
                             "policy": f"keep newest {keep_newest}, "
                                       f"expire older than {max_age_days:g} days"}
        return report

    def start_observer_outbox_sweeper(self, interval_minutes: float = 30.0) -> bool:
        """Run the sweep in the background so the queue is bounded by itself."""
        if not self.observer or interval_minutes <= 0:
            return False
        if getattr(self, "_outbox_sweeper", None) is not None:
            return True

        def loop():
            while True:
                time.sleep(interval_minutes * 60)
                try:
                    self.sweep_observer_outbox()
                except Exception as exc:  # noqa: BLE001 - a sweeper must never kill the gateway
                    logger.warning("observer outbox sweep failed: %s", exc)

        thread = threading.Thread(target=loop, name="elfred-outbox-sweeper", daemon=True)
        thread.start()
        self._outbox_sweeper = thread
        return True

    def drain_observer_outbox(self, pa_id: str, confirmed: bool = False,
                              limit: int = 20) -> dict:
        """Consume the Observer outbox under the memory-write gate.

        `confirmed=False` is the honest default: a capture the Observer asked the
        user to confirm stays in the outbox instead of quietly becoming memory.
        """
        if not self.observer:
            raise ApiError("SERVICE_UNAVAILABLE", "observer connector is not configured")
        if not self.store.get_profile(pa_id):
            raise ApiError("NOT_FOUND", f"unknown pa_id {pa_id}")
        items = self.observer_outbox()
        report = {"pa_id": pa_id, "confirmed": confirmed, "considered": 0,
                  "written": [], "held": [], "blocked": [], "errors": []}
        for item in items[:max(0, limit)]:
            report["considered"] += 1
            item = item if isinstance(item, dict) else {}
            item_id = str(item.get("item_id") or "")
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            entry = {"item_id": item_id,
                     "event_id": str(payload.get("event_id") or ""),
                     "suggestion_id": str(payload.get("suggestion_id") or "")}
            if str(item.get("item_type") or "") != "memory_write_suggestion":
                entry["action"] = "blocked"
                entry["reason"] = f"unsupported outbox item_type {item.get('item_type')}"
                report["blocked"].append(entry)
                self._mark_outbox_sent(item_id)
                continue
            action, reason = suggestion_action(payload, confirmed)
            entry["reason"] = reason
            if action == "write":
                if not self.emos:
                    entry["action"] = "error"
                    entry["reason"] = "EMOS connector is not configured"
                    report["errors"].append(entry)
                    continue
                text = self._suggestion_text(payload)
                res = self._safe(lambda timeout: self.emos.write(pa_id, entry["event_id"] or "observer",
                                                                 text))
                memory_id = (res.get("payload") or {}).get("memory_id") if isinstance(res, dict) else None
                if not isinstance(res, dict) or "error" in res:
                    entry["action"] = "error"
                    entry["reason"] = f"EMOS write failed: {res}"
                    report["errors"].append(entry)
                    continue
                if not memory_id:
                    entry["action"] = "error"
                    entry["reason"] = f"EMOS accepted the call but wrote no memory: {res}"
                    report["errors"].append(entry)
                    continue
                entry["action"] = "write"
                entry["memory_id"] = memory_id
                report["written"].append(entry)
                self._mark_outbox_sent(item_id)
            elif action == "blocked":
                # Blocked items are terminal: drop them from the pending queue but
                # keep them in the report so the refusal stays visible.
                entry["action"] = "blocked"
                report["blocked"].append(entry)
                self._mark_outbox_sent(item_id)
            else:
                entry["action"] = "hold"
                report["held"].append(entry)
        report["summary"] = {
            "written": len(report["written"]),
            "held": len(report["held"]),
            "blocked": len(report["blocked"]),
            "errors": len(report["errors"]),
        }
        return report

    def _mark_outbox_sent(self, item_id: str) -> None:
        if item_id:
            self._safe(lambda timeout: self.observer.mark_outbox_sent(item_id))

    @staticmethod
    def _suggestion_text(payload: dict) -> str:
        """The memory text handed to EMOS, with its provenance kept in-band."""
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        event_id = str(payload.get("event_id") or "")
        body = summary or title or "desktop context"
        prefix = f"desktop context confirmed by the user (observer event {event_id}): "
        return (prefix + body)[:1200]

    def forget_observer(self, event_id: str = "", app_name: str = "",
                        temporary: bool = False) -> dict:
        """Forget desktop context: the event, one app's history, or all temporary."""
        if not self.observer:
            raise ApiError("SERVICE_UNAVAILABLE", "observer connector is not configured")
        if event_id:
            res = self._safe(lambda timeout: self.observer.delete_event(event_id))
            scope = {"event_id": event_id}
        elif app_name:
            res = self._safe(lambda timeout: self.observer.delete_app_data(app_name))
            scope = {"app_name": app_name}
        elif temporary:
            res = self._safe(lambda timeout: self.observer.clear_temporary_context())
            scope = {"temporary": True}
        else:
            raise ApiError("INVALID_OUTPUT",
                           "forget needs one of: event_id, app_name, temporary")
        if not isinstance(res, dict) or "error" in res:
            raise ApiError("SERVICE_UNAVAILABLE", f"observer forget failed: {res}")
        return {"scope": scope, "observer": res}

    def start(self, run: Run) -> Run:
        """Run up to waiting_approval, then stop (approval gates execution)."""
        try:
            self._emit(run, "run.created", {"state": RunState.created.value})
            self._to(run, RunState.admitted)
            self._to(run, RunState.contextualizing)
            self._emit(run, "context.started", {})
            ctx, redaction_log = self._build_context(run)
            profile = self.store.get_profile(run.pa_id)
            run.context_refs = build_manifest(run.run_id, run.query_summary, profile, ctx, redaction_log)
            self._emit(run, "context.completed", {"refs": list(ctx.keys())})
            self._to(run, RunState.planning)
            policy = self._policy_for(run.pa_id)
            planning_started = time.time()
            allowed = set(policy.available_tools())
            plan2 = getattr(self.planner, "plan2", None)
            if callable(plan2):
                planned_raw, plan_source = plan2(
                    run.query_summary, ctx, tools=policy.available_tools())
            else:
                planned_raw = self.planner.plan(
                    run.query_summary, ctx, tools=policy.available_tools())
                plan_source = getattr(self.planner, "name", "unknown")
            planned = policy.cap_steps(planned_raw)
            # Defense in depth: whatever the planner returns, a step may only name a
            # tool this profile can actually use (execution book WP-06).
            plan = [step for step in planned
                    if not step.get("tool") or step.get("tool") in allowed]
            dropped = [step.get("tool") for step in planned if step not in plan]
            run.plan = plan
            self._emit(run, "plan.created", {
                "steps": len(plan),
                "planner": getattr(self.planner, "name", "unknown"),
                # `source` tells the truth when a model backend fell back, so a
                # silently deterministic plan can never be reported as model output.
                "source": plan_source,
                "planning_ms": int((time.time() - planning_started) * 1000),
                # An empty or trimmed plan must be explainable, never silent.
                "dropped_tools": dropped,
                "note": "no available tool matched the request" if not plan else None,
            })
            # plan.updated carries real information: the plan the planner proposed is
            # not the plan that will run, and the difference is named.
            if dropped:
                self._emit(run, "plan.updated", {
                    "reason": "unavailable tools removed",
                    "dropped_tools": dropped,
                    "steps": len(plan),
                })
            self._to(run, RunState.waiting_approval)
            run.approval = {"pending": True}
            self._emit(run, "approval.required", {"pending": True, "steps": len(plan)})
            self.store.save_run(run)
            return run
        except Exception as e:  # noqa: BLE001  never leave a run stuck mid-pipeline
            logger.exception("run %s failed during start: %s", run.run_id, e)
            return self._fail(run, f"start failed: {e}")

    def _fail(self, run: Run, reason: str) -> Run:
        run.state = RunState.failed
        self._emit(run, "run.failed", {"reason": reason})
        self.store.save_run(run)
        return run

    def _wait_for_resume(self, run: Run, max_seconds: float = 900.0) -> bool:
        """Block the worker while the persisted run is paused.

        Returns False when the run was cancelled or paused past the limit, in which
        case the caller stops without emitting a completion.
        """
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            stored = self.store.get_run(run.run_id)
            if stored is None:
                return True
            if stored.state == RunState.cancelled:
                run.state = RunState.cancelled
                logger.info("run %s cancelled while paused", run.run_id)
                return False
            if not stored.paused:
                run.paused = False
                self._emit(run, "run.status_changed",
                           {"state": run.state.value, "paused": False})
                return True
            time.sleep(0.5)
        self._fail(run, "paused too long; run abandoned")
        return False

    def execute_worker(self, run: Run) -> Run:
        """Entry point for the background executor (async approval mode)."""
        return self._execute(run)

    # A run is "in flight" only while a worker thread is driving it. After a
    # restart, resuming it would replay side effects, so it is failed explicitly
    # (execution book 12.1 recovery loop). A run parked at waiting_approval is not
    # in flight: the user still owns that decision, so it is left untouched.
    IN_FLIGHT_STATES = (RunState.created, RunState.admitted, RunState.contextualizing,
                        RunState.planning, RunState.executing, RunState.verifying,
                        RunState.delivering)

    def recover_interrupted_runs(self) -> int:
        runs = self.store.runs_by_state([state.value for state in self.IN_FLIGHT_STATES])
        for run in runs:
            self._fail(run, "interrupted by a gateway restart; approve a new run to retry")
        if runs:
            logger.warning("recovered %d interrupted run(s) on startup", len(runs))
        return len(runs)

    def _fail_tool(self, run: Run, env, tool: str, code: str, detail: str,
                   retryable: bool = False) -> bool:
        env.status = "failed"
        # A failed tool still produced evidence about what it tried; keep it out of
        # the manifest but do not let the failure vanish from the run record.
        env.error_code = code
        env.retryable = retryable
        env.ended_at = _now()
        env.result_summary = detail
        self._emit(run, "tool.failed", {"tool": tool, "error": code, "detail": detail,
                                        "retryable": retryable})
        return False

    # Execution-book 7.3 wants five ref categories in the manifest. observer /
    # memory / knowledge are known at context time; tasks and skills only exist
    # once the run actually uses them, so they are folded in here rather than
    # being left as empty columns that look implemented.
    REF_BUCKETS = {"todo:": "task_refs", "skill:": "skill_refs", "skillrun:": "skill_refs"}

    def _note_context_refs(self, run: Run, env) -> None:
        refs = dict(run.context_refs or {})
        changed = False
        for ref in list(env.evidence_refs or []) + list(env.artifact_refs or []):
            for prefix, bucket in self.REF_BUCKETS.items():
                if str(ref).startswith(prefix):
                    current = list(refs.get(bucket) or [])
                    if ref not in current:
                        current.append(ref)
                        refs[bucket] = current
                        changed = True
        if changed:
            run.context_refs = refs

    def _call_emos_recall(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        res = self._safe(lambda timeout: self.emos.recall(run.pa_id, run.query_summary))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS recall failed: {res}", retryable=True)
        payload = res.get("payload") or {}
        refs = self._memory_refs(payload)
        env.evidence_refs = list(refs)
        # The recall is fused server-side; naming the backend is what makes the
        # claim checkable instead of a vague "we used memory".
        backend = payload.get("retrieval_backend") or "unknown"
        env.result_summary = f"recalled {len(refs)} memory refs via {backend}"
        return True

    def _call_emos_write(self, run: Run, env, tool: str, step=None) -> bool:
        """Explicit durable write: what the user asked to be remembered."""
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        goal = str((step or {}).get("goal") or run.query_summary)
        text = f"{goal} (context: {run.query_summary})"
        res = self._safe(lambda timeout: self.emos.write(run.pa_id, run.run_id, text))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS write failed: {res}", retryable=True)
        payload = res.get("payload") or {}
        memory_id = payload.get("memory_id")
        if not payload.get("memory_written") or not memory_id:
            reasons = (payload.get("write_policy") or {}).get("reasons")
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"EMOS refused the write (reasons={reasons})")
        env.evidence_refs = [memory_id]
        env.artifact_refs = [memory_id]
        env.result_summary = f"wrote memory {memory_id}"
        env.emotion = payload.get("emotion") or None
        if payload.get("emotion"):
            # WP-04 emotion tag: the affective label belongs to the record, so it
            # travels with the evidence instead of being dropped on the floor.
            self._emit(run, "tool.progress", {"tool": tool, "stage": "emotion_tagged",
                                              "emotion": payload["emotion"]})
        return True

    def _call_emos_forget(self, run: Run, env, tool: str, step=None) -> bool:
        """Soft-forget one memory, with the receipt kept as the evidence ref."""
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        goal = str((step or {}).get("goal") or run.query_summary)
        target = str((step or {}).get("memory_id") or "")
        if not target:
            recalled = self._safe(lambda timeout: self.emos.recall(run.pa_id, goal))
            if isinstance(recalled, dict) and "error" not in recalled:
                target = ((recalled.get("payload") or {}).get("recalled_memory") or
                          {}).get("memory_id") or ""
        if not target:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"nothing in memory matched '{goal[:60]}' to forget")
        res = self._safe(lambda timeout: self.emos.forget(run.pa_id, run.run_id, target,
                                                          reason=goal, source="elfred-pa"))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS forget failed: {res}", retryable=True)
        payload = res.get("payload") or {}
        receipt = (payload.get("execution_surface") or {}).get("operation") or "forget_memory"
        env.evidence_refs = [f"forget:{target}"]
        env.result_summary = f"forgot {target} ({receipt})"
        return True

    def _call_emos_block_set(self, run: Run, env, tool: str, step=None) -> bool:
        """Set a core memory block, then mirror it into the agent's next request.

        The Letta App Server exposes no endpoint for editing an agent's own memory
        blocks, so the mirror is delivered by putting the block into every request
        the planner makes. That is stated in the manifest instead of being implied.
        """
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        goal = str((step or {}).get("goal") or run.query_summary)
        label = str((step or {}).get("label") or "user_profile")
        res = self._safe(lambda timeout: self.emos.set_block(
            run.pa_id, run.run_id, label, goal,
            description="set from an approved PA run", read_only=False,
            source="elfred-pa"))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS block write failed: {res}", retryable=True)
        env.evidence_refs = [f"block:{label}"]
        env.result_summary = f"set memory block {label}"
        return True

    # Filler that appears in a request but carries no retrieval signal. Measured
    # problem: a natural question ("根据我上传的 PPT，<token> 是什么意思？用三点总结，
    # 并给出出处。") searched Typesense with all of that text at once and returned 0
    # hits, while the same run asked as "<token> 是什么" returned the slide. So the
    # search runs a ladder of queries, best-first, and reports which one matched.
    QUERY_FILLERS = ("请帮我", "帮我", "帮忙", "根据", "我上传的", "我传的", "上传的",
                     "这份", "这个", "那个", "关于", "是什么", "什么意思", "意思",
                     "用三点", "三点式", "三点", "总结", "概括", "给出", "出处",
                     "引用", "来源", "回答", "告诉", "一下", "并且", "并", "以及")

    def _query_ladder(self, run: Run, step=None) -> list[str]:
        """Candidate retrieval queries, best first.

        The planner's own step goal is the closest thing to an extracted intent we
        already have; after that come quoted terms, high-signal tokens (latin or
        digit runs, then the longest CJK runs), the de-filled message, and finally
        the raw message - which is what used to be the only behaviour.
        """
        raw = (run.query_summary or "").strip()
        candidates: list[str] = []

        goal = str((step or {}).get("goal") or "").strip()
        if goal:
            candidates.append(goal)
        candidates += [m.group(1).strip() for m in
                        re.finditer(r"[「『\"'“”\"']([^」』\"'“”\"']{2,})[」』\"'“”\"']", raw)]
        latin = [w for w in re.findall(r"[A-Za-z0-9_]{3,}", raw)]
        if latin:
            candidates.append(" ".join(latin[:8]))
        stripped = raw
        for filler in self.QUERY_FILLERS:
            stripped = stripped.replace(filler, " ")
        stripped = re.sub(r"[，。！？、,.!?;；:：\s]+", " ", stripped).strip()
        cjk = [w for w in re.findall(r"[\u4e00-\u9fff]{2,}", stripped)]
        if cjk:
            candidates.append(" ".join(sorted(cjk, key=len, reverse=True)[:3]))
        if stripped:
            candidates.append(stripped[:60])
        candidates.append(raw)

        seen: set[str] = set()
        ladder: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                ladder.append(candidate)
        return ladder

    def _call_knowledge_search(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.knowledge:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no knowledge client")
        res = self._safe(lambda timeout: self._knowledge_hits(run, step))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"knowledge search failed: {res}", retryable=True)
        refs = [h.get("document", {}).get("id") for h in (res.get("hits") or [])
                if isinstance(h, dict)]
        refs = [ref for ref in refs if ref]
        env.evidence_refs = list(refs)
        env.artifact_refs = list(refs)
        # WP-07: a citation is the chunk, not just the document, so the run can be
        # traced back to the exact passage that was used.
        cited = [h for h in (res.get("hits") or []) if h.get("chunk_id")]
        for hit in cited:
            self.store.add_citation(run.run_id, run.pa_id, hit.get("document_id") or "",
                                    hit.get("chunk_id") or "",
                                    (hit.get("text") or "")[:200])
        env.evidence_refs += [h["chunk_id"] for h in cited]
        # Say which query found it: a run that only matched after the ladder
        # degraded must not look like the raw question was searchable.
        env.evidence_refs.append(f"knowledge-query:{res.get('query')}")
        if refs:
            run.artifacts.append({"type": "knowledge", "refs": refs,
                                  "citations": [h["chunk_id"] for h in cited]})
        env.result_summary = (f"{len(refs)} knowledge hits (query: {res.get('query')})"
                              if refs else
                              f"no knowledge hits (tried {len(res.get('tried') or [])} queries)")
        return True

    # Context building calls this on every run, so the ladder has to stay cheap:
    # at most this many candidate queries locally, and one fallback query if the
    # local pipeline is present but found nothing (the fallback exists for the case
    # where the local pipeline is not installed at all).
    MAX_QUERIES_PER_BACKEND = 3

    def _knowledge_hits(self, run: Run, step=None) -> dict:
        """Prefer the local knowledge pipeline (it returns citations); the mobile
        search proxy stays as the capability-library fallback."""
        service = getattr(self, "knowledge_service", None)
        ladder = self._query_ladder(run, step)[:self.MAX_QUERIES_PER_BACKEND]
        tried: list[str] = []
        if service is not None and os.environ.get("PA_KNOWLEDGE_LOCAL", "1") == "1":
            for query in ladder:
                tried.append(query)
                local = service.search(query, pa_id=run.pa_id, per_page=5)
                if local.get("hits"):
                    return {**local, "query": query, "tried": tried}
            # One fallback query, not the whole ladder: the capability proxy is a
            # different index and re-walking the ladder there only adds latency.
            query = ladder[0] if ladder else run.query_summary
            tried.append(query)
        else:
            query = ladder[0] if ladder else run.query_summary
        fallback = self.knowledge.search(query)
        if fallback.get("hits"):
            return {**fallback, "query": query, "tried": tried}
        return {"found": 0, "hits": [], "query": ladder[-1] if ladder else "",
                "tried": tried}

    # --- memory (EMOS is the long-term authority, ADR-002) ---
    def _call_emos_plan_write(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        goal = str((step or {}).get("goal") or run.query_summary)
        text = f"run plan for request '{run.query_summary}': {goal}"
        res = self._safe(lambda timeout: self.emos.write_plan(run.pa_id, run.run_id, text))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS write-plan failed: {res}", retryable=True)
        payload = res.get("payload") or {}
        decision = payload.get("suggested_action") or payload.get("next_action")
        env.evidence_refs = [f"emos-plan:{run.run_id}:{decision}"]
        env.result_summary = f"EMOS plan decision: {decision}"
        return True

    def _call_emos_reflect(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        # persist=False by default: a reflection must not overwrite factual memory
        # (execution book: 反思结果不直接覆盖事实记忆).
        persist = os.environ.get("PA_REFLECT_PERSIST", "false").lower() == "true"
        res = self._safe(lambda timeout: self.emos.reflect(run.pa_id, run.run_id, persist))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS reflect failed: {res}", retryable=True)
        payload = res.get("payload") or {}
        refs = [f"emos-reflect:{run.run_id}"]
        for key in ("reflection_id", "memory_id"):
            if payload.get(key):
                refs.append(str(payload[key]))
        env.evidence_refs = refs
        env.result_summary = f"reflected (persist={persist})"
        return True

    def _call_emos_supersede(self, run: Run, env, tool: str, step=None) -> bool:
        """Change a preference: write the new one and invalidate the previous value.

        This is the "改偏好→旧值失效" path: EMOS supersede marks the old memory as
        superseded, so later recalls cite the new value instead of the old one.
        """
        if not self.emos:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no EMOS client")
        goal = str((step or {}).get("goal") or run.query_summary)
        self._emit(run, "tool.progress", {"tool": tool, "stage": "recalling_previous"})
        recalled = self._safe(lambda timeout: self.emos.recall(run.pa_id, goal))
        old_id = None
        if isinstance(recalled, dict) and "error" not in recalled:
            payload = recalled.get("payload") or {}
            item = payload.get("recalled_memory") or {}
            old_id = item.get("memory_id")
        self._emit(run, "tool.progress", {"tool": tool, "stage": "writing_replacement",
                                          "had_previous": bool(old_id)})
        text = f"user preference update: {goal}. (context: {run.query_summary})"
        written = self._safe(lambda timeout: self.emos.write(run.pa_id, run.run_id, text))
        if not isinstance(written, dict) or "error" in written:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"EMOS write failed: {written}", retryable=True)
        payload = written.get("payload") or {}
        new_id = payload.get("memory_id")
        if not payload.get("memory_written") or not new_id:
            reasons = (payload.get("write_policy") or {}).get("reasons")
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"EMOS refused the write (reasons={reasons}); "
                                   "preferences need substantive text")
        if old_id and old_id != new_id:
            superseded = self._safe(lambda timeout: self.emos.supersede(
                run.pa_id, run.run_id, old_id, new_id, "user changed the preference"))
            if not isinstance(superseded, dict) or "error" in superseded:
                return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                       f"EMOS supersede failed: {superseded}", retryable=True)
            operation = superseded.get("operation")
        else:
            operation = None
        env.evidence_refs = [ref for ref in (f"emos:{old_id}" if old_id else None,
                                            f"emos:{new_id}") if ref]
        run.artifacts.append({"type": "memory", "new_memory_id": new_id,
                              "superseded_memory_id": old_id,
                              # EMOS's own confirmation that the old value is now
                              # marked superseded (not just that we asked).
                              "supersede_operation": operation,
                              "run_id": run.run_id})
        env.result_summary = (f"preference updated: {old_id} -> {new_id}" if old_id
                              else f"preference stored: {new_id} (nothing to supersede)")
        return True

    def _call_task_create(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.freetodo:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no task host client")
        payload = self._task_payload(run, step)
        res = self._safe(lambda timeout: self.freetodo.create_todo(payload, payload["uid"]))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"task host unavailable: {res}", retryable=True)
        ref, uid = res.get("id"), res.get("uid")
        env.artifact_refs = [f"todo:{uid}"]
        env.evidence_refs = [f"run:{run.run_id}"]
        run.artifacts.append({"type": "task", "id": ref, "uid": uid, "run_id": run.run_id})
        env.result_summary = f"task #{ref} {uid} ({res.get('status')})"
        return True

    # --- tasks (FreeTodo-compatible task host) ---
    def _task_uid(self, run: Run, step) -> str:
        """Stable business key: a retried step must not create a second task."""
        index = (step or {}).get("step") or len(run.tool_calls) + 1
        return f"elfred-{run.run_id}-s{index}"

    def _task_payload(self, run: Run, step) -> dict:
        goal = str((step or {}).get("goal") or run.query_summary or "Elfred task")
        return {"uid": self._task_uid(run, step), "name": goal[:120],
                "description": run.query_summary or goal, "status": "active",
                "tags": ["elfred", f"pa-run:{run.run_id}"]}

    @staticmethod
    def _terms(text: str) -> list[str]:
        text = (text or "").lower()
        words = [w for w in re.split(r"[^\w\u4e00-\u9fff]+", text) if len(w) >= 2]
        grams = [text[i:i + 2] for i in range(len(text) - 1)
                 if re.match(r"[\u4e00-\u9fff]", text[i]) and re.match(r"[\u4e00-\u9fff]", text[i + 1])]
        return list(dict.fromkeys(words + grams))[:40]

    def _run_task(self, run: Run):
        """Most recent task this run created (artifacts are its audit trail)."""
        for artifact in reversed(run.artifacts):
            if artifact.get("type") == "task" and artifact.get("uid"):
                return artifact
        return None

    def _search_tasks(self, query: str, limit: int = 5):
        listing = self._safe(lambda timeout: self.freetodo.list_todos())
        if not isinstance(listing, dict) or "error" in listing:
            return None, f"task host unavailable: {listing}"
        todos = listing.get("todos") or []
        terms = self._terms(query)
        scored = []
        for todo in todos:
            haystack = f"{todo.get('name') or ''} {todo.get('description') or ''}".lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, todo))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [todo for _, todo in scored[:limit]], None

    def _call_task_search(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.freetodo:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no task host client")
        query = str((step or {}).get("goal") or run.query_summary)
        hits, error = self._search_tasks(query)
        if error:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", error, retryable=True)
        env.evidence_refs = [f"todo:{t.get('uid')}" for t in hits]
        env.result_summary = f"{len(hits)} task(s) matched"
        return True

    def _call_task_update(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.freetodo:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no task host client")
        target = self._run_task(run)
        if not target and step is not None:
            hits, _ = self._search_tasks(str(step.get("goal") or run.query_summary), limit=1)
            target = {"id": hits[0]["id"], "uid": hits[0]["uid"]} if hits else None
        if not target:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT", "no task to update")
        note = str((step or {}).get("goal") or run.query_summary)
        res = self._safe(lambda timeout: self.freetodo.update_todo(
            int(target["id"]), {"user_notes": note, "related_activity_ids": [run.run_id]}))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"task update failed: {res}", retryable=True)
        env.artifact_refs = [f"todo:{res.get('uid')}"]
        env.result_summary = f"updated task #{res.get('id')}"
        return True

    def _call_task_complete(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.freetodo:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no task host client")
        target = self._run_task(run)
        if not target:
            hits, _ = self._search_tasks(str((step or {}).get("goal") or run.query_summary), limit=1)
            target = {"id": hits[0]["id"], "uid": hits[0]["uid"]} if hits else None
        if not target:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT", "no task to complete")
        res = self._safe(lambda timeout: self.freetodo.update_todo(
            int(target["id"]), {"status": "completed", "percent_complete": 100,
                                "completed_at": _now()}))
        if not isinstance(res, dict) or "error" in res:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"task completion failed: {res}", retryable=True)
        env.artifact_refs = [f"todo:{res.get('uid')}"]
        env.result_summary = f"completed task #{res.get('id')}"
        return True

    # --- skills (Skill Foundry in the FreeTodo adapter) ---
    def _pick_skill(self, run: Run, step):
        context = {"title": str((step or {}).get("goal") or run.query_summary),
                   "description": run.query_summary, "currentApp": "Elfred",
                   "context": f"pa-run:{run.run_id}"}
        matches = self._safe(lambda timeout: self.skill.match(context))
        if isinstance(matches, dict) and matches.get("matches"):
            best = matches["matches"][0]
            skill_id = best.get("skillId") or best.get("skill_id") or best.get("id")
            if skill_id:
                return skill_id, "matched", matches
        listing = self._safe(lambda timeout: self.skill.list_skills())
        if isinstance(listing, dict):
            usable = [s for s in (listing.get("skills") or [])
                      if s.get("status") in ("approved", "active")
                      and (s.get("skill_id") or s.get("id"))]
            if len(usable) == 1:
                return (usable[0].get("skill_id") or usable[0]["id"]), "only-approved-skill", listing
        return None, "no-approved-skill", listing

    def _call_skill_match(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.skill:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE", "no skill adapter")
        skill_id, reason, raw = self._pick_skill(run, step)
        if not skill_id:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT", reason)
        env.evidence_refs = [f"skill:{skill_id}"]
        env.result_summary = f"skill {skill_id} ({reason})"
        return True

    def _call_skill_run(self, run: Run, env, tool: str, step=None) -> bool:
        if not self.skill or not self.freetodo:
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   "skill adapter or task host missing")
        skill_id, reason, _ = self._pick_skill(run, step)
        if not skill_id:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT", reason)
        self._emit(run, "tool.progress", {"tool": tool, "stage": "skill_selected",
                                          "skill": skill_id, "via": reason})
        todo = self._run_task(run)
        if not todo:
            # Reuse a task that already carries the real content (a document, a
            # dossier) before inventing a thin one from this run's request.
            hits, _ = self._search_tasks(str((step or {}).get("goal") or run.query_summary), limit=1)
            if hits:
                todo = {"id": hits[0]["id"], "uid": hits[0]["uid"]}
        if not todo:
            payload = self._task_payload(run, step)
            created = self._safe(lambda timeout: self.freetodo.create_todo(payload, payload["uid"]))
            if not isinstance(created, dict) or "error" in created:
                return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                       f"could not attach a task: {created}", retryable=True)
            todo = {"id": created.get("id"), "uid": created.get("uid")}
            run.artifacts.append({"type": "task", "id": todo["id"], "uid": todo["uid"],
                                  "run_id": run.run_id})
        context = {"freetodoTodoId": int(todo["id"]),
                   "title": str((step or {}).get("goal") or run.query_summary)}
        full = self._safe(lambda timeout: self.freetodo.get_todo(int(todo["id"])))
        parts = []
        if isinstance(full, dict) and "error" not in full:
            parts.extend([full.get("name"), full.get("description"), full.get("user_notes")])
        parts.append(run.query_summary)
        # The skill verifies that it produced N bullet points, so the source text
        # must actually contain enough material: merge every available fragment
        # (task name, body, notes, request) instead of summarising a one-line stub.
        seen: list[str] = []
        for part in parts:
            text = (part or "").strip()
            if text and text not in seen:
                seen.append(text)
        inputs = {"sourceText": "\n".join(seen) or run.query_summary}
        started = time.time()
        self._emit(run, "tool.progress", {"tool": tool, "stage": "running",
                                          "skill": skill_id, "task": todo["uid"]})
        res = self._safe(lambda timeout: self.skill.run(skill_id, inputs, context))
        payload = (res or {}).get("run") if isinstance(res, dict) else None
        if not isinstance(payload, dict):
            return self._fail_tool(run, env, tool, "SERVICE_UNAVAILABLE",
                                   f"skill run failed: {res}", retryable=True)
        run_id = payload.get("run_id")
        self._emit(run, "tool.progress", {
            "tool": tool, "stage": "finished", "skill": skill_id,
            "skill_run": run_id, "status": payload.get("status"),
            "duration_ms": int((time.time() - started) * 1000)})
        if payload.get("status") != "succeeded":
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"skill run {run_id} {payload.get('status')}: {payload.get('error')}")
        env.evidence_refs = [f"skillrun:{run_id}", f"skill:{skill_id}"]
        env.artifact_refs = [f"todo:{todo['uid']}", f"skillrun:{run_id}"]
        run.artifacts.append({"type": "skill_run", "id": run_id, "skill": skill_id,
                              "todo": todo["uid"], "run_id": run.run_id})
        env.result_summary = f"skill {skill_id} ran ({run_id})"
        return True

    # --- controlled local access + delegation ---
    def _allowed_roots(self, run: Run) -> list[str]:
        profile = self.store.get_profile(run.pa_id)
        roots = (profile.boundaries or {}).get("allowed_roots") if profile else []
        return [os.path.realpath(str(r)) for r in (roots or [])]

    def _call_local_file_read(self, run: Run, env, tool: str, step=None) -> bool:
        pattern = r"[A-Za-z]:\\[^\s\"']+|\/[^\s\"']+"
        goal = str((step or {}).get("goal") or "")
        # The planner often paraphrases the goal away from the literal path, so fall
        # back to the user's own request before giving up.
        match = re.search(pattern, goal) or re.search(pattern, run.query_summary or "")
        if not match:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   "no file path in the step goal")
        path = os.path.realpath(match.group(0))
        roots = self._allowed_roots(run)
        if not roots:
            return self._fail_tool(run, env, tool, "POLICY_DENIED",
                                   "no allowed_roots configured for this PA")
        if not any(path == root or path.startswith(root + os.sep) for root in roots):
            return self._fail_tool(run, env, tool, "POLICY_DENIED",
                                   f"{path} is outside the allowed roots")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(8000)
        except Exception as e:  # noqa: BLE001
            return self._fail_tool(run, env, tool, "TOOL_UNAVAILABLE", f"read failed: {e}")
        env.evidence_refs = [f"file:{path}"]
        env.artifact_refs = [f"file:{path}"]
        run.artifacts.append({"type": "file", "path": path, "bytes": len(content),
                              "run_id": run.run_id})
        env.result_summary = f"read {len(content)} chars from {os.path.basename(path)}"
        return True

    CONTENT_MARKERS = ("内容：", "内容:", "content:", "content：")
    MAX_WRITE_BYTES = 64 * 1024

    def _write_payload(self, run: Run, step) -> str:
        """The text to write: explicit step content, else an explicit marker.

        There is deliberately no guesswork: a paraphrase is not a file body, and
        writing the wrong text into a user's file is worse than refusing.
        """
        explicit = (step or {}).get("content")
        if isinstance(explicit, str) and explicit.strip():
            return explicit
        for source in (str((step or {}).get("goal") or ""), run.query_summary or ""):
            for marker in self.CONTENT_MARKERS:
                if marker in source:
                    body = source.split(marker, 1)[1].strip()
                    if body:
                        return body
        return ""

    def _call_local_file_write(self, run: Run, env, tool: str, step=None) -> bool:
        """Write a file inside the PA's allowed roots. Never silently overwrites."""
        pattern = r"[A-Za-z]:\\[^\s\"']+|\/[^\s\"']+"
        goal = str((step or {}).get("goal") or "")
        match = re.search(pattern, goal) or re.search(pattern, run.query_summary or "")
        if not match:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   "no file path in the step goal")
        path = os.path.realpath(match.group(0))
        roots = self._allowed_roots(run)
        if not roots:
            return self._fail_tool(run, env, tool, "POLICY_DENIED",
                                   "no allowed_roots configured for this PA")
        if not any(path == root or path.startswith(root + os.sep) for root in roots):
            return self._fail_tool(run, env, tool, "POLICY_DENIED",
                                   f"{path} is outside the allowed roots")
        content = self._write_payload(run, step)
        if not content:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   "no content to write: the step carried none and the "
                                   "request had no '内容:' payload")
        if len(content.encode("utf-8")) > self.MAX_WRITE_BYTES:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"refusing to write more than "
                                   f"{self.MAX_WRITE_BYTES // 1024} KB in one step")
        existed = os.path.exists(path)
        if existed and not (step or {}).get("overwrite"):
            return self._fail_tool(run, env, tool, "CONFLICT",
                                   f"{path} already exists; set overwrite to replace it")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                written = handle.write(content)
        except Exception as e:  # noqa: BLE001
            return self._fail_tool(run, env, tool, "TOOL_UNAVAILABLE", f"write failed: {e}")
        env.evidence_refs = [f"file:{path}"]
        env.artifact_refs = [f"file:{path}"]
        run.artifacts.append({"type": "file", "path": path, "bytes": written,
                              "mode": "overwrite" if existed else "create",
                              "run_id": run.run_id})
        env.result_summary = (f"wrote {written} chars to {os.path.basename(path)}"
                              + (" (overwrote)" if existed else " (new file)"))
        return True

    def _call_opencode_delegate(self, run: Run, env, tool: str, step=None) -> bool:
        command = os.environ.get("PA_DELEGATE_CMD", "").strip()
        workspace = os.environ.get("PA_DELEGATE_WORKSPACE", "").strip()
        if not command or not workspace:
            return self._fail_tool(run, env, tool, "TOOL_UNAVAILABLE",
                                   "delegation is not configured (PA_DELEGATE_CMD/WORKSPACE)")
        workspace = os.path.realpath(workspace)
        roots = self._allowed_roots(run)
        if roots and not any(workspace == r or workspace.startswith(r + os.sep) for r in roots):
            return self._fail_tool(run, env, tool, "POLICY_DENIED",
                                   f"workspace {workspace} is outside the allowed roots")
        timeout = float(os.environ.get("PA_DELEGATE_TIMEOUT", "180"))
        prompt = str((step or {}).get("goal") or run.query_summary)
        self._emit(run, "tool.progress", {"tool": tool, "stage": "spawned",
                                          "command": command, "workspace": workspace,
                                          "timeout_s": timeout})
        started = time.time()
        # Popen + communicate rather than subprocess.run: the handle has to stay
        # reachable while the harness runs, otherwise cancelling the run can only
        # stop waiting for it and the harness keeps running as an orphan.
        arguments = shlex.split(command) + [prompt]
        proc = subprocess.Popen(arguments, cwd=workspace, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace")
        self.delegates[run.run_id] = proc
        try:
            out, err = proc.communicate(timeout=timeout)
            proc = subprocess.CompletedProcess(arguments, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            self._kill_delegate(run.run_id)
            self._emit(run, "tool.progress", {
                "tool": tool, "stage": "timeout", "command": command,
                "duration_ms": int((time.time() - started) * 1000)})
            return self._fail_tool(run, env, tool, "TIMEOUT",
                                   f"delegation exceeded {timeout}s", retryable=True)
        except Exception as e:  # noqa: BLE001
            return self._fail_tool(run, env, tool, "TOOL_UNAVAILABLE", f"delegation failed: {e}")
        finally:
            self.delegates.pop(run.run_id, None)
        self._emit(run, "tool.progress", {
            "tool": tool, "stage": "finished", "command": command,
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - started) * 1000)})
        output = (proc.stdout or "").strip()
        ref = f"delegation:{run.run_id}:{int(time.time())}"
        env.artifact_refs = [ref]
        env.evidence_refs = [f"delegate-exit:{proc.returncode}"]
        run.artifacts.append({"type": "delegation", "ref": ref, "command": command,
                              "exit_code": proc.returncode, "output": output[:4000],
                              "run_id": run.run_id})
        if proc.returncode != 0:
            return self._fail_tool(run, env, tool, "INVALID_OUTPUT",
                                   f"delegate exited {proc.returncode}: {(proc.stderr or output)[:300]}")
        env.result_summary = f"delegated to {command} (exit 0, {len(output)} chars)"
        return True

    def _execute(self, run: Run) -> Run:
        """Run the planned tools (after approval), then verifying -> delivering -> completed."""
        try:
            policy = self._policy_for(run.pa_id)
            if run.state != RunState.executing:
                self._to(run, RunState.executing)
            for step in run.plan:
                # Between steps the worker re-reads the persisted run: that is what
                # makes pause / cancel work while a run is executing (cross-thread
                # state changes are things the worker itself must observe).
                stored = self.store.get_run(run.run_id)
                if stored is not None and stored.state == RunState.cancelled:
                    logger.info("run %s cancelled mid-execution", run.run_id)
                    run.state = RunState.cancelled
                    return run
                if stored is not None and stored.paused and not run.paused:
                    run.paused = True
                    self._emit(run, "run.status_changed",
                               {"state": run.state.value, "paused": True})
                if run.paused and not self._wait_for_resume(run):
                    return run
                tool = step.get("tool", "unknown")
                env = ToolEnvelope(tool_call_id=f"tool_{run.seq + 1}", run_id=run.run_id, status="started",
                                   started_at=_now(), artifact_refs=[], evidence_refs=[])
                run.tool_calls.append(env)
                self._emit(run, "tool.requested", {"tool": tool})
                if not policy.allow(tool):
                    # The scope is re-checked before anything is announced as
                    # started, so a tool revoked between planning and execution is
                    # refused rather than "started and then denied".
                    env.status = "failed"
                    env.error_code = "POLICY_DENIED"
                    env.ended_at = _now()
                    env.result_summary = f"{tool} not in tool scope"
                    self._emit(run, "tool.failed", {"tool": tool, "error": "POLICY_DENIED"})
                    continue
                if policy.needs_second_approval(tool) and tool not in run.approved_tools:
                    if not self._wait_for_tool_approval(run, tool):
                        self._fail_tool(run, env, tool, "APPROVAL_REQUIRED",
                                        f"{tool} needs its own approval and none came")
                        continue
                self._emit(run, "tool.started", {"tool": tool})
                handlers = {
                    "emos_recall": self._call_emos_recall,
                    "emos_write": self._call_emos_write,
                    "emos_forget": self._call_emos_forget,
                    "emos_block_set": self._call_emos_block_set,
                    "emos_plan_write": self._call_emos_plan_write,
                    "emos_reflect": self._call_emos_reflect,
                    "emos_supersede": self._call_emos_supersede,
                    "knowledge_search": self._call_knowledge_search,
                    "task_create": self._call_task_create,
                    "task_search": self._call_task_search,
                    "task_update": self._call_task_update,
                    "task_complete": self._call_task_complete,
                    "skill_match": self._call_skill_match,
                    "skill_run": self._call_skill_run,
                    "local_file_read": self._call_local_file_read,
                    "local_file_write": self._call_local_file_write,
                    "opencode_delegate": self._call_opencode_delegate,
                }
                handler = handlers.get(tool)
                if handler is None:
                    # Never report an action the gateway cannot actually perform.
                    self._fail_tool(run, env, tool, "TOOL_UNAVAILABLE",
                                    f"{tool} has no implementation yet")
                    continue
                if not handler(run, env, tool, step):
                    continue
                env.status = "completed"
                env.ended_at = _now()
                env.result_summary = env.result_summary or f"ran {tool}"
                self._note_context_refs(run, env)
                self._emit(run, "tool.completed", {"tool": tool})
                self._emit(run, "artifact.created", {"tool": tool, "artifact_refs": env.artifact_refs})
            # A run whose every step failed must not masquerade as a success.
            if run.tool_calls and all(env.status == "failed" for env in run.tool_calls):
                reasons = "; ".join(sorted({env.result_summary or "failed"
                                            for env in run.tool_calls}))
                logger.warning("run %s: all %d step(s) failed: %s",
                               run.run_id, len(run.tool_calls), reasons)
                return self._fail(run, f"all planned steps failed: {reasons}")
            self._to(run, RunState.verifying)
            self._to(run, RunState.delivering)
            self._emit(run, "delivery.ready", {"artifacts": len(run.artifacts)})
            self._to(run, RunState.completed)
            self._emit(run, "run.completed", {})
            self.store.save_run(run)
            return run
        except Exception as e:  # noqa: BLE001
            logger.exception("run %s failed during execution: %s", run.run_id, e)
            return self._fail(run, f"execution failed: {e}")

    def approve(self, run: Run, decision: str, async_execute: bool = False) -> Run:
        """Resolve the approval decision.

        With `async_execute=True` the caller runs `execute_worker` on a thread, so the
        request returns as soon as the decision is recorded — that is what lets
        pause/cancel act on a run that is already executing.
        """
        if run.state != RunState.waiting_approval:
            raise ApiError("CONFLICT", f"run is {run.state.value}, not awaiting approval")
        if run.paused:
            raise ApiError("CONFLICT", "run is paused; resume it before approving")
        run.approval = run.approval or {}
        run.approval["pending"] = False
        run.approval["decision"] = decision
        self._emit(run, "approval.resolved", {"decision": decision})
        if decision != "approve":
            self._to(run, RunState.cancelled)
            self._emit(run, "run.cancelled", {"reason": decision})
            self.store.save_run(run)
            return run
        if async_execute:
            self._to(run, RunState.executing)
            self.store.save_run(run)
            return run
        return self._execute(run)

    def accept(self, run: Run, decision: str, comment: Optional[str] = None) -> Run:
        """Record the user's verdict and write the feedback where the book requires it.

        Feedback goes to EMOS (per cited memory), Skill Foundry (per skill run) and a
        local audit record; a change request additionally derives a revision run while
        the original run and its artifacts stay untouched.
        """
        if run.state != RunState.completed:
            raise ApiError("CONFLICT", f"run is {run.state.value}, only a completed run can be accepted")
        writeback = self._write_feedback(run, decision, comment)
        revision = self._create_revision(run, comment) if decision == "request_changes" else None
        feedback = Feedback(
            feedback_id=f"fb_{uuid.uuid4().hex[:12]}", run_id=run.run_id, pa_id=run.pa_id,
            decision=decision, comment=comment, emos=writeback["emos"],
            skill=writeback["skill"], degraded=writeback["degraded"],
            revision_run_id=revision.run_id if revision else None, created_at=_now())
        self.store.add_feedback(feedback)
        if self.emos:
            self._safe(lambda timeout: self.emos.write(
                run.pa_id, run.run_id, f"acceptance:{decision}:{comment or ''}"))
        self._emit(run, "acceptance.recorded", {
            "decision": decision, "comment": comment,
            "feedback_writtenback": {"emos": len(writeback["emos"]),
                                     "skill": len(writeback["skill"]),
                                     "degraded": writeback["degraded"]},
            "revision_run_id": revision.run_id if revision else None,
        })
        self.store.save_run(run)
        if revision is not None:
            # the revision is a normal run: it plans and parks at the approval gate
            from threading import Thread
            Thread(target=self.start, args=(revision,), daemon=True).start()
        return run

    FEEDBACK_TYPES = {"accept": "correct", "request_changes": "incorrect", "reject": "irrelevant"}

    def _cited_memory_ids(self, run: Run) -> list:
        refs = (run.context_refs or {}).get("memory_refs") or []
        return [ref for ref in refs if isinstance(ref, str) and not ref.startswith("block:")]

    def _write_feedback(self, run: Run, decision: str, comment: Optional[str]) -> dict:
        feedback_type = self.FEEDBACK_TYPES.get(decision, "irrelevant")
        emos_results: list = []
        skill_results: list = []
        degraded: list = []
        if self.emos:
            for memory_id in self._cited_memory_ids(run):
                res = self._safe(lambda timeout: self.emos.feedback(
                    run.pa_id, run.run_id, memory_id, feedback_type,
                    query_text=run.query_summary, notes=comment))
                if isinstance(res, dict) and "error" not in res:
                    emos_results.append({"memory_id": memory_id, "type": feedback_type})
                else:
                    degraded.append(f"emos feedback {memory_id}: {str(res)[:120]}")
        else:
            degraded.append("no EMOS client")
        if self.skill:
            rating = {"accept": 5, "request_changes": 3, "reject": 1}.get(decision)
            for artifact in run.artifacts:
                if artifact.get("type") != "skill_run" or not artifact.get("id"):
                    continue
                res = self._safe(lambda timeout: self.skill.feedback(
                    str(artifact["id"]), rating=rating, outcome=decision, comment=comment))
                if isinstance(res, dict) and "error" not in res:
                    skill_results.append({"skill_run": artifact["id"], "outcome": decision})
                else:
                    degraded.append(f"skill feedback {artifact['id']}: {str(res)[:120]}")
        return {"emos": emos_results, "skill": skill_results, "degraded": degraded}

    def _create_revision(self, run: Run, comment: Optional[str]) -> Run:
        query = run.query_summary
        if comment:
            query = f"{query}\n[修改要求] {comment}"
        revision = self.store.create_run(run.pa_id, query)
        revision.parent_run_id = run.run_id
        self.store.save_run(revision)
        return revision

    def _wait_for_tool_approval(self, run: Run, tool: str, max_seconds: float = 900.0) -> bool:
        """Park the run on a tool-scoped approval and wait for the user's answer.

        The run-level approval only says "the plan may run"; a tool listed in the
        profile's `tool_approval_required` asks once more, after the plan is
        visible, so a write can be refused while the read-only steps still run.
        """
        run.approval = {"pending": True, "scope": "tool", "tool": tool}
        run.paused = True
        # save_run preserves the stored paused flag, so set it explicitly too -
        # otherwise the worker's own pause check blocks on the next iteration.
        self.store.set_run_paused(run.run_id, True)
        self._emit(run, "approval.required", {"pending": True, "scope": "tool",
                                              "tool": tool})
        self.store.save_run(run)
        deadline = time.time() + max_seconds
        while time.time() < deadline:
            stored = self.store.get_run(run.run_id)
            if stored is None:
                return False
            if stored.state == RunState.cancelled:
                run.state = RunState.cancelled
                return False
            decision = stored.approval or {}
            if decision.get("scope") == "tool" and decision.get("tool") == tool:
                if decision.get("approved") is True:
                    run.approved_tools = list(run.approved_tools) + [tool]
                    run.approval = {"approved": True, "scope": "tool", "tool": tool}
                    run.paused = False
                    self.store.set_run_paused(run.run_id, False)
                    self._emit(run, "tool.progress", {"tool": tool,
                                                      "stage": "tool_approved"})
                    self.store.save_run(run)
                    return True
                if decision.get("approved") is False:
                    run.approval = {"approved": False, "scope": "tool", "tool": tool}
                    run.paused = False
                    self.store.set_run_paused(run.run_id, False)
                    self.store.save_run(run)
                    return False
            time.sleep(0.5)
        run.paused = False
        self.store.set_run_paused(run.run_id, False)
        self.store.save_run(run)
        return False

    def _kill_delegate(self, run_id: str) -> bool:
        """Kill a live delegation for this run, process tree included.

        The harness is usually a wrapper (`cmd`/`node`), so killing only the direct
        child would leave the real worker running.
        """
        proc = self.delegates.pop(run_id, None)
        if proc is None or proc.poll() is not None:
            return False
        try:
            if os.name == "nt":
                # The launcher (`python.exe` shim) often spawns the real worker as a
                # child; taskkill /T can miss it once the shim dies, so take the
                # children down first and then the tree.
                subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"Get-CimInstance Win32_Process -Filter "
                                f"'ParentProcessId={proc.pid}' | ForEach-Object "
                                f"{{ Stop-Process -Id $_.ProcessId -Force "
                                f"-ErrorAction SilentlyContinue }}"],
                               capture_output=True)
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:  # pragma: no cover - Phase-1 runs on Windows
                proc.terminate()
        except Exception:  # noqa: BLE001 - never let cleanup break the cancel
            proc.kill()
        return True

    def cancel(self, run: Run, reason: str = "user_cancelled") -> Run:
        """User-initiated cancellation.

        Only a run parked at the approval gate can be cancelled exactly: a run that
        is already executing has a live worker whose steps would race the state
        change. Those are reported as a conflict instead of being half-cancelled.
        """
        if run.state == RunState.cancelled:
            return run
        if run.state == RunState.executing and approval_mode() == "async":
            # The worker re-reads the persisted state between steps and stops by
            # itself, so this is an exact cancel rather than a half one.
            self._kill_delegate(run.run_id)
            self._to(run, RunState.cancelled)
            self._emit(run, "run.cancelled", {"reason": reason})
            self.store.save_run(run)
            return run
        if run.state != RunState.waiting_approval:
            raise ApiError("CONFLICT",
                           f"run is {run.state.value}; only a run awaiting approval can be cancelled")
        run.approval = {**(run.approval or {}), "pending": False, "decision": "cancel"}
        self._to(run, RunState.cancelled)
        self._emit(run, "run.cancelled", {"reason": reason})
        self.store.save_run(run)
        return run

    TERMINAL_STATES = (RunState.completed, RunState.failed, RunState.cancelled)

    def pause(self, run: Run) -> Run:
        """Freeze the run at its current state.

        Phase-1 semantics: pausing stops the run from advancing (a run parked at the
        approval gate can no longer be approved). Pausing a run that is already
        executing is refused rather than faked, because approval currently executes
        inline; a true mid-execution pause needs the async executor.
        """
        if run.state in self.TERMINAL_STATES:
            raise ApiError("CONFLICT", f"run is {run.state.value}; a finished run cannot be paused")
        if run.state == RunState.executing and approval_mode() != "async":
            raise ApiError("CONFLICT",
                           "run is executing; mid-execution pause needs the async executor")
        if run.paused:
            return run
        self.store.set_run_paused(run.run_id, True)
        run.paused = True
        self._emit(run, "run.status_changed", {"state": run.state.value, "paused": True})
        self.store.save_run(run)
        return run

    def resume(self, run: Run) -> Run:
        if not run.paused:
            return run
        if run.state in self.TERMINAL_STATES:
            raise ApiError("CONFLICT", f"run is {run.state.value}; a finished run cannot be resumed")
        self.store.set_run_paused(run.run_id, False)
        run.paused = False
        self._emit(run, "run.status_changed", {"state": run.state.value, "paused": False})
        self.store.save_run(run)
        return run
