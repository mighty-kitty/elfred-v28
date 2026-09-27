"""freetodo_client 单元测试 — InMemoryFreeTodoClient CRUD + 错误处理"""

from __future__ import annotations

import pytest

from adapter.freetodo_client import (
    FreeTodoClient,
    FreeTodoError,
    FreeTodoNotFound,
    InMemoryFreeTodoClient,
)


# ── InMemoryFreeTodoClient: Todos CRUD ──

def test_create_and_list_todos():
    client = InMemoryFreeTodoClient()
    client.create_todo({"name": "任务1", "status": "active"})
    client.create_todo({"name": "任务2", "status": "completed"})
    todos = client.list_todos()
    assert len(todos) == 2
    assert todos[0]["name"] == "任务1"


def test_get_todo():
    client = InMemoryFreeTodoClient()
    created = client.create_todo({"name": "test"})
    fetched = client.get_todo(created["id"])
    assert fetched["name"] == "test"


def test_update_todo():
    client = InMemoryFreeTodoClient()
    created = client.create_todo({"name": "old"})
    updated = client.update_todo(created["id"], {"name": "new"})
    assert updated["name"] == "new"


def test_delete_todo():
    client = InMemoryFreeTodoClient()
    created = client.create_todo({"name": "to_delete"})
    client.delete_todo(created["id"])
    assert len(client.list_todos()) == 0


def test_get_missing_todo_raises():
    client = InMemoryFreeTodoClient()
    with pytest.raises(FreeTodoNotFound):
        client.get_todo(9999)


def test_update_missing_todo_raises():
    client = InMemoryFreeTodoClient()
    with pytest.raises(FreeTodoNotFound):
        client.update_todo(9999, {"name": "x"})


# ── Journals CRUD ──

def test_create_and_list_journals():
    client = InMemoryFreeTodoClient()
    client.create_journal({"name": "日报", "date": "2026-07-31"})
    journals = client.list_journals()
    assert len(journals) == 1
    assert journals[0]["name"] == "日报"


def test_http_client_reads_every_journal_page():
    client = FreeTodoClient("http://freetodo.test")
    journals = [{"id": index + 1, "uid": f"journal-{index + 1}"} for index in range(2505)]
    requested_offsets: list[int] = []

    def fake_request(method, path, payload=None):
        assert method == "GET"
        query = path.split("?", 1)[1]
        parts = dict(item.split("=", 1) for item in query.split("&"))
        limit = int(parts["limit"])
        offset = int(parts["offset"])
        requested_offsets.append(offset)
        return {
            "total": len(journals),
            "journals": journals[offset:offset + limit],
        }

    client._request = fake_request  # type: ignore[method-assign]

    assert client.list_journals() == journals
    assert requested_offsets == [0, 1000, 2000]


def test_http_client_rejects_overlapping_incomplete_journal_pages():
    client = FreeTodoClient("http://freetodo.test")

    def fake_request(method, path, payload=None):
        offset = int(path.rsplit("offset=", 1)[1])
        indexes = range(1000) if offset == 0 else range(999, 1499)
        return {
            "total": 1500,
            "journals": [{"id": index + 1} for index in indexes],
        }

    client._request = fake_request  # type: ignore[method-assign]

    with pytest.raises(FreeTodoError, match="incomplete journals"):
        client.list_journals()


def test_http_client_uses_uid_endpoint_for_lookup_and_upsert():
    client = FreeTodoClient("http://freetodo.test")
    requests = []

    def fake_request(method, path, payload=None):
        requests.append((method, path, payload))
        return {"id": 7, "uid": "task/with spaces", **(payload or {})}

    client._request = fake_request  # type: ignore[method-assign]

    found = client.find_todo_by_uid("task/with spaces")
    upserted = client.upsert_todo("task/with spaces", {"name": "Task"})

    assert found["uid"] == "task/with spaces"
    assert upserted["name"] == "Task"
    assert requests == [
        ("GET", "/api/todos/by-uid/task%2Fwith%20spaces", None),
        (
            "PUT",
            "/api/todos/by-uid/task%2Fwith%20spaces",
            {"name": "Task", "uid": "task/with spaces"},
        ),
    ]


def test_in_memory_uid_upsert_is_idempotent():
    client = InMemoryFreeTodoClient()

    first = client.upsert_todo("task-1", {"name": "First"})
    second = client.upsert_todo("task-1", {"name": "Second"})

    assert first["id"] == second["id"]
    assert len(client.todos) == 1
    assert second["name"] == "Second"


def test_update_journal():
    client = InMemoryFreeTodoClient()
    created = client.create_journal({"name": "old"})
    updated = client.update_journal(created["id"], {"name": "new"})
    assert updated["name"] == "new"


# ── Availability ──

def test_availability_toggle():
    client = InMemoryFreeTodoClient()
    client.create_todo({"name": "x"})  # works
    client.available = False
    with pytest.raises(FreeTodoError, match="unavailable"):
        client.create_todo({"name": "y"})


# ── Thread safety ──

def test_concurrent_creates_unique_ids():
    import threading

    client = InMemoryFreeTodoClient()

    def create():
        for _ in range(10):
            client.create_todo({"name": "t"})

    threads = [threading.Thread(target=create) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    todos = client.list_todos()
    ids = {t["id"] for t in todos}
    assert len(ids) == 50  # 5 threads × 10 = 50 unique IDs
    assert len(todos) == 50


# ── FreeTodoError hierarchy ──

def test_freetodo_error_with_status():
    err = FreeTodoError("msg", status_code=503)
    assert err.status_code == 503
    assert "msg" in str(err)


def test_freetodo_not_found_is_freetodo_error():
    err = FreeTodoNotFound("gone")
    assert isinstance(err, FreeTodoError)
    assert isinstance(err, FreeTodoNotFound)
