from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from adapter.config import Settings
from adapter.service import AdapterService
from adapter.storage.store import now_iso


def inspect_legacy(source_db: Path) -> dict[str, Any]:
    if not source_db.exists():
        raise FileNotFoundError(source_db)
    with sqlite3.connect(source_db) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "ingested_events" not in tables:
            raise ValueError("legacy database has no ingested_events table")
        events = conn.execute("SELECT event_id,payload_json,status FROM ingested_events ORDER BY created_at").fetchall()
        topics = conn.execute("SELECT * FROM topics ORDER BY topic_id").fetchall() if "topics" in tables else []
        aliases = conn.execute("SELECT * FROM topic_aliases").fetchall() if "topic_aliases" in tables else []
        outbox = conn.execute("SELECT * FROM outbox WHERE status!='acknowledged'").fetchall() if "outbox" in tables else []
    return {
        "tables": sorted(tables),
        "events": [dict(row) for row in events],
        "topics": [dict(row) for row in topics],
        "aliases": [dict(row) for row in aliases],
        "outbox": [dict(row) for row in outbox],
    }


def migrate(source_db: Path, service: AdapterService, *, dry_run: bool) -> dict[str, Any]:
    legacy = inspect_legacy(source_db)
    batch_id = "migration_" + uuid.uuid4().hex
    report: dict[str, Any] = {
        "batch_id": batch_id,
        "source_db": str(source_db.resolve()),
        "dry_run": dry_run,
        "legacy_counts": {key: len(legacy[key]) for key in ("events", "topics", "aliases", "outbox")},
        "imported_event_ids": [],
        "result_counts": {},
        "errors": [],
    }
    if dry_run:
        report["status"] = "dry_run_complete"
        return report

    alias_map: dict[str, list[str]] = {}
    for alias in legacy["aliases"]:
        alias_map.setdefault(alias["topic_id"], []).append(alias.get("alias") or alias.get("normalized_alias") or "")
    for topic in legacy["topics"]:
        service.store.seed_topic(
            topic["topic_id"], topic["display_name"], [value for value in alias_map.get(topic["topic_id"], []) if value]
        )
    for item in legacy["events"]:
        try:
            payload = json.loads(item["payload_json"])
            result = service.process_payload(payload)
            report["result_counts"][result.status] = report["result_counts"].get(result.status, 0) + 1
            if result.status in {"synced", "retry", "privacy_blocked"}:
                report["imported_event_ids"].append(result.event_id)
        except Exception as error:
            report["errors"].append({"event_id": item["event_id"], "error": str(error)})
    for item in legacy["outbox"]:
        target = str(item.get("target") or "").replace("-", "_")
        if target in {"memory", "personal_agent"}:
            try:
                service.store.enqueue(target, item.get("event_id") or "legacy", json.loads(item["payload_json"]))
            except Exception as error:
                report["errors"].append({"outbox_item_id": item.get("item_id"), "error": str(error)})
    report["status"] = "completed_with_errors" if report["errors"] else "completed"
    with service.store.transaction() as conn:
        conn.execute(
            """INSERT INTO migration_batches
            (batch_id,source_path,dry_run,status,imported_event_ids_json,report_json,created_at)
            VALUES(?,?,?,?,?,?,?)""",
            (
                batch_id,
                str(source_db.resolve()),
                0,
                report["status"],
                json.dumps(report["imported_event_ids"], ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                now_iso(),
            ),
        )
    return report


def rollback(batch_id: str, service: AdapterService) -> dict[str, Any]:
    with service.store.connect() as conn:
        row = conn.execute("SELECT * FROM migration_batches WHERE batch_id=?", (batch_id,)).fetchone()
    if not row:
        raise KeyError(batch_id)
    event_ids = json.loads(row["imported_event_ids_json"])
    results = []
    for event_id in reversed(event_ids):
        try:
            results.append(service.forget_event(event_id))
        except Exception as error:
            results.append({"event_id": event_id, "status": "error", "error": str(error)})
    completed = all(item["status"] == "completed" for item in results)
    with service.store.transaction() as conn:
        conn.execute(
            "UPDATE migration_batches SET status=?,rolled_back_at=? WHERE batch_id=?",
            ("rolled_back" if completed else "rollback_partial", now_iso(), batch_id),
        )
    return {"batch_id": batch_id, "status": "rolled_back" if completed else "rollback_partial", "results": results}


def default_source() -> Path:
    return Path(__file__).resolve().parents[3] / "elfred_context_organizer_legacy" / "data" / "organizer.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate the retained legacy Organizer SQLite database")
    parser.add_argument("--source-db", type=Path, default=default_source())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", metavar="BATCH_ID")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    service = AdapterService(Settings.from_env())
    result = rollback(args.rollback, service) if args.rollback else migrate(args.source_db, service, dry_run=args.dry_run)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
