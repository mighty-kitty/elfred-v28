from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from typing import Any


class FreeTodoError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FreeTodoNotFound(FreeTodoError):
    pass


class FreeTodoClient:
    _PAGE_SIZE = 1000
    _MAX_PAGES = 10000

    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return json.loads(body.decode("utf-8")) if body else None
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 404:
                raise FreeTodoNotFound(body or "not found", error.code) from error
            raise FreeTodoError(f"FreeTodo HTTP {error.code}: {body}", error.code) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise FreeTodoError(f"FreeTodo unavailable: {error}") from error

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_todos(self) -> list[dict[str, Any]]:
        return self._list_all("/api/todos", "todos")

    def find_todo_by_uid(self, uid: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(str(uid), safe="")
        try:
            return self._request("GET", f"/api/todos/by-uid/{encoded}")
        except FreeTodoNotFound:
            return None

    def upsert_todo(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.quote(str(uid), safe="")
        body = {**payload, "uid": uid}
        return self._request("PUT", f"/api/todos/by-uid/{encoded}", body)

    def create_todo(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/todos", payload)

    def get_todo(self, todo_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/todos/{todo_id}")

    def update_todo(self, todo_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/todos/{todo_id}", payload)

    def delete_todo(self, todo_id: int) -> None:
        self._request("DELETE", f"/api/todos/{todo_id}")

    def list_journals(self) -> list[dict[str, Any]]:
        return self._list_all("/api/journals", "journals")

    def find_journal_by_uid(self, uid: str) -> dict[str, Any] | None:
        return next((item for item in self.list_journals() if item.get("uid") == uid), None)

    def create_journal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/journals", payload)

    def get_journal(self, journal_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/journals/{journal_id}")

    def update_journal(self, journal_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/journals/{journal_id}", payload)

    def delete_journal(self, journal_id: int) -> None:
        self._request("DELETE", f"/api/journals/{journal_id}")

    def _list_all(self, path: str, collection_name: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        offset = 0
        expected_total: int | None = None

        for _ in range(self._MAX_PAGES):
            separator = "&" if "?" in path else "?"
            response = self._request(
                "GET",
                f"{path}{separator}limit={self._PAGE_SIZE}&offset={offset}",
            )
            if not isinstance(response, dict):
                if offset == 0:
                    return list(response or [])
                raise FreeTodoError(
                    f"FreeTodo returned an invalid {collection_name} page"
                )

            page = response.get(collection_name)
            if not isinstance(page, list):
                raise FreeTodoError(
                    f"FreeTodo returned an invalid {collection_name} page"
                )
            reported_total = response.get("total")
            if isinstance(reported_total, int) and reported_total >= 0:
                expected_total = reported_total

            for item in page:
                if not isinstance(item, dict):
                    raise FreeTodoError(
                        f"FreeTodo returned an invalid {collection_name} item"
                    )
                item_id = item.get("id")
                identity = str(item_id) if item_id is not None else None
                if identity is not None and identity in seen_ids:
                    continue
                if identity is not None:
                    seen_ids.add(identity)
                items.append(item)

            offset += len(page)
            reached_total = expected_total is not None and offset >= expected_total
            reached_end = len(page) < self._PAGE_SIZE
            if reached_total or reached_end:
                if expected_total is not None and len(items) < expected_total:
                    raise FreeTodoError(
                        f"FreeTodo returned an incomplete {collection_name} collection"
                    )
                return items

        raise FreeTodoError(
            f"FreeTodo {collection_name} pagination exceeded the safety limit"
        )


class InMemoryFreeTodoClient(FreeTodoClient):
    """Deterministic, thread-safe fake used by tests and the offline demo."""

    def __init__(self) -> None:
        self.todos: dict[int, dict[str, Any]] = {}
        self.journals: dict[int, dict[str, Any]] = {}
        self._next_todo = 1
        self._next_journal = 1
        self.available = True
        self.calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def _check(self) -> None:
        if not self.available:
            raise FreeTodoError("FreeTodo unavailable: test switch")

    def health(self) -> dict[str, Any]:
        self._check()
        return {"status": "healthy", "database": "connected", "app": "in-memory-freetodo"}

    def list_todos(self) -> list[dict[str, Any]]:
        self._check()
        return deepcopy(list(self.todos.values()))

    def create_todo(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._check()
        self.calls.append(("POST", "/api/todos"))
        with self._lock:
            item = {"id": self._next_todo, **deepcopy(payload)}
            item.setdefault("uid", f"todo-{self._next_todo}")
            self.todos[self._next_todo] = item
            self._next_todo += 1
        return deepcopy(item)

    def find_todo_by_uid(self, uid: str) -> dict[str, Any] | None:
        self._check()
        return next(
            (deepcopy(item) for item in self.todos.values() if item.get("uid") == uid),
            None,
        )

    def upsert_todo(self, uid: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._check()
        existing = self.find_todo_by_uid(uid)
        if existing is None:
            return self.create_todo({**payload, "uid": uid})
        return self.update_todo(int(existing["id"]), {**payload, "uid": uid})

    def get_todo(self, todo_id: int) -> dict[str, Any]:
        self._check()
        if todo_id not in self.todos:
            raise FreeTodoNotFound("todo not found", 404)
        return deepcopy(self.todos[todo_id])

    def update_todo(self, todo_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._check()
        if todo_id not in self.todos:
            raise FreeTodoNotFound("todo not found", 404)
        self.calls.append(("PUT", f"/api/todos/{todo_id}"))
        self.todos[todo_id].update(deepcopy(payload))
        return deepcopy(self.todos[todo_id])

    def delete_todo(self, todo_id: int) -> None:
        self._check()
        if todo_id not in self.todos:
            raise FreeTodoNotFound("todo not found", 404)
        self.calls.append(("DELETE", f"/api/todos/{todo_id}"))
        del self.todos[todo_id]

    def list_journals(self) -> list[dict[str, Any]]:
        self._check()
        return deepcopy(list(self.journals.values()))

    def create_journal(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._check()
        self.calls.append(("POST", "/api/journals"))
        with self._lock:
            item = {"id": self._next_journal, **deepcopy(payload)}
            item.setdefault("uid", f"journal-{self._next_journal}")
            self.journals[self._next_journal] = item
            self._next_journal += 1
        return deepcopy(item)

    def get_journal(self, journal_id: int) -> dict[str, Any]:
        self._check()
        if journal_id not in self.journals:
            raise FreeTodoNotFound("journal not found", 404)
        return deepcopy(self.journals[journal_id])

    def update_journal(self, journal_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._check()
        if journal_id not in self.journals:
            raise FreeTodoNotFound("journal not found", 404)
        self.calls.append(("PUT", f"/api/journals/{journal_id}"))
        self.journals[journal_id].update(deepcopy(payload))
        return deepcopy(self.journals[journal_id])

    def delete_journal(self, journal_id: int) -> None:
        self._check()
        if journal_id not in self.journals:
            raise FreeTodoNotFound("journal not found", 404)
        self.calls.append(("DELETE", f"/api/journals/{journal_id}"))
        del self.journals[journal_id]
