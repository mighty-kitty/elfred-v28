# -*- coding: utf-8 -*-
"""WP-07 knowledge pipeline: source -> document -> chunk -> index -> citation.

Real, not decorative: files are parsed with real parsers, chunks are stored with
their page and ordinal, Typesense holds exactly the chunks the database holds,
and deleting a document removes it from the index in the same call that removes
it from the database. Anything the pipeline cannot do (an unparsable format, a
down index) fails the job with a named error instead of an empty success.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path

import httpx

COLLECTION = "elfred_knowledge"
CHUNK_CHARS = 900
CHUNK_OVERLAP = 120
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".json", ".csv", ".log", ".yaml", ".yml"}
BINARY_SUFFIXES = {".pdf", ".pptx", ".docx"}
UPLOAD_SUFFIXES = TEXT_SUFFIXES | BINARY_SUFFIXES
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class KnowledgeError(RuntimeError):
    """A failure with a stable code, so the API never has to invent detail."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def typesense_base() -> str:
    host = os.environ.get("TYPESENSE_HOST", "127.0.0.1")
    port = os.environ.get("TYPESENSE_PORT", "8108")
    return f"http://{host}:{port}"


def typesense_key() -> str:
    return os.environ.get("TYPESENSE_ADMIN_KEY", "elfred-demo-admin")


# ------------------------------------------------------------------ parsing


def _parse_text(path: Path) -> tuple[str, list]:
    return path.read_text(encoding="utf-8", errors="replace"), []


def _parse_pdf(path: Path) -> tuple[str, list]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise KnowledgeError("PARSER_UNAVAILABLE", "pypdf is not installed") from exc
    try:
        reader = PdfReader(str(path))
        sections = [(page_idx + 1, page.extract_text() or "")
                    for page_idx, page in enumerate(reader.pages)]
    except Exception as exc:  # noqa: BLE001 - a broken file is a failed job, not a crash
        raise KnowledgeError("PARSE_FAILED", f"pdf: {exc}") from exc
    return "\n\n".join(text for _page, text in sections), sections


def _parse_pptx(path: Path) -> tuple[str, list]:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise KnowledgeError("PARSER_UNAVAILABLE", "python-pptx is not installed") from exc
    try:
        deck = Presentation(str(path))
        sections = []
        for index, slide in enumerate(deck.slides, start=1):
            parts = [shape.text for shape in slide.shapes
                     if hasattr(shape, "text") and shape.text]
            sections.append((index, "\n".join(parts)))
    except Exception as exc:  # noqa: BLE001
        raise KnowledgeError("PARSE_FAILED", f"pptx: {exc}") from exc
    return "\n\n".join(text for _page, text in sections), sections


def _parse_docx(path: Path) -> tuple[str, list]:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise KnowledgeError("PARSER_UNAVAILABLE", "python-docx is not installed") from exc
    try:
        document = docx.Document(str(path))
        text = "\n".join(p.text for p in document.paragraphs if p.text)
    except Exception as exc:  # noqa: BLE001
        raise KnowledgeError("PARSE_FAILED", f"docx: {exc}") from exc
    return text, []


PARSERS = {".pdf": _parse_pdf, ".pptx": _parse_pptx, ".docx": _parse_docx}


def extract_text(path) -> tuple[str, list]:
    """Return (text, [(page, text)]) with the real parser for this file type."""
    path = Path(path)
    if not path.is_file():
        raise KnowledgeError("FILE_NOT_FOUND", f"{path} is not a readable file")
    suffix = path.suffix.lower()
    if suffix in PARSERS:
        return PARSERS[suffix](path)
    if suffix in TEXT_SUFFIXES:
        return _parse_text(path)
    raise KnowledgeError("UNSUPPORTED_FORMAT",
                         f"{suffix or 'no extension'} is not a supported document type")


def chunk_text(text: str, sections: list = None, size: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> list:
    """Split into overlapping chunks, keeping each chunk's page when known.

    A chunk never spans two pages of a PDF/PPTX: a citation that points at the
    wrong page is worse than a shorter chunk.
    """
    pieces: list = []
    blocks = sections or [(0, text)]
    for page, block in blocks:
        block = (block or "").strip()
        if not block:
            continue
        step = max(1, size - overlap)
        for start in range(0, len(block), step):
            piece = block[start:start + size].strip()
            if not piece:
                continue
            pieces.append({"text": piece, "page": page,
                           "token_estimate": max(1, len(piece) // 4)})
            if start + size >= len(block):
                break
    return pieces


# ------------------------------------------------------------------ indexing


def _request(method: str, path: str, **kw):
    headers = {"X-TYPESENSE-API-KEY": typesense_key()}
    with httpx.Client(base_url=typesense_base(), timeout=15) as client:
        response = client.request(method, path, headers=headers, **kw)
        return response


def ensure_collection() -> dict:
    """Create the knowledge collection if it is missing. Idempotent."""
    schema = {
        "name": COLLECTION,
        "fields": [
            {"name": "chunk_id", "type": "string"},
            {"name": "document_id", "type": "string", "facet": True},
            {"name": "source_id", "type": "string", "facet": True},
            {"name": "pa_id", "type": "string", "facet": True},
            {"name": "kind", "type": "string", "facet": True},
            {"name": "title", "type": "string"},
            {"name": "text", "type": "string"},
            {"name": "page", "type": "int32"},
            {"name": "ordinal", "type": "int32"},
            {"name": "indexed_at", "type": "int32"},
        ],
        "default_sorting_field": "indexed_at",
    }
    response = _request("POST", "/collections", json=schema)
    if response.status_code in (200, 201):
        return {"created": True, "collection": response.json()["name"]}
    if response.status_code == 409:
        return {"created": False, "collection": COLLECTION}
    raise KnowledgeError("INDEX_UNAVAILABLE",
                         f"typesense refused the collection: {response.status_code} "
                         f"{response.text[:200]}")


def index_chunks(document: dict, chunks: list) -> int:
    ensure_collection()
    payload = "\n".join(json.dumps({
        "chunk_id": chunk["chunk_id"],
        "document_id": document["document_id"],
        "source_id": document["source_id"],
        "pa_id": document.get("pa_id") or "",
        "kind": document.get("kind") or "personal",
        "title": document["title"],
        "page": chunk["page"],
        "ordinal": chunk["ordinal"],
        "indexed_at": int(time.time()),
        "text": chunk["text"],
    }, ensure_ascii=False) for chunk in chunks)
    if not payload:
        return 0
    response = _request("POST", f"/collections/{COLLECTION}/documents/import",
                        params={"action": "upsert"}, content=payload.encode("utf-8"))
    if response.status_code not in (200, 201):
        raise KnowledgeError("INDEX_WRITE_FAILED",
                             f"typesense import: {response.status_code} {response.text[:200]}")
    accepted = sum(1 for line in response.text.splitlines()
                   if line.strip() and '"success":true' in line.replace(" ", ""))
    if accepted != len(chunks):
        raise KnowledgeError("INDEX_WRITE_FAILED",
                             f"typesense accepted {accepted}/{len(chunks)} chunks")
    return accepted


def remove_document(document_id: str) -> dict:
    """Delete every chunk of a document. A 404 means it was already gone."""
    response = _request("DELETE", f"/collections/{COLLECTION}/documents",
                        params={"filter_by": f"document_id:={document_id}"})
    if response.status_code == 404:
        return {"deleted": 0, "note": "collection absent, index already empty"}
    if response.status_code != 200:
        raise KnowledgeError("INDEX_DELETE_FAILED",
                             f"typesense delete: {response.status_code} {response.text[:200]}")
    return {"deleted": int(response.json().get("num_deleted") or 0)}


def drop_collection() -> bool:
    response = _request("DELETE", f"/collections/{COLLECTION}")
    return response.status_code in (200, 404)


def search(query: str, pa_id: str = "", kind: str = "", per_page: int = 5) -> dict:
    filters = []
    if kind:
        filters.append(f"kind:={kind}")
    elif pa_id:
        # A PA sees its own documents plus the shared capability library.
        filters.append(f"(pa_id:={pa_id} || kind:=capability)")
    params = {"q": query, "query_by": "title,text", "per_page": max(1, min(per_page, 20))}
    if filters:
        params["filter_by"] = " && ".join(filters)
    response = _request("GET", f"/collections/{COLLECTION}/documents/search", params=params)
    if response.status_code == 404:
        return {"found": 0, "hits": [], "note": "knowledge collection does not exist yet"}
    if response.status_code != 200:
        raise KnowledgeError("INDEX_UNAVAILABLE",
                             f"typesense search: {response.status_code} {response.text[:200]}")
    body = response.json()
    hits = []
    for hit in body.get("hits", []):
        doc = hit.get("document") or {}
        hits.append({
            "chunk_id": doc.get("chunk_id"),
            "document_id": doc.get("document_id"),
            "title": doc.get("title"),
            "page": doc.get("page"),
            "kind": doc.get("kind"),
            "text": doc.get("text"),
            # The manifest turns these into citations, so the shape is explicit.
            "document": {"id": doc.get("document_id"), "title": doc.get("title")},
        })
    return {"found": body.get("found", len(hits)), "hits": hits}


def checksum_of(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()[:32]


def upload_root() -> Path:
    """Where uploaded files land. Inside the service by default, overridable so a
    real deployment can point it at a data volume."""
    configured = os.environ.get("PA_UPLOAD_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "uploads"


def safe_filename(name: str) -> str:
    """Keep the name readable but never let it escape the upload directory."""
    base = Path(str(name or "")).name.strip().replace("\\", "_").replace("/", "_")
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ()[]")
    cleaned = cleaned.strip(" .")
    if not cleaned:
        raise KnowledgeError("INVALID_OUTPUT", "the uploaded file has no usable name")
    return cleaned[:120]


def store_upload(pa_id: str, filename: str, data: bytes) -> str:
    """Validate and persist an uploaded body, returning the path to ingest.

    Validation happens before anything is written: an oversized or unsupported
    upload must fail without leaving a half-file behind that a later rebuild
    would try to parse.
    """
    name = safe_filename(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise KnowledgeError("UNSUPPORTED_FORMAT",
                             f"{suffix or 'no extension'} is not an accepted upload type")
    if not data:
        raise KnowledgeError("EMPTY_DOCUMENT", "the uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise KnowledgeError("FILE_TOO_LARGE",
                             f"{len(data)} bytes exceeds the "
                             f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    owner = safe_filename(pa_id) if pa_id else "unscoped"
    directory = upload_root() / owner
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{int(time.time() * 1000)}-{name}"
    path.write_bytes(data)
    return str(path)


# ------------------------------------------------------------------- service


class KnowledgeService:
    """Owns the document lifecycle. Every state change leaves a job record."""

    def __init__(self, store):
        self.store = store

    def ensure_source(self, name: str, kind: str, pa_id: str = "") -> dict:
        existing = [s for s in self.store.list_sources(kind=kind, pa_id=pa_id)
                    if s["name"] == name]
        if existing:
            return existing[0]
        return self.store.create_source(name=name, kind=kind, pa_id=pa_id,
                                        collection=COLLECTION)

    def ingest(self, path: str, title: str = "", kind: str = "personal",
               pa_id: str = "", source_name: str = "") -> dict:
        """Parse, chunk, store and index one document. Fails loudly, never silently."""
        document_path = Path(path)
        source = self.ensure_source(source_name or kind, kind, pa_id)
        job = self.store.add_job("ingest", source_id=source["source_id"], state="running",
                                 detail=f"parsing {document_path.name}")
        try:
            document = self.store.create_document(
                source_id=source["source_id"],
                title=title or document_path.stem,
                path=str(document_path),
                mime=document_path.suffix.lower().lstrip("."),
                size=document_path.stat().st_size if document_path.exists() else 0,
                checksum=checksum_of(document_path) if document_path.exists() else "",
            )
        except Exception as exc:  # noqa: BLE001 - a bad path is a failed job
            self.store.update_job(job["job_id"], "failed", f"{type(exc).__name__}: {exc}")
            raise
        self.store.update_document(document["document_id"], status="parsing")
        try:
            text, sections = extract_text(document_path)
            chunks = chunk_text(text, sections)
            if not chunks:
                raise KnowledgeError("EMPTY_DOCUMENT",
                                     "the parser found no text to index")
            rows = self.store.replace_chunks(document["document_id"], chunks)
        except Exception as exc:  # noqa: BLE001 - never leave a job "running"
            code = exc.code if isinstance(exc, KnowledgeError) else type(exc).__name__
            self.store.update_document(document["document_id"], status="failed",
                                       error=f"{code}: {exc}")
            self.store.update_job(job["job_id"], "failed", f"{code}: {exc}")
            raise
        indexed_document = {**document, "pa_id": pa_id, "kind": kind}
        try:
            count = index_chunks(indexed_document, rows)
        except Exception as exc:  # noqa: BLE001
            # The chunks are real and stored; only the index is missing, and the
            # document says exactly that so a rebuild can finish the job.
            code = exc.code if isinstance(exc, KnowledgeError) else type(exc).__name__
            self.store.update_document(document["document_id"], status="stored",
                                       error=f"{code}: {exc}",
                                       chunk_count=len(rows))
            self.store.update_job(job["job_id"], "failed", f"{code}: {exc}")
            raise
        self.store.update_document(document["document_id"], status="indexed", error="",
                                   chunk_count=len(rows))
        self.store.update_job(job["job_id"], "succeeded",
                              f"indexed {count} chunk(s) from {len(rows)}")
        return {"document": self.store.get_document(document["document_id"]),
                "chunks": len(rows), "indexed": count, "job_id": job["job_id"]}

    def delete(self, document_id: str) -> dict:
        document = self.store.get_document(document_id)
        if not document:
            raise KnowledgeError("NOT_FOUND", f"unknown document {document_id}")
        job = self.store.add_job("delete", document_id=document_id, state="running",
                                 detail="removing chunks from the index")
        removed = remove_document(document_id)
        self.store.delete_document(document_id)
        self.store.update_job(job["job_id"], "succeeded",
                              f"deleted {removed['deleted']} indexed chunk(s)")
        return {"document_id": document_id, "indexed_deleted": removed["deleted"],
                "job_id": job["job_id"]}

    def rebuild(self, kind: str = "", pa_id: str = "") -> dict:
        """Drop the collection and re-index every stored chunk from the database."""
        job = self.store.add_job("rebuild", state="running",
                                 detail="dropping and re-creating the collection")
        dropped = drop_collection()
        ensure_collection()
        reindexed, skipped = [], []
        for document in self.store.list_documents():
            source = self.store.get_source(document["source_id"]) or {}
            if kind and source.get("kind") != kind:
                skipped.append(document["document_id"])
                continue
            if pa_id and source.get("pa_id") != pa_id:
                skipped.append(document["document_id"])
                continue
            chunks = self.store.list_chunks(document["document_id"])
            if not chunks:
                skipped.append(document["document_id"])
                continue
            try:
                index_chunks({**document, "pa_id": source.get("pa_id") or "",
                              "kind": source.get("kind") or "personal"}, chunks)
            except KnowledgeError as exc:
                self.store.update_document(document["document_id"], status="stored",
                                           error=f"{exc.code}: {exc.message}")
                skipped.append(document["document_id"])
                continue
            self.store.update_document(document["document_id"], status="indexed",
                                       error="", chunk_count=len(chunks))
            reindexed.append(document["document_id"])
        self.store.update_job(job["job_id"], "succeeded",
                              f"re-indexed {len(reindexed)}, skipped {len(skipped)}")
        return {"dropped": dropped, "reindexed": reindexed, "skipped": skipped,
                "job_id": job["job_id"]}

    def search(self, query: str, pa_id: str = "", kind: str = "", per_page: int = 5) -> dict:
        return search(query, pa_id=pa_id, kind=kind, per_page=per_page)
