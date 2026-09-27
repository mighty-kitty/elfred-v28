"""Loopback-only Elfred adapter over EMOS's native durable state store.

Only the application's server token can access this surface. The native /memory
API is deliberately absent: the application retains evidence and scope policy.
"""
from __future__ import annotations

import copy
import hmac
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs
from uuid import uuid5, NAMESPACE_URL

from ..models import MemoryEntry
from ..storage_backends import build_state_store

EMPTY = {"episodic": [], "emotional": [], "semantic": {}, "dreams": {}, "memory_blocks": {}, "idempotency_records": {}}
SYSTEMS = {"explore", "advise", "create", "connect", "execute"}


class Bridge:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.store = build_state_store("sqlite", path.with_suffix(".json"), path)
        self.lock = threading.RLock()

    def apply(self, method, external_id, data):
        if not isinstance(data, dict) or data.get("contract") != "elfred-memory-v1" or data.get("id") != external_id:
            raise ValueError("Invalid memory contract")
        owner, revision, state_hash = data.get("owner"), data.get("revision"), data.get("state_hash")
        sequence = data.get("intent_sequence", revision)
        if not isinstance(owner, str) or not re.fullmatch(r"[\w-]{1,100}", owner) or type(revision) is not int or revision < 1 or type(sequence) is not int or sequence < 1 or not isinstance(state_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", state_hash):
            raise ValueError("Invalid memory identity")
        if method == "PUT":
            if data.get("scope") not in SYSTEMS | {"owner"} or not isinstance(data.get("content"), str) or not data["content"].strip() or len(data["content"]) > 12000:
                raise ValueError("Invalid memory content or allocation")
            allocation = data.get("allocation", {})
            if not isinstance(allocation, dict) or any(system not in SYSTEMS for system in allocation.get("allowed_systems", [])):
                raise ValueError("Invalid allocation")
        elif data.get("action") != "forget":
            raise ValueError("Invalid withdrawal")
        key = "elfred:" + str(uuid5(NAMESPACE_URL, owner + ":" + external_id))
        physical_id = key.removeprefix("elfred:")
        with self.lock:
            payload = self.store.load(default=copy.deepcopy(EMPTY))
            records = payload.setdefault("idempotency_records", {})
            previous = records.get(key)
            receipt = {"contract": "elfred-memory-v1", "owner": owner, "id": external_id, "revision": revision, "state_hash": state_hash, "intent_sequence": sequence}
            if previous:
                if sequence < previous["intent_sequence"] or revision < previous["revision"]:
                    raise ValueError("Stale memory revision")
                if sequence == previous["intent_sequence"]:
                    if previous["state_hash"] != state_hash or previous["action"] != method:
                        raise ValueError("Conflicting memory revision")
                    return receipt
            payload["episodic"] = [entry for entry in payload["episodic"] if entry["memory_id"] != physical_id]
            if method == "PUT":
                # Preserve the application's exact allocation/evidence. Do not
                # re-extract unrestricted facts from its provisional memories.
                entry = MemoryEntry(memory_id=physical_id, text=data["content"], category="elfred_scoped", score=0.0, user_id=owner, session_id="elfred:" + data["scope"], metadata={"status": "active", "revision": revision, "elfred": copy.deepcopy(data)})
                payload["episodic"].append(entry.to_dict())
            records[key] = {**receipt, "action": method}
            # SQLiteStateStore commits atomically. No receipt before commit.
            self.store.save(payload)
            return receipt

    def read(self, owner, external_id):
        physical_id = str(uuid5(NAMESPACE_URL, owner + ":" + external_id))
        with self.lock:
            payload = self.store.load(default=copy.deepcopy(EMPTY))
            return next((entry["metadata"]["elfred"] for entry in payload["episodic"] if entry["user_id"] == owner and entry["memory_id"] == physical_id), None)


def create_handler(bridge, token):
    if not token or len(token) < 32:
        raise ValueError("A server-only token of at least 32 characters is required")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, payload):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send(401, {"error": "Authentication required"})
                return False
            return True

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send(200, {"status": "ok", "contract": "elfred-memory-v1", "storage": "emos-native-sqlite", "mode": "scoped-adapter"})
                return
            if not self.authorized():
                return
            if parsed.path == "/v1/status":
                self.send(200, {"status": "ok", "contract": "elfred-memory-v1"})
                return
            match = re.fullmatch(r"/v1/memories/([\w-]{1,100})", parsed.path)
            if match:
                owner = parse_qs(parsed.query).get("owner", [""])[0]
                result = bridge.read(owner, unquote(match[1]))
                self.send(200 if result else 404, result or {"error": "Memory not found"})
                return
            self.send(404, {"error": "Route not available in scoped adapter"})

        def mutate(self):
            if not self.authorized():
                return
            match = re.fullmatch(r"/v1/memories/([\w-]{1,100})", self.path)
            if not match:
                self.send(404, {"error": "Route not available in scoped adapter"})
                return
            self.connection.settimeout(5)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100000:
                    raise ValueError("Invalid request length")
                data = json.loads(self.rfile.read(length))
                receipt = bridge.apply(self.command, match[1], data)
            except (ValueError, TypeError, KeyError):
                self.send(400, {"error": "Invalid or stale memory request"})
                return
            except Exception:
                self.send(503, {"error": "Durable memory write failed"})
                return
            self.send(200, receipt)

        do_PUT = mutate
        do_DELETE = mutate

    return Handler


if __name__ == "__main__":
    path = Path(os.environ["ELFRED_EMOS_DATABASE"])
    token = os.environ["ELFRED_MEMORY_HUB_TOKEN"]
    port = int(os.environ.get("ELFRED_EMOS_PORT", "8200"))
    ThreadingHTTPServer(("127.0.0.1", port), create_handler(Bridge(path), token)).serve_forever()
