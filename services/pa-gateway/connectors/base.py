# -*- coding: utf-8 -*-
import os
import httpx

from app.tracing import trace_headers


def _u(env: str, default: str) -> str:
    return os.environ.get(env, default)


class BaseClient:
    base_url: str = ""
    TIMEOUT = 8.0

    def _get(self, path: str, params=None, headers=None):
        with httpx.Client(base_url=self.base_url, timeout=self.TIMEOUT) as c:
            r = c.get(path, params=params, headers={**(headers or {}), **trace_headers()})
            r.raise_for_status()
            return r.json()

    def _post(self, path: str, json=None):
        with httpx.Client(base_url=self.base_url, timeout=self.TIMEOUT) as c:
            r = c.post(path, json=json, headers=trace_headers())
            r.raise_for_status()
            return r.json()

    def _delete(self, path: str):
        with httpx.Client(base_url=self.base_url, timeout=self.TIMEOUT) as c:
            r = c.delete(path, headers=trace_headers())
            r.raise_for_status()
            return r.json()


class EmosClient(BaseClient):
    def __init__(self):
        self.base_url = _u("EMOS_URL", "http://127.0.0.1:8000")

    def health(self):
        return self._get("/health")

    def recall(self, user_id: str, query_text: str, **kw):
        return self._post("/memory/recall", {"user_id": user_id, "query_text": query_text, **kw})

    def memories(self, user_id: str, limit: int = 50):
        """Long-term memory rows for a PA (EMOS is the authority - ADR-002).

        Distinct from recall: this is the stored list, not a query-shaped
        retrieval, which is what the memory page needs to show.
        """
        return self._get("/memory/memories", params={"user_id": user_id, "limit": limit})

    def write(self, user_id: str, session_id: str, text: str, **kw):
        return self._post("/memory/write", {"user_id": user_id, "session_id": session_id, "text": text, **kw})

    def write_plan(self, user_id: str, session_id: str, text: str, **kw):
        return self._post("/memory/write-plan", {"user_id": user_id, "session_id": session_id, "text": text, **kw})

    def forget(self, user_id: str, session_id: str, memory_id: str, reason: str = "",
               source: str = "elfred-pa"):
        """Soft-forget with an auditable deletion receipt (EMOS /memory/forget)."""
        return self._post("/memory/forget", {
            "user_id": user_id, "session_id": session_id, "memory_id": memory_id,
            "reason": reason, "source": source,
        })

    def set_block(self, user_id: str, session_id: str, label: str, value: str,
                  description: str = "", read_only: bool = False,
                  source: str = "elfred-pa"):
        """Write a core memory block: the durable, always-on part of the profile."""
        return self._post("/memory/block", {
            "user_id": user_id, "session_id": session_id, "label": label, "value": value,
            "description": description, "read_only": read_only, "source": source,
        })

    def delete_block(self, user_id: str, session_id: str, label: str):
        return self._post("/memory/block/delete", {
            "user_id": user_id, "session_id": session_id, "label": label,
        })

    def system_report(self):
        """Which retrieval backend is actually serving recall, straight from EMOS."""
        return self._get("/system/report")

    def reflect(self, user_id: str, session_id: str | None = None, persist: bool = False):
        body = {"user_id": user_id}
        if session_id:
            body["session_id"] = session_id
        body["persist"] = persist
        return self._post("/memory/reflect", body)

    def supersede(self, user_id: str, session_id: str, source_memory_id: str,
                  replacement_memory_id: str, reason: str = ""):
        return self._post("/memory/supersede", {
            "user_id": user_id, "session_id": session_id,
            "source_memory_id": source_memory_id,
            "replacement_memory_id": replacement_memory_id,
            "reason": reason,
        })

    def update(self, user_id: str, session_id: str, memory_id: str, text: str):
        return self._post("/memory/update", {
            "user_id": user_id, "session_id": session_id,
            "memory_id": memory_id, "text": text,
        })

    def feedback(self, user_id: str, session_id: str, memory_id: str, feedback_type: str,
                 query_text: str | None = None, notes: str | None = None):
        """feedback_type is one of correct | incorrect | irrelevant (EMOS contract)."""
        return self._post("/memory/feedback", {
            "user_id": user_id, "session_id": session_id, "memory_id": memory_id,
            "feedback_type": feedback_type, "query_text": query_text, "notes": notes,
        })


class OrganizerClient(BaseClient):
    def __init__(self):
        self.base_url = _u("ORGANIZER_URL", "http://127.0.0.1:8770")

    def health(self):
        return self._get("/v1/health")

    def topics(self, limit: int = 5):
        return self._get("/v1/topics", params={"limit": limit})

    def events(self, limit: int = 5):
        return self._get("/v1/events", params={"limit": limit})


class KnowledgeClient(BaseClient):
    def __init__(self):
        self.base_url = _u("MOBILE_URL", "http://127.0.0.1:5173")

    def search(self, q: str, query_by: str = "title,summary", per_page: int = 5):
        return self._get("/api/search", params={"q": q, "query_by": query_by, "per_page": per_page})

    def assets(self, per_page: int = 20, page: int = 1):
        return self._get("/api/knowledge/assets", params={"per_page": per_page, "page": page})


class FreeTodoClient(BaseClient):
    """Task authority for Phase-1: the FreeTodo-compatible task host (:8001)."""

    def __init__(self):
        self.base_url = _u("TASK_HOST_URL", _u("FREETODO_URL", "http://127.0.0.1:8001"))

    def health(self):
        return self._get("/health")

    def list_todos(self, status: str | None = None):
        params = {"status": status} if status else None
        return self._get("/api/todos", params=params)

    def get_todo(self, todo_id: int):
        return self._get(f"/api/todos/{todo_id}")

    def find_by_uid(self, uid: str):
        return self._get(f"/api/todos/by-uid/{uid}")

    def create_todo(self, payload: dict, idempotency_key: str | None = None):
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        with httpx.Client(base_url=self.base_url, timeout=self.TIMEOUT) as c:
            r = c.post("/api/todos", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()

    def update_todo(self, todo_id: int, payload: dict):
        return self._put(f"/api/todos/{todo_id}", payload)

    def _put(self, path: str, json=None):
        with httpx.Client(base_url=self.base_url, timeout=self.TIMEOUT) as c:
            r = c.put(path, json=json)
            r.raise_for_status()
            return r.json()


class SkillClient(BaseClient):
    """Skill Foundry lives in the FreeTodo adapter (:8765)."""

    def __init__(self):
        self.base_url = _u("SKILL_URL", "http://127.0.0.1:8765")

    def health(self):
        return self._get("/v1/elfred/health")

    def match(self, task_context: dict):
        return self._post("/v1/elfred/skills/match", task_context)

    def list_skills(self):
        return self._get("/v1/elfred/skills")

    def approve(self, skill_id: str, allow_heuristic: bool = True):
        return self._post(f"/v1/elfred/skills/{skill_id}/approve",
                          {"allowHeuristic": allow_heuristic})

    def run(self, skill_id: str, inputs: dict | None = None, task_context: dict | None = None):
        return self._post(f"/v1/elfred/skills/{skill_id}/run",
                          {"inputs": inputs or {}, "taskContext": task_context or {}})

    def runs(self):
        return self._get("/v1/elfred/skill-runs")

    def feedback(self, skill_run_id: str, rating=None, outcome=None, comment=None):
        return self._post(f"/v1/elfred/skill-runs/{skill_run_id}/feedback",
                          {"rating": rating, "outcome": outcome, "comment": comment,
                           "corrections": []})


class LettaClient(BaseClient):
    """Local Letta App Server (WP-01). Each agent is exposed as an OpenAI model."""

    def __init__(self):
        self.base_url = _u("LETTA_URL", "http://127.0.0.1:4500")
        self.api_key = _u("LETTA_API_KEY", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def models(self):
        return self._get("/v1/models", headers=self._headers())


class ObserverClient(BaseClient):
    """Elfred Desktop Observer (:8781) - the desktop intake layer.

    Only the Observer looks at the screen; it already decides per capture whether
    a screenshot may be taken and flags sensitive scenes. The gateway reads what
    the Observer recorded and applies its own gate before anything reaches a
    model (WP-05).
    """

    def __init__(self):
        self.base_url = _u("OBSERVER_URL", "http://127.0.0.1:8781")

    def health(self):
        return self._get("/health")

    def recent_events(self, limit: int = 10):
        return self._get("/events/recent", params={"limit": limit})

    def event(self, event_id: str):
        return self._get(f"/events/{event_id}")

    def delete_event(self, event_id: str):
        return self._delete(f"/events/{event_id}")

    def current_context(self):
        return self._get("/context/current")

    def outbox(self, status: str = ""):
        return self._get("/outbox", params={"status": status or None})

    def mark_outbox_sent(self, item_id: str):
        return self._post(f"/outbox/{item_id}/mark-sent")

    def delete_app_data(self, app_name: str):
        return self._post("/privacy/delete-app-data", {"app_name": app_name})

    def clear_temporary_context(self):
        return self._post("/privacy/clear-temporary-context")
