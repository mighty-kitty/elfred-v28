# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi import File, Form, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .models import PAProfile, PAState, Run, RunEvent, Session, AcceptRequest
from .db import DbStore
from .engine import RunEngine, approval_mode
from .calibration import ALIGNMENT_CORPUS, DECISION_CORPUS, compute_gates, is_ready
from .knowledge import KnowledgeError, KnowledgeService, store_upload
from .tracing import set_trace_id
from .planners import select_planner
from connectors import (EmosClient, OrganizerClient, KnowledgeClient, FreeTodoClient, SkillClient,
                        LettaClient, ObserverClient)

app = FastAPI(title="Elfred PA Gateway")

# The PC workbench is served from the gateway so the console is same-origin with
# the API (no CORS shim, no second UI stack). The existing pages keep working.
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))  # .../Elfred-PA-Product
_pc_workbench = os.path.join(_repo_root, "apps", "pc-agent-workbench")
if os.path.isdir(_pc_workbench):
    app.mount("/pc", StaticFiles(directory=_pc_workbench, html=True), name="pc-workbench")
app.add_middleware(
    CORSMiddleware,
    # Local development origins: the mobile BFF (:5173), the legacy workbench
    # (:3000) and the V28 frontend (:5200 - see apps/v28-frontend). Deployments
    # can extend this with ELFRED_CORS_ORIGINS (comma separated) instead of
    # editing code.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:5200",
        "http://127.0.0.1:5200",
        *[
            origin.strip()
            for origin in os.environ.get("ELFRED_CORS_ORIGINS", "").split(",")
            if origin.strip()
        ],
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
store = DbStore()
# planner: use LLM if LLM_* env is configured, else deterministic (v0)
engine = RunEngine(store, EmosClient(), OrganizerClient(), KnowledgeClient(), FreeTodoClient(),
                   skill=SkillClient(), observer=ObserverClient(), planner=select_planner())
# WP-07: ingestion owns its own pipeline; the run engine only reads from it.
knowledge_service = KnowledgeService(store)
engine.knowledge_service = knowledge_service
# Anything left mid-flight by a crash or a restart is closed out honestly instead
# of being silently resumed (which would replay side effects).
engine.recover_interrupted_runs()
# The observer outbox must not grow forever: unconfirmed desktop suggestions are
# swept on a timer (see RunEngine.sweep_observer_outbox).
engine.start_observer_outbox_sweeper(float(os.environ.get("PA_OUTBOX_SWEEP_MINUTES", "30")))

logger = logging.getLogger("elfred.pa-gateway")
logging.basicConfig(level=logging.INFO, format="%(message)s")


@app.middleware("http")
async def trace_and_log(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    # Carry the same id into every downstream call this request makes.
    set_trace_id(trace_id)
    logger.info(json.dumps({"level": "info", "trace_id": trace_id, "path": request.url.path,
                            "method": request.method}, ensure_ascii=False))
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(HTTPException)
async def http_exc_handler(request: Request, exc: HTTPException):
    code = {404: "NOT_FOUND", 422: "INVALID_OUTPUT", 403: "POLICY_DENIED",
            503: "SERVICE_UNAVAILABLE", 409: "CONFLICT", 504: "TIMEOUT"}.get(
        exc.status_code, "INVALID_OUTPUT")
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code,
                        content={"code": code, "message": detail,
                                 "trace_id": getattr(request.state, "trace_id", None)})


@app.get("/health")
def health():
    return {"status": "ok", "store": "sqlite", "planner": engine.planner.name}


def _idem(request: Request, key_name: str):
    key = request.headers.get("Idempotency-Key")
    if not key:
        return None
    row = store.get_idempotent(key)
    if row and row["resource_type"] == key_name:
        if key_name == "profile":
            return store.get_profile(row["resource_id"])
        return store.get_run(row["resource_id"])
    return ("new", key)


@app.post("/v1/pa/profiles", response_model=PAProfile)
def create_profile(request: Request, payload: dict):
    idem = _idem(request, "profile")
    if isinstance(idem, PAProfile):
        return idem
    p = store.create_profile(user_id=payload.get("user_id", "user_1"),
                             persona=payload.get("persona", {}),
                             preferences=payload.get("preferences", {}),
                             boundaries=payload.get("boundaries", {}),
                             knowledge_sources=payload.get("knowledge_sources", []),
                             tool_scopes=payload.get("tool_scopes", []),
                             consent_version=payload.get("consent_version", 0))
    if idem:
        store.set_idempotent(idem[1], "profile", p.pa_id)
    return p


def _load_profile_or_404(pa_id: str) -> PAProfile:
    p = store.get_profile(pa_id)
    if not p:
        raise HTTPException(404, "profile not found")
    return p


def _to_state(p: PAProfile, state: PAState) -> PAProfile:
    p.state = state
    return store.save_profile(p)


@app.get("/v1/pa/profiles/{pa_id}")
def get_profile(pa_id: str):
    return _load_profile_or_404(pa_id)


@app.post("/v1/pa/profiles/{pa_id}/initialize")
def initialize_profile(pa_id: str):
    """Execution book 7.1: onboarding -> initializing -> calibrating.

    Binds the PA本体 (Letta agent + EMOS memory namespace). Reports per-step
    status honestly: a step that is not wired yet is reported as pending, never faked.
    """
    p = _load_profile_or_404(pa_id)
    if p.state in (PAState.trial_ready, PAState.active):
        return {"pa": p, "steps": [{"step": "already_initialized", "status": "ok"}]}
    _to_state(p, PAState.initializing)
    steps: list[dict] = []
    # 1) Letta agent binding — verified against the running App Server, never assumed.
    configured = os.environ.get("LETTA_AGENT_ID", "")
    if not configured:
        steps.append({"step": "letta_agent", "status": "pending",
                      "detail": "LETTA_AGENT_ID is not configured"})
    else:
        try:
            listed = [m.get("id") for m in LettaClient().models().get("data", [])]
            if any(m == os.environ.get("LETTA_MODEL", configured) or m == configured
                   for m in listed):
                p.letta_agent_id = configured
                steps.append({"step": "letta_agent", "status": "ok",
                              "detail": f"{configured} (verified against the App Server)"})
            else:
                steps.append({"step": "letta_agent", "status": "degraded",
                              "detail": f"{configured} not listed by the App Server: {listed}"})
        except Exception as e:  # noqa: BLE001
            steps.append({"step": "letta_agent", "status": "degraded",
                          "detail": f"App Server unreachable: {e}"})
    # 2) EMOS memory namespace binding.
    if engine.emos:
        try:
            # The PA's memory namespace is keyed by pa_id, matching recall and writeback.
            engine.emos.health()
            p.emos_profile_ref = f"emos:{p.pa_id}"
            # EMOS rejects low-signal text, so persist the user's *declared*
            # preferences instead of a synthetic marker note.
            declared = {**(p.persona or {}), **(p.preferences or {})}
            if declared:
                note = "user declared preferences: " + ", ".join(
                    f"{k}={v}" for k, v in declared.items())
                res = engine.emos.write(p.pa_id, p.pa_id, note)
                stored = bool((res.get("payload") or {}).get("memory_written"))
                steps.append({
                    "step": "emos_binding",
                    "status": "ok" if stored else "degraded",
                    "detail": p.emos_profile_ref if stored
                    else "namespace ready; declared preferences were not stored",
                })
            else:
                steps.append({"step": "emos_binding", "status": "ok",
                              "detail": f"{p.emos_profile_ref} (no declared preferences yet)"})
        except Exception as e:  # noqa: BLE001
            steps.append({"step": "emos_binding", "status": "degraded", "detail": str(e)})
    else:
        steps.append({"step": "emos_binding", "status": "degraded", "detail": "no EMOS client"})
    _to_state(p, PAState.calibrating)
    return {"pa": p, "steps": steps}


@app.post("/v1/pa/profiles/{pa_id}/activate")
def activate_profile(pa_id: str):
    """Only a PA that passed both calibration gates and has consent may go active."""
    p = _load_profile_or_404(pa_id)
    if p.state == PAState.active:
        return p
    if p.state != PAState.trial_ready:
        raise HTTPException(409, f"PA is {p.state.value}, only trial_ready can be activated")
    return _to_state(p, PAState.active)


@app.patch("/v1/pa/profiles/{pa_id}", response_model=PAProfile)
def patch_profile(pa_id: str, payload: dict):
    """Partial profile update (書 §6.1). Bumps profile_version so runs can cite it."""
    p = _load_profile_or_404(pa_id)
    for field in ("persona", "preferences", "boundaries",
                  "knowledge_sources", "tool_scopes"):
        if field in payload:
            setattr(p, field, payload[field])
    p.profile_version += 1
    return store.save_profile(p)


@app.post("/v1/pa/profiles/{pa_id}/consents", response_model=PAProfile)
def record_consent(pa_id: str, payload: dict):
    """Record a (monotonically increasing) user consent version.

    Consent is what turns a calibrated PA into trial_ready, so this is where the
    §7.1 gate condition actually lands.
    """
    p = _load_profile_or_404(pa_id)
    version = int(payload.get("consent_version", p.consent_version + 1))
    if version <= p.consent_version:
        raise HTTPException(409, f"consent_version must increase (current {p.consent_version})")
    p.consent_version = version
    calibration = store.get_calibration(pa_id)
    if calibration and is_ready(calibration["gates"], p.consent_version) and p.state in (
            PAState.onboarding, PAState.initializing, PAState.calibrating):
        p.state = PAState.trial_ready
    return store.save_profile(p)


@app.post("/v1/pa/{pa_id}/messages", response_model=Run)
def send_message(pa_id: str, request: Request, payload: dict):
    profile = _load_profile_or_404(pa_id)
    if profile.state in (PAState.suspended, PAState.archived):
        raise HTTPException(409, f"PA is {profile.state.value}")
    idem = _idem(request, "run")
    if isinstance(idem, Run):
        return idem
    run = store.create_run(pa_id, payload.get("message", ""))
    # snapshot before the worker thread starts mutating the shared run object,
    # otherwise the accepted state returned to the client is nondeterministic
    accepted = Run(run_id=run.run_id, pa_id=run.pa_id, state=run.state,
                   query_summary=run.query_summary)
    if idem:
        store.set_idempotent(idem[1], "run", run.run_id)
    threading.Thread(target=engine.start, args=(run,), daemon=True).start()
    return accepted


@app.get("/v1/runs/{run_id}", response_model=Run)
def get_run(run_id: str):
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.get("/v1/runs/{run_id}/events")
def get_events(run_id: str, request: Request, last_event_id: str | None = Header(default=None)):
    # Lock-free read: this handler runs while the run that was just created is
    # still being written, and queueing behind that writer delayed the stream's
    # first event by ~1s (measured). The generator below uses the same reader.
    r = store.read_run_unlocked(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    start = 0
    if last_event_id:
        try:
            start = int(last_event_id)
        except ValueError:
            start = 0

    def gen():
        yield "event: connected\ndata: {\"ok\":true}\n\n"
        last = start
        deadline = time.time() + 30
        while time.time() < deadline:
            r = store.read_run_unlocked(run_id)
            events = r.events if r else []
            for e in events:
                seq = e["event_seq"] if isinstance(e, dict) else e.event_seq
                if seq > last:
                    typ = e["type"] if isinstance(e, dict) else e.type
                    data = dict(e) if isinstance(e, dict) else e.model_dump()
                    yield f"id: {seq}\nevent: {typ}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                    last = seq
            terminal = r and r.state.value in ("completed", "failed", "cancelled")
            if terminal and not any(
                    (e["event_seq"] if isinstance(e, dict) else e.event_seq) > last for e in events):
                break
            time.sleep(0.15)
    return StreamingResponse(gen(), media_type="text/event-stream")


def _load_run_or_404(run_id: str) -> Run:
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.post("/v1/runs/{run_id}/approvals")
def approval(run_id: str, payload: dict):
    run = _load_run_or_404(run_id)
    pending = run.approval or {}
    if pending.get("pending") and pending.get("scope") == "tool":
        # This is the tool-scoped second approval: the worker is waiting on the
        # decision, so record it and let the worker pick it up.
        decision = str(payload.get("decision", "approve"))
        run.approval = {"approved": decision == "approve", "scope": "tool",
                        "tool": pending.get("tool")}
        return store.save_run(run)
    async_mode = approval_mode() == "async"
    run = engine.approve(run, payload.get("decision", "approve"),
                         async_execute=async_mode)
    if async_mode and run.state.value == "executing":
        # Execution continues on a worker thread; the client follows SSE and can
        # pause / cancel while it runs.
        threading.Thread(target=engine.execute_worker, args=(run,), daemon=True).start()
    return run


@app.post("/v1/runs/{run_id}/acceptance")
def acceptance(run_id: str, payload: AcceptRequest):
    return engine.accept(_load_run_or_404(run_id), payload.decision, payload.comment)


@app.get("/v1/runs/{run_id}/artifacts")
def run_artifacts(run_id: str):
    run = _load_run_or_404(run_id)
    return {"run_id": run.run_id, "total": len(run.artifacts), "artifacts": run.artifacts}


@app.get("/v1/runs/{run_id}/feedback")
def run_feedback(run_id: str):
    """Audit trail of the user's verdict + where it was written back (WP-09)."""
    run = _load_run_or_404(run_id)
    rows = store.list_feedback(run.run_id)
    return {"run_id": run.run_id, "total": len(rows), "feedback": rows}


@app.get("/v1/runs/{run_id}/revisions")
def run_revisions(run_id: str):
    """Runs derived from this one by a change request (the original is untouched)."""
    run = _load_run_or_404(run_id)
    revisions = store.list_child_runs(run.run_id)
    return {"run_id": run.run_id, "total": len(revisions), "revisions": revisions}


@app.post("/v1/runs/{run_id}/cancel")
def cancel_run(run_id: str, payload: dict | None = None):
    return engine.cancel(_load_run_or_404(run_id), (payload or {}).get("reason", "user_cancelled"))


@app.post("/v1/runs/{run_id}/pause")
def pause_run(run_id: str):
    """Freeze a run so it cannot advance (書 §6.1)."""
    return engine.pause(_load_run_or_404(run_id))


@app.post("/v1/runs/{run_id}/resume")
def resume_run(run_id: str):
    return engine.resume(_load_run_or_404(run_id))


@app.post("/v1/pa/profiles/{pa_id}/calibrate")
def calibrate(pa_id: str, payload: dict):
    p = _load_profile_or_404(pa_id)
    gates = compute_gates(payload)
    store.set_calibration(pa_id, payload, gates)
    # 7.1: both gates passing + user consent moves the PA to trial_ready.
    if is_ready(gates, p.consent_version) and p.state in (
            PAState.onboarding, PAState.initializing, PAState.calibrating):
        p = _to_state(p, PAState.trial_ready)
    gates["pa_state"] = p.state.value
    return gates


@app.get("/v1/pa/profiles/{pa_id}/readiness")
def readiness(pa_id: str):
    p = store.get_profile(pa_id)
    if not p:
        raise HTTPException(404, "profile not found")
    cal = store.get_calibration(pa_id)
    if cal:
        gates = cal["gates"]
    else:
        gates = compute_gates({"decision": {}, "alignment": {}})
    ready = is_ready(gates, p.consent_version)
    return {"pa_id": pa_id, **gates, "consent_version": p.consent_version, "ready": ready}


@app.get("/v1/tasks")
def list_tasks(limit: int = 100, status: str | None = None):
    """Real task list for the PC workbench (Phase-1 task authority).

    Served through the gateway so the workbench stays same-origin, and so the
    task host is never exposed to the browser directly.
    """
    if not engine.freetodo:
        raise HTTPException(503, "task host not configured")
    try:
        listing = engine.freetodo.list_todos(status)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"task host unavailable: {e}") from e
    todos = listing.get("todos", []) if isinstance(listing, dict) else []
    total = listing.get("total", len(todos)) if isinstance(listing, dict) else len(todos)
    return {"tasks": todos[:limit], "total": total}


@app.get("/v1/pa/current")
def current_pa():
    """The PA this gateway last worked on.

    The frontend cannot discover a pa_id on its own and every read it needs is
    keyed by one, so it asks here instead of inventing an identifier. Returns
    null when no PA exists yet - the caller shows an empty state, not a guess.

    """
    profile = store.most_recent_profile()
    if not profile:
        return {"pa_id": None, "state": None, "profile_version": None}
    return {
        "pa_id": profile.pa_id,
        "state": profile.state.value,
        "profile_version": profile.profile_version,
    }


@app.get("/v1/memories")
def list_memories(pa_id: str, limit: int = 50):
    """Long-term memory rows for a PA, read from EMOS (the authority, ADR-002).

    Exposed so the frontend can show what the agent actually remembers without
    talking to EMOS directly. This is a read-only projection: writing memory
    stays behind the agent run and the user's confirmation gate.
    """
    if not engine.emos:
        raise HTTPException(503, "memory service not configured")
    try:
        body = engine.emos.memories(pa_id, limit=limit)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"memory service unavailable: {e}") from e
    rows = body.get("memories", []) if isinstance(body, dict) else []
    return {
        "pa_id": pa_id,
        "memories": [
            {
                "memory_id": row.get("memory_id"),
                "text": row.get("text"),
                "category": row.get("category"),
                "created_at": row.get("created_at"),
            }
            for row in rows
            if isinstance(row, dict)
        ],
    }


@app.get("/v1/skills")
def list_skills():
    """Real Skill Foundry library (proxied so the workbench stays same-origin)."""
    if not engine.skill:
        raise HTTPException(503, "skill adapter not configured")
    try:
        body = engine.skill.list_skills()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"skill adapter unavailable: {e}") from e
    skills = body.get("skills", []) if isinstance(body, dict) else []
    return {"total": len(skills), "skills": skills}


@app.get("/v1/skill-runs")
def list_skill_runs(limit: int = 50):
    if not engine.skill:
        raise HTTPException(503, "skill adapter not configured")
    try:
        body = engine.skill.runs()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"skill adapter unavailable: {e}") from e
    runs = body.get("runs", []) if isinstance(body, dict) else []
    return {"total": len(runs), "runs": runs[:limit]}


@app.get("/v1/knowledge/assets")
def knowledge_assets(per_page: int = 20, page: int = 1):
    """Capability assets from the mobile knowledge backend (Typesense)."""
    if not engine.knowledge:
        raise HTTPException(503, "knowledge backend not configured")
    try:
        body = engine.knowledge.assets(per_page=per_page, page=page)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"knowledge backend unavailable: {e}") from e
    return body


@app.get("/v1/knowledge/search")
def knowledge_search(q: str, pa_id: str = "", kind: str = "", per_page: int = 5):
    """Search the ingested knowledge base, falling back to the capability library.

    The local pipeline wins when it has hits because only it can cite the exact
    chunk that was used; the capability proxy stays for the shared asset library.
    """
    if not q.strip():
        raise HTTPException(422, "q is required")
    local = _knowledge_call(knowledge_service.search, q, pa_id=pa_id, kind=kind,
                            per_page=per_page)
    if local.get("hits"):
        return {**local, "source": "knowledge"}
    if not engine.knowledge:
        return {**local, "source": "knowledge"}
    try:
        capability = engine.knowledge.search(q, per_page=per_page)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"knowledge backend unavailable: {e}") from e
    return {"found": capability.get("found", 0), "hits": capability.get("hits", []),
            "source": "capability"}


def _load_session_or_404(session_id: str) -> Session:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    return session


def _session_view(session: Session) -> dict:
    """Session + the live state of its focused run (both devices read this)."""
    view = session.model_dump()
    if session.run_id:
        run = store.get_run(session.run_id)
        view["run"] = {"run_id": run.run_id, "state": run.state.value,
                       "paused": run.paused, "plan_steps": len(run.plan),
                       "artifacts": len(run.artifacts),
                       "awaiting_approval": run.state.value == "waiting_approval"}
    else:
        view["run"] = None
    return view


@app.post("/v1/pa/{pa_id}/sessions")
def create_or_join_session(pa_id: str, payload: dict):
    """Create a session, or join an existing one with its session_id (pairing).

    `POST /v1/pa/{id}/sessions` is the book's cross-device entry point: the PC
    creates the session, the mobile joins it and both then observe the same run.
    """
    profile = _load_profile_or_404(pa_id)
    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(422, "device_id is required")
    role = str(payload.get("role") or "other")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    session_id = payload.get("session_id")
    if session_id:
        session = _load_session_or_404(session_id)
        if session.pa_id != profile.pa_id:
            raise HTTPException(409, "session belongs to a different PA")
        if session.status != "active":
            raise HTTPException(409, f"session is {session.status}")
    else:
        session = Session(session_id=f"sess_{uuid.uuid4().hex[:12]}", pa_id=profile.pa_id,
                          created_at=now, updated_at=now)

    existing = next((d for d in session.devices if d.get("device_id") == device_id), None)
    if existing:
        existing["last_seen_at"] = now
        existing["role"] = role or existing.get("role")
    else:
        session.devices.append({"device_id": device_id, "role": role,
                                "joined_at": now, "last_seen_at": now})
    if payload.get("run_id"):
        run = _load_run_or_404(str(payload["run_id"]))
        if run.pa_id != profile.pa_id:
            raise HTTPException(409, "run belongs to a different PA")
        session.run_id = run.run_id
    return _session_view(store.save_session(session))


@app.get("/v1/sessions/{session_id}")
def get_session(session_id: str):
    return _session_view(_load_session_or_404(session_id))


@app.post("/v1/sessions/{session_id}/focus")
def focus_session(session_id: str, payload: dict):
    """Point the session at a run (mobile 'continues' the run the PC started)."""
    session = _load_session_or_404(session_id)
    if session.status != "active":
        raise HTTPException(409, f"session is {session.status}")
    run_id = str(payload.get("run_id") or "")
    run = _load_run_or_404(run_id)
    if run.pa_id != session.pa_id:
        raise HTTPException(409, "run belongs to a different PA")
    session.run_id = run.run_id
    return _session_view(store.save_session(session))


@app.post("/v1/sessions/{session_id}/close")
def close_session(session_id: str):
    session = _load_session_or_404(session_id)
    if session.status != "closed":
        session.status = "closed"
        store.save_session(session)
    return _session_view(session)


# ---------------------------------------------------------------- WP-05 intake
# The Observer owns capture and its own privacy gate; the gateway only reports
# what it really did, moves its outbox forward under the memory-write gate, and
# lets the user forget desktop context.


@app.get("/v1/observer/health")
def observer_health():
    return engine.observer_status()


@app.get("/v1/observer/events")
def observer_events(limit: int = 10):
    return engine.observer_events(limit=max(1, min(limit, 50)))


@app.get("/v1/observer/outbox")
def observer_outbox():
    items = engine.observer_outbox()
    return {"pending": len(items), "items": items}


@app.post("/v1/observer/outbox/sweep")
def observer_outbox_sweep(payload: dict = None):
    """Expire unconfirmed suggestions by age or by count (never writes memory)."""
    payload = payload or {}
    return engine.sweep_observer_outbox(
        max_age_days=float(payload.get("max_age_days", 7)),
        keep_newest=int(payload.get("keep_newest", 100)))


@app.post("/v1/observer/outbox/drain")
def observer_outbox_drain(payload: dict):
    """Promote confirmed captures into EMOS; hold or block everything else."""
    pa_id = str(payload.get("pa_id") or "")
    if not pa_id:
        raise HTTPException(422, "pa_id is required: desktop context is memory, "
                                 "and memory belongs to a PA namespace")
    limit = int(payload.get("limit") or 20)
    return engine.drain_observer_outbox(pa_id, confirmed=bool(payload.get("confirmed")),
                                        limit=max(1, min(limit, 100)))


@app.post("/v1/observer/forget")
def observer_forget(payload: dict):
    """Forget one event, one app's history, or all temporary desktop context."""
    return engine.forget_observer(event_id=str(payload.get("event_id") or ""),
                                  app_name=str(payload.get("app_name") or ""),
                                  temporary=bool(payload.get("temporary")))


# ------------------------------------------------------------- WP-07 knowledge
# Upload -> parse -> chunk -> index -> cite -> delete -> rebuild. The ingest
# endpoints take a local path because Phase-1 ingests files on the same machine;
# nothing here pretends a file was parsed when it was not.


def _knowledge_call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except KnowledgeError as exc:
        raise HTTPException(503 if exc.code in ("INDEX_UNAVAILABLE", "INDEX_WRITE_FAILED",
                                                "INDEX_DELETE_FAILED", "PARSER_UNAVAILABLE")
                            else 422, f"{exc.code}: {exc.message}")
    except Exception as exc:  # noqa: BLE001 - a named failure, never a blank 500
        logger.exception("knowledge call failed: %s", exc)
        raise HTTPException(500, f"{type(exc).__name__}: {exc}")


@app.get("/v1/knowledge/sources")
def knowledge_sources(kind: str = "", pa_id: str = ""):
    return {"sources": store.list_sources(kind=kind, pa_id=pa_id)}


@app.post("/v1/knowledge/sources")
def knowledge_create_source(payload: dict):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "name is required")
    return knowledge_service.ensure_source(name, str(payload.get("kind") or "personal"),
                                           str(payload.get("pa_id") or ""))


@app.get("/v1/knowledge/documents")
def knowledge_documents(source_id: str = "", status: str = ""):
    return {"documents": store.list_documents(source_id=source_id, status=status)}


@app.post("/v1/knowledge/documents")
def knowledge_ingest(payload: dict):
    path = str(payload.get("path") or "").strip()
    if not path:
        raise HTTPException(422, "path is required: Phase-1 ingests a local file")
    return _knowledge_call(knowledge_service.ingest, path,
                           title=str(payload.get("title") or ""),
                           kind=str(payload.get("kind") or "personal"),
                           pa_id=str(payload.get("pa_id") or ""),
                           source_name=str(payload.get("source_name") or ""))


@app.delete("/v1/knowledge/documents/{document_id}")
def knowledge_delete(document_id: str):
    return _knowledge_call(knowledge_service.delete, document_id)


@app.post("/v1/knowledge/uploads")
async def knowledge_upload(file: UploadFile = File(...), pa_id: str = Form(""),
                           title: str = Form(""), kind: str = Form("personal"),
                           source_name: str = Form("upload")):
    """Upload a document, then run it through the same parse -> chunk -> index path.

    This is the entry point a phone or browser uses; the path-based endpoint above
    stays for local ingestion. The body is validated and stored before it is
    parsed, so a rejected upload never leaves a half-file to be indexed later.
    """
    data = await file.read()
    path = _knowledge_call(store_upload, pa_id, file.filename or "", data)
    result = _knowledge_call(knowledge_service.ingest, path,
                             title=title or path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1],
                             kind=kind, pa_id=pa_id, source_name=source_name)
    return {**result, "stored_path": path, "bytes": len(data)}


@app.post("/v1/knowledge/rebuild")
def knowledge_rebuild(payload: dict = None):
    payload = payload or {}
    return _knowledge_call(knowledge_service.rebuild, str(payload.get("kind") or ""),
                           str(payload.get("pa_id") or ""))


@app.get("/v1/knowledge/jobs")
def knowledge_jobs(limit: int = 20):
    return {"jobs": store.list_jobs(limit=max(1, min(limit, 100)))}


@app.get("/v1/runs/{run_id}/citations")
def run_citations(run_id: str):
    _load_run_or_404(run_id)
    return {"citations": store.list_citations(run_id)}


@app.get("/v1/pa/calibration/corpus")
def calibration_corpus():
    """Two-gate corpus for the PC workbench.

    Phase-1 calibration is an internal readiness questionnaire, so the scenarios are
    returned together with their expected answers: the console fills them in and the
    *server* still computes the gates. If calibration ever becomes a security
    boundary, drop the expected answers from this response.
    """
    return {
        "decision": [scenario for scenario, _ in DECISION_CORPUS],
        "decision_expected": {scenario: expected for scenario, expected in DECISION_CORPUS},
        "alignment": [scenario for scenario, _ in ALIGNMENT_CORPUS],
        "alignment_expected_hint": {scenario: expected for scenario, expected in ALIGNMENT_CORPUS},
    }


@app.get("/v1/server/health")
def server_health():
    def probe(fn):
        try:
            fn()
            return "ok"
        except Exception:  # noqa: BLE001
            return "down"
    # Each probe must perform the same read-only call the run pipeline depends on,
    # otherwise the endpoint would report a green light it never verified.
    #
    # They run concurrently: sequentially this took 7.6-11.8s (measured), because
    # EMOS alone needs 4-9s, and any caller with an 8s budget - such as
    # scripts/check-all.ps1 - then reported the planner as down even though it
    # was healthy. Probe in parallel so the cost is the slowest dependency
    # rather than their sum.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "emos": pool.submit(probe, engine.emos.health) if engine.emos
            else None,
            "organizer": pool.submit(probe, engine.organizer.health) if engine.organizer
            else None,
            "knowledge": pool.submit(probe, lambda: engine.knowledge.search("health", per_page=1))
            if engine.knowledge else None,
            "observer": pool.submit(probe, engine.observer.health) if engine.observer
            else None,
        }
        results = {
            name: (future.result() if future else "off")
            for name, future in futures.items()
        }
    emos = results["emos"]
    org = results["organizer"]
    kn = results["knowledge"]
    obs = results["observer"]
    return {"status": "ok", "emos": emos, "organizer": org, "knowledge": kn,
            "observer": obs,
            "planner": engine.planner.name, "trace_id": "server"}
