from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from adapter.config import Settings
from adapter.freetodo_client import FreeTodoClient, InMemoryFreeTodoClient
from adapter.scripts.demo_events import build_demo_events
from adapter.service import AdapterService


def _cleanup_owned_demo_objects(client: FreeTodoClient) -> dict[str, int]:
    cleaned = {"todos": 0, "journals": 0}
    for todo in client.list_todos():
        if str(todo.get("uid") or "").startswith("elfred-demo-20260713-"):
            client.delete_todo(int(todo["id"]))
            cleaned["todos"] += 1
    for journal in client.list_journals():
        if journal.get("uid") == "elfred-daily-2026-07-13":
            client.delete_journal(int(journal["id"]))
            cleaned["journals"] += 1
    return cleaned


def run_demo(real_http: bool, db_path: Path, reset_demo: bool = False) -> dict[str, Any]:
    settings = replace(Settings.from_env(), db_path=db_path)
    client: FreeTodoClient = FreeTodoClient(settings.freetodo_base_url) if real_http else InMemoryFreeTodoClient()
    cleaned = _cleanup_owned_demo_objects(client) if real_http and reset_demo else {"todos": 0, "journals": 0}
    if reset_demo and db_path.exists():
        db_path.unlink()
    service = AdapterService(settings, client)
    events = build_demo_events()
    results = [service.process_payload(event).model_dump(mode="json") for event in events]
    duplicate = service.process_payload(events[0]).model_dump(mode="json")
    status = service.status()
    todo_list = client.list_todos()
    journals = client.list_journals()
    sensitive_blob = json.dumps({"todos": todo_list, "journals": journals}, ensure_ascii=False)
    elfred_topics = []
    for event_id in ("demo-20260713-001", "demo-20260713-015", "demo-20260713-016"):
        elfred_topics.append([topic["topic_id"] for topic in service.store.topics_for_event(event_id) if topic["topic_id"] == "topic_elfred"])
    weekly = service.weekly_report(2026, 29)
    checks = {
        "twenty_events_submitted": len(events) == 20,
        "duplicate_is_idempotent": duplicate["status"] == "duplicate",
        "sensitive_event_blocked": results[9]["status"] == "privacy_blocked",
        "sensitive_secret_absent_remote": "DEMO-SECRET-MUST-NOT-LEAVE" not in sensitive_blob,
        "pii_redacted_remote": "13800138000" not in sensitive_blob and "demo.owner@example.com" not in sensitive_blob,
        "todo_created": len(todo_list) >= 10,
        "single_daily_journal": len([j for j in journals if j.get("uid") == "elfred-daily-2026-07-13"]) == 1,
        "idea_oriented_journal": bool(journals) and all(section in (journals[-1].get("content_ai") or "") for section in ("新想法与认识", "关键决策", "风险与卡点", "下一步")),
        "topic_alias_stable": all(elfred_topics),
        "memory_outbox_idempotent": status["counts"]["memory_outbox"] == 19,
        "pa_outbox_idempotent": status["counts"]["personal_agent_outbox"] == 19,
        "weekly_is_synthesis": "main_threads" in weekly and "daily" not in weekly,
    }
    report = {
        "mode": "real_http" if real_http else "in_memory",
        "database": str(db_path),
        "cleaned_before_run": cleaned,
        "submitted": len(events) + 1,
        "result_counts": {state: sum(1 for item in [*results, duplicate] if item["status"] == state) for state in {item["status"] for item in [*results, duplicate]}},
        "adapter_status": status,
        "remote_counts": {"todos": len(todo_list), "journals": len(journals)},
        "checks": checks,
        "passed": all(checks.values()),
    }
    if not report["passed"]:
        raise RuntimeError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 20-event Elfred × FreeTodo acceptance demo")
    parser.add_argument("--real-http", action="store_true", help="Use FREETODO_BASE_URL instead of the in-memory fake")
    parser.add_argument("--reset-demo", action="store_true", help="Delete only adapter-owned demo objects before the run")
    parser.add_argument("--db", type=Path, help="Adapter SQLite path")
    parser.add_argument("--output", type=Path, help="Write the JSON report")
    parser.add_argument("--write-samples", type=Path, help="Write the 20 redacted sample events and exit")
    args = parser.parse_args()
    if args.write_samples:
        args.write_samples.parent.mkdir(parents=True, exist_ok=True)
        args.write_samples.write_text(json.dumps({"events": build_demo_events()}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(args.write_samples)
        return
    db_path = args.db or (Path(tempfile.mkdtemp(prefix="elfred-freetodo-demo-")) / "elfred_adapter.db")
    report = run_demo(args.real_http, db_path.resolve(), args.reset_demo)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
