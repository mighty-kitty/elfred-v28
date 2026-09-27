# -*- coding: utf-8 -*-
"""SQLite store (stdlib sqlite3).

The run worker threads and the API threads share one connection, so *every*
method that touches the connection holds the lock. sqlite3 objects are not
thread-safe; without this guard concurrent access raises InterfaceError /
"cannot commit - no transaction is active".
"""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
import uuid
from .models import PAProfile, Run, Session, Feedback, PAState, RunState

DB_PATH = os.environ.get("PA_GATEWAY_DB", "pa-gateway.db")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class DbStore:
    """Persistent store. sqlite3 row_factory = dict."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or DB_PATH
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS profiles (
                    pa_id TEXT PRIMARY KEY, user_id TEXT, letta_agent_id TEXT,
                    profile_version INTEGER, state TEXT, persona TEXT, preferences TEXT,
                    boundaries TEXT, knowledge_sources TEXT, tool_scopes TEXT,
                    emos_profile_ref TEXT, consent_version INTEGER,
                    created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, pa_id TEXT, state TEXT, query_summary TEXT,
                    context_refs TEXT, plan TEXT, artifacts TEXT, events TEXT,
                    tool_calls TEXT, approval TEXT, paused INTEGER, parent_run_id TEXT,
                    seq INTEGER,
                    created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY, resource_type TEXT, resource_id TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS calibrations (
                    pa_id TEXT PRIMARY KEY, responses TEXT, gates TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, pa_id TEXT, status TEXT, run_id TEXT,
                    devices TEXT, created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY, run_id TEXT, pa_id TEXT, decision TEXT,
                    comment TEXT, emos TEXT, skill TEXT, degraded TEXT,
                    revision_run_id TEXT, created_at TEXT)"""
            )
            # WP-07 knowledge layer: a real pipeline needs the source of every
            # citation, so the document/chunk/job chain is persisted, not implied.
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_sources (
                    source_id TEXT PRIMARY KEY, name TEXT, kind TEXT, pa_id TEXT,
                    collection TEXT, status TEXT, created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY, source_id TEXT, title TEXT, path TEXT,
                    mime TEXT, bytes INTEGER, checksum TEXT, status TEXT, error TEXT,
                    chunk_count INTEGER, created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY, document_id TEXT, ordinal INTEGER,
                    text TEXT, page INTEGER, token_estimate INTEGER, created_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_jobs (
                    job_id TEXT PRIMARY KEY, kind TEXT, document_id TEXT, source_id TEXT,
                    state TEXT, detail TEXT, created_at TEXT, updated_at TEXT)"""
            )
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_citations (
                    citation_id TEXT PRIMARY KEY, run_id TEXT, pa_id TEXT,
                    document_id TEXT, chunk_id TEXT, quote TEXT, created_at TEXT)"""
            )
            # Widen older databases: a missing column silently dropped `paused`,
            # which made pause/resume look like it worked while changing nothing.
            run_columns = {row["name"] for row in
                           self.conn.execute("PRAGMA table_info(runs)").fetchall()}
            if "paused" not in run_columns:
                self.conn.execute("ALTER TABLE runs ADD COLUMN paused INTEGER DEFAULT 0")
            if "parent_run_id" not in run_columns:
                self.conn.execute("ALTER TABLE runs ADD COLUMN parent_run_id TEXT")
            self.conn.commit()

    # --- idempotency ---
    def get_idempotent(self, key: str):
        with self._lock:
            row = self.conn.execute("SELECT * FROM idempotency WHERE key=?", (key,)).fetchone()
            return dict(row) if row else None

    def set_idempotent(self, key: str, resource_type: str, resource_id: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO idempotency(key,resource_type,resource_id) VALUES(?,?,?)",
                              (key, resource_type, resource_id))
            self.conn.commit()

    # --- profiles ---
    def create_profile(self, user_id: str, **kw) -> PAProfile:
        with self._lock:
            # A millisecond clock alone can collide under load and silently
            # overwrite another resource, so ids carry a random suffix.
            pa_id = kw.pop("pa_id", None) or f"pa_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
            p = PAProfile(pa_id=pa_id, user_id=user_id, created_at=_now(), updated_at=_now(), **kw)
            self.conn.execute(
                "INSERT INTO profiles(pa_id,user_id,letta_agent_id,profile_version,state,persona,preferences,"
                "boundaries,knowledge_sources,tool_scopes,emos_profile_ref,consent_version,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.pa_id, p.user_id, p.letta_agent_id, p.profile_version, p.state.value,
                 json.dumps(p.persona), json.dumps(p.preferences), json.dumps(p.boundaries),
                 json.dumps(p.knowledge_sources), json.dumps(p.tool_scopes), p.emos_profile_ref,
                 p.consent_version, p.created_at, p.updated_at))
            self.conn.commit()
            return p

    def get_profile(self, pa_id: str) -> PAProfile | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM profiles WHERE pa_id=?", (pa_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["state"] = PAState(d["state"])
            for key in ("persona", "preferences", "boundaries", "knowledge_sources", "tool_scopes"):
                if key in ("knowledge_sources", "tool_scopes"):
                    d[key] = json.loads(d[key] or "[]")
                else:
                    d[key] = json.loads(d[key] or "{}")
            return PAProfile(**d)

    def most_recent_profile(self) -> PAProfile | None:
        """The PA this gateway last worked on.

        The frontend has no way to discover a pa_id by itself (there is no list
        endpoint), yet every read it needs - memory, readiness - is keyed by one.
        Rather than invent an id, resolve the most recently updated profile and
        report it as the current one.

        Profiles still sitting in onboarding are placeholders created by tests and
        by repeated initialisation; a PA the user actually worked on comes first,
        so the memory and readiness views do not open on an empty shell when a
        real one exists.
        """
        with self._lock:
            row = self.conn.execute(
                "SELECT pa_id FROM profiles "
                "ORDER BY CASE state "
                "  WHEN 'active' THEN 0 WHEN 'trial_ready' THEN 1 "
                "  WHEN 'calibrating' THEN 2 ELSE 3 END, "
                "updated_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return self.get_profile(row["pa_id"])

    def save_profile(self, p: PAProfile) -> PAProfile:
        with self._lock:
            p.updated_at = _now()
            self.conn.execute(
                "UPDATE profiles SET state=?,consent_version=?,letta_agent_id=?,profile_version=?,"
                "persona=?,preferences=?,boundaries=?,knowledge_sources=?,tool_scopes=?,"
                "emos_profile_ref=?,updated_at=? WHERE pa_id=?",
                (p.state.value, p.consent_version, p.letta_agent_id, p.profile_version,
                 json.dumps(p.persona), json.dumps(p.preferences), json.dumps(p.boundaries),
                 json.dumps(p.knowledge_sources), json.dumps(p.tool_scopes),
                 p.emos_profile_ref, p.updated_at, p.pa_id))
            self.conn.commit()
            return p

    # --- runs ---
    def create_run(self, pa_id: str, query: str) -> Run:
        run_id = f"run_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        r = Run(run_id=run_id, pa_id=pa_id, query_summary=query, created_at=_now(), updated_at=_now())
        self.save_run(r)
        return r

    def _row_to_run(self, row) -> Run:
        d = dict(row)
        for key in ("context_refs", "plan", "artifacts", "events", "tool_calls"):
            d[key] = json.loads(d[key] or "[]")
        d["approval"] = json.loads(d["approval"]) if d["approval"] else None
        d["paused"] = bool(d.get("paused"))
        return Run(**d)

    def save_run(self, run: Run) -> Run:
        with self._lock:
            run.updated_at = _now()
            # `paused` is owned by pause/resume (set_run_paused). A worker saving a
            # stale copy of the run must not clear a flag the user just set, so the
            # persisted value wins over whatever this in-memory copy believes.
            row = self.conn.execute("SELECT paused, state FROM runs WHERE run_id=?",
                                    (run.run_id,)).fetchone()
            preserved = (int(row["paused"]) if row and row["paused"] is not None
                         else int(bool(run.paused)))
            run.paused = bool(preserved)
            # A user-issued cancel is authoritative: a worker that is mid-step holds a
            # stale copy of the run and must not resurrect it by saving "executing".
            if (row and row["state"] == RunState.cancelled.value
                    and run.state not in (RunState.cancelled, RunState.completed, RunState.failed)):
                run.state = RunState.cancelled
            self.conn.execute(
                "INSERT OR REPLACE INTO runs(run_id,pa_id,state,query_summary,context_refs,plan,artifacts,events,"
                "tool_calls,approval,paused,parent_run_id,seq,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.pa_id, run.state.value, run.query_summary,
                 json.dumps(run.context_refs), json.dumps(run.plan), json.dumps(run.artifacts),
                 json.dumps([e.model_dump() if hasattr(e, "model_dump") else e for e in run.events]),
                 json.dumps([t.model_dump() if hasattr(t, "model_dump") else t for t in run.tool_calls]),
                 json.dumps(run.approval) if run.approval else None, preserved,
                 run.parent_run_id, run.seq,
                 run.created_at, run.updated_at))
            self.conn.commit()
        return run

    def set_run_paused(self, run_id: str, paused: bool) -> None:
        """The single writer of the pause flag (see save_run)."""
        with self._lock:
            self.conn.execute("UPDATE runs SET paused=?, updated_at=? WHERE run_id=?",
                              (int(bool(paused)), _now(), run_id))
            self.conn.commit()

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return self._row_to_run(row) if row else None

    def read_run_unlocked(self, run_id: str) -> Run | None:
        """Read a run without taking the writer's lock.

        The SSE stream opens the moment a run is created, which is exactly when
        the creating thread is writing events. Sharing one in-process lock made
        the first paint of the stream wait ~1s behind that writer; WAL allows an
        independent reader, so the stream reads on its own connection. Anything
        unexpected falls back to the locked read rather than failing the stream.
        """
        try:
            uri = f"file:{self.path}?mode=ro"
            if not os.path.isfile(self.path):
                return self.get_run(run_id)
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=5.0)
        except sqlite3.Error:
            return self.get_run(run_id)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return self._row_to_run(row) if row else None
        except sqlite3.Error:
            return self.get_run(run_id)
        finally:
            conn.close()

    def runs_by_state(self, states: list[str]) -> list[Run]:
        if not states:
            return []
        placeholders = ",".join("?" for _ in states)
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM runs WHERE state IN ({placeholders}) ORDER BY created_at",
                tuple(states)).fetchall()
            return [self._row_to_run(row) for row in rows]

    def delete_run(self, run_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
            self.conn.commit()

    # --- calibration ---
    def set_calibration(self, pa_id: str, responses: dict, gates: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO calibrations(pa_id,responses,gates,updated_at) VALUES(?,?,?,?)",
                (pa_id, json.dumps(responses), json.dumps(gates), _now()))
            self.conn.commit()

    def get_calibration(self, pa_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT responses,gates FROM calibrations WHERE pa_id=?", (pa_id,)).fetchone()
            if not row:
                return None
            return {"responses": json.loads(row["responses"]), "gates": json.loads(row["gates"])}

    # --- sessions (cross-device pairing, book 6.1) ---
    def save_session(self, session: Session) -> Session:
        with self._lock:
            session.updated_at = _now()
            self.conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id,pa_id,status,run_id,devices,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (session.session_id, session.pa_id, session.status, session.run_id,
                 json.dumps(session.devices), session.created_at, session.updated_at))
            self.conn.commit()
        return session

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM sessions WHERE session_id=?",
                                    (session_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["devices"] = json.loads(data["devices"] or "[]")
            return Session(**data)

    # --- feedback + revision lineage (book WP-09) ---
    def add_feedback(self, feedback: Feedback) -> Feedback:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO feedback(feedback_id,run_id,pa_id,decision,comment,"
                "emos,skill,degraded,revision_run_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (feedback.feedback_id, feedback.run_id, feedback.pa_id, feedback.decision,
                 feedback.comment, json.dumps(feedback.emos), json.dumps(feedback.skill),
                 json.dumps(feedback.degraded), feedback.revision_run_id,
                 feedback.created_at or _now()))
            self.conn.commit()
        return feedback

    def list_feedback(self, run_id: str) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM feedback WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
            out = []
            for row in rows:
                data = dict(row)
                for key in ("emos", "skill", "degraded"):
                    data[key] = json.loads(data[key] or "[]")
                out.append(data)
            return out

    def list_child_runs(self, run_id: str) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT run_id,state,query_summary,created_at FROM runs WHERE parent_run_id=?"
                " ORDER BY created_at", (run_id,)).fetchall()
            return [dict(row) for row in rows]

    # --- knowledge layer (WP-07) ---
    def create_source(self, name: str, kind: str, pa_id: str = "", collection: str = "") -> dict:
        source_id = f"ksrc_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self.conn.execute(
                "INSERT INTO knowledge_sources(source_id,name,kind,pa_id,collection,status,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (source_id, name, kind, pa_id, collection, "active", _now(), _now()))
            self.conn.commit()
        return self.get_source(source_id)

    def get_source(self, source_id: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM knowledge_sources WHERE source_id=?", (source_id,)).fetchone()
            return dict(row) if row else None

    def list_sources(self, kind: str = "", pa_id: str = "") -> list:
        sql = "SELECT * FROM knowledge_sources WHERE 1=1"
        args: list = []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        if pa_id:
            sql += " AND pa_id=?"
            args.append(pa_id)
        sql += " ORDER BY created_at"
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def create_document(self, source_id: str, title: str, path: str, mime: str = "",
                        size: int = 0, checksum: str = "") -> dict:
        document_id = f"kdoc_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self.conn.execute(
                "INSERT INTO knowledge_documents(document_id,source_id,title,path,mime,bytes,"
                "checksum,status,error,chunk_count,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (document_id, source_id, title, path, mime, size, checksum, "pending",
                 "", 0, _now(), _now()))
            self.conn.commit()
        return self.get_document(document_id)

    def get_document(self, document_id: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM knowledge_documents WHERE document_id=?", (document_id,)).fetchone()
            return dict(row) if row else None

    def list_documents(self, source_id: str = "", status: str = "") -> list:
        sql = "SELECT * FROM knowledge_documents WHERE 1=1"
        args: list = []
        if source_id:
            sql += " AND source_id=?"
            args.append(source_id)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at"
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def update_document(self, document_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        columns = ",".join(f"{k}=?" for k in fields)
        with self._lock:
            self.conn.execute(f"UPDATE knowledge_documents SET {columns} WHERE document_id=?",
                              (*fields.values(), document_id))
            self.conn.commit()

    def delete_document(self, document_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM knowledge_chunks WHERE document_id=?", (document_id,))
            self.conn.execute("DELETE FROM knowledge_documents WHERE document_id=?", (document_id,))
            self.conn.commit()

    def replace_chunks(self, document_id: str, chunks: list) -> list:
        """Chunk ids are derived from the document so re-indexing stays idempotent."""
        with self._lock:
            self.conn.execute("DELETE FROM knowledge_chunks WHERE document_id=?", (document_id,))
            rows = []
            for ordinal, chunk in enumerate(chunks):
                chunk_id = f"{document_id}::c{ordinal}"
                self.conn.execute(
                    "INSERT INTO knowledge_chunks(chunk_id,document_id,ordinal,text,page,"
                    "token_estimate,created_at) VALUES(?,?,?,?,?,?,?)",
                    (chunk_id, document_id, ordinal, chunk["text"], int(chunk.get("page") or 0),
                     int(chunk.get("token_estimate") or 0), _now()))
                rows.append({"chunk_id": chunk_id, "ordinal": ordinal,
                             "text": chunk["text"], "page": int(chunk.get("page") or 0),
                             "token_estimate": int(chunk.get("token_estimate") or 0)})
            self.conn.commit()
            return rows

    def list_chunks(self, document_id: str) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM knowledge_chunks WHERE document_id=? ORDER BY ordinal",
                (document_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_job(self, kind: str, document_id: str = "", source_id: str = "",
                state: str = "queued", detail: str = "") -> dict:
        job_id = f"kjob_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self.conn.execute(
                "INSERT INTO knowledge_jobs(job_id,kind,document_id,source_id,state,detail,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, kind, document_id, source_id, state, detail, _now(), _now()))
            self.conn.commit()
        return self.get_job(job_id)

    def update_job(self, job_id: str, state: str, detail: str = "") -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE knowledge_jobs SET state=?, detail=?, updated_at=? WHERE job_id=?",
                (state, detail, _now(), job_id))
            self.conn.commit()

    def get_job(self, job_id: str):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM knowledge_jobs WHERE job_id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list:
        with self._lock:
            rows = self.conn.execute(
                # created_at has second resolution, so rowid breaks ties and keeps
                # "the newest job" deterministic within the same second.
                "SELECT * FROM knowledge_jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]

    def add_citation(self, run_id: str, pa_id: str, document_id: str, chunk_id: str,
                     quote: str = "") -> dict:
        # The context builder and the knowledge tool can both cite the same chunk;
        # one run cites a passage once.
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM knowledge_citations WHERE run_id=? AND chunk_id=?",
                (run_id, chunk_id)).fetchone()
            if row:
                return dict(row)
        citation_id = f"kcite_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self.conn.execute(
                "INSERT INTO knowledge_citations(citation_id,run_id,pa_id,document_id,chunk_id,"
                "quote,created_at) VALUES(?,?,?,?,?,?,?)",
                (citation_id, run_id, pa_id, document_id, chunk_id, quote[:400], _now()))
            self.conn.commit()
        return {"citation_id": citation_id, "document_id": document_id,
                "chunk_id": chunk_id}

    def list_citations(self, run_id: str) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM knowledge_citations WHERE run_id=? ORDER BY created_at",
                (run_id,)).fetchall()
            return [dict(r) for r in rows]
