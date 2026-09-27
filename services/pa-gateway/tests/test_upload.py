# -*- coding: utf-8 -*-
"""WP-07 upload entry: validation, storage and hand-off to the ingest pipeline."""
import os

import pytest

import app.knowledge as knowledge_mod
import app.main as main_mod
from fastapi.testclient import TestClient

from app.knowledge import KnowledgeError, safe_filename, store_upload
from app.main import app

c = TestClient(app)


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_UPLOAD_DIR", str(tmp_path))
    return tmp_path


def test_safe_filename_strips_any_path():
    assert safe_filename("..\\..\\Windows\\system32\\evil.md") == "evil.md"
    assert safe_filename("/etc/passwd.md") == "passwd.md"
    assert safe_filename("报告 2026.md") == "报告 2026.md"
    with pytest.raises(KnowledgeError):
        safe_filename("..")


def test_upload_is_written_under_the_pa_directory(uploads):
    path = store_upload("pa_demo", "notes.md", "北极星目标".encode("utf-8"))
    assert os.path.isfile(path)
    assert "pa_demo" in path.replace("/", os.sep)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == "北极星目标"


def test_upload_refuses_an_unsupported_extension(uploads):
    with pytest.raises(KnowledgeError) as exc:
        store_upload("pa_demo", "payload.exe", b"MZ")
    assert exc.value.code == "UNSUPPORTED_FORMAT"
    assert not list(uploads.rglob("*.exe")), "nothing may be written for a rejected upload"


def test_upload_refuses_an_empty_body(uploads):
    with pytest.raises(KnowledgeError) as exc:
        store_upload("pa_demo", "empty.md", b"")
    assert exc.value.code == "EMPTY_DOCUMENT"


def test_upload_refuses_an_oversized_body(uploads, monkeypatch):
    monkeypatch.setattr(knowledge_mod, "MAX_UPLOAD_BYTES", 16)
    with pytest.raises(KnowledgeError) as exc:
        store_upload("pa_demo", "big.md", b"x" * 17)
    assert exc.value.code == "FILE_TOO_LARGE"
    assert not list(uploads.rglob("big.md"))


def test_endpoint_hands_the_stored_path_to_the_pipeline(uploads, monkeypatch):
    seen = {}

    def fake_ingest(path, **kw):
        seen["path"] = path
        seen.update(kw)
        return {"document": {"document_id": "kdoc_1", "status": "indexed"},
                "chunks": 2, "indexed": 2, "job_id": "kjob_1"}

    monkeypatch.setattr(main_mod.knowledge_service, "ingest", fake_ingest)
    response = c.post("/v1/knowledge/uploads",
                      files={"file": ("blueprint.md", "北极星目标".encode("utf-8"),
                                      "text/markdown")},
                      data={"pa_id": "pa_upload", "title": "上传蓝图",
                            "kind": "personal", "source_name": "upload-test"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document"]["status"] == "indexed" and body["bytes"] == len("北极星目标".encode())
    assert seen["pa_id"] == "pa_upload" and seen["title"] == "上传蓝图"
    assert os.path.isfile(seen["path"]) and seen["path"].startswith(str(uploads))


def test_endpoint_surfaces_a_named_rejection(uploads, monkeypatch):
    monkeypatch.setattr(main_mod.knowledge_service, "ingest",
                        lambda path, **kw: {"document": {}})
    response = c.post("/v1/knowledge/uploads",
                      files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
                      data={"pa_id": "pa_upload"})
    assert response.status_code == 422
    assert "UNSUPPORTED_FORMAT" in response.text


def test_endpoint_works_without_a_pa_but_keeps_files_separate(uploads, monkeypatch):
    monkeypatch.setattr(main_mod.knowledge_service, "ingest",
                        lambda path, **kw: {"document": {"document_id": "kdoc_2"},
                                            "chunks": 1})
    response = c.post("/v1/knowledge/uploads",
                      files={"file": ("note.txt", b"hello", "text/plain")})
    assert response.status_code == 200
    assert "unscoped" in response.json()["stored_path"].replace("/", os.sep)
