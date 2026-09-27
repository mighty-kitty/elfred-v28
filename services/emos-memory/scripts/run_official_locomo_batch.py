from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory_system.benchmarks.runner import (
    _build_runtime_config,
    _contains_expected,
    _matched_rank,
    load_all_benchmarks,
)
from src.memory_system.workflow import build_default_agent


def _summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {
            "total": 0,
            "hit_at_1": 0.0,
            "hit_at_3": 0.0,
            "mrr": 0.0,
            "miss_count": 0,
        }
    return {
        "total": len(rows),
        "hit_at_1": mean(1.0 if row["hit_at_1"] else 0.0 for row in rows),
        "hit_at_3": mean(1.0 if row["hit_at_3"] else 0.0 for row in rows),
        "mrr": mean((1.0 / row["rank"]) if row["rank"] else 0.0 for row in rows),
        "miss_count": sum(1 for row in rows if not row["hit_at_1"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run official LoCoMo full benchmark on selected conversations.")
    parser.add_argument("--conv", nargs="+", required=True, help="Conversation ids such as conv-49 conv-50")
    parser.add_argument("--benchmark-root", default="data/benchmarks/official", help="Official benchmark root")
    parser.add_argument("--limit", type=int, default=None, help="Optional sample cap after conversation filtering")
    args = parser.parse_args()

    benchmark_root = Path(args.benchmark_root)
    all_samples, manifests = load_all_benchmarks(Path("data/benchmarks"), extra_roots=[benchmark_root])
    allowed = set(args.conv)
    filtered = [
        sample
        for sample in all_samples
        if sample.benchmark == "locomo_official_full" and sample.sample_id.split("-qa-")[0] in allowed
    ]
    filtered.sort(key=lambda sample: sample.sample_id)
    if args.limit is not None:
        filtered = filtered[: args.limit]

    rows: list[dict[str, object]] = []
    per_conversation_rows: dict[str, list[dict[str, object]]] = defaultdict(list)

    for sample in filtered:
        config = _build_runtime_config("embedding_rerank")
        memory_file = os.environ.get("MEMORY_SYSTEM_MEMORY_FILE")
        sqlite_file = os.environ.get("MEMORY_SYSTEM_SQLITE_FILE")
        if memory_file:
            config.paths.memory_file = Path(memory_file)
        if sqlite_file:
            config.paths.sqlite_file = Path(sqlite_file)
        agent = build_default_agent(config=config)
        user_id = f"{sample.user_id}-{sample.sample_id}"
        session_id = f"{sample.session_id}-{sample.sample_id}"
        for history_turn in sample.history:
            agent.ingest_history_turn(user_id=user_id, session_id=session_id, text=history_turn)
        result = agent.process_turn(
            user_id=user_id,
            session_id=session_id,
            text=sample.query_text,
            persist=False,
        )
        ranked = [candidate.surface_text for candidate in result.retrieval_candidates]
        expected = sample.expectation.memory_hints
        row = {
            "sample_id": sample.sample_id,
            "conversation": sample.sample_id.split("-qa-")[0],
            "hit_at_1": _contains_expected(ranked[:1], expected),
            "hit_at_3": _contains_expected(ranked[:3], expected),
            "rank": _matched_rank(ranked, expected),
            "query": sample.query_text,
        }
        rows.append(row)
        per_conversation_rows[row["conversation"]].append(row)

    payload = {
        "summary": _summarize(rows),
        "per_conversation": {
            conv: _summarize(conv_rows) for conv, conv_rows in sorted(per_conversation_rows.items())
        },
        "conversations": args.conv,
        "benchmark_manifest": manifests.get("locomo_official_full", {}),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
