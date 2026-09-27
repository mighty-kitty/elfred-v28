from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory_system.benchmarks.base import BenchmarkResult, BenchmarkSample
from src.memory_system.benchmarks.datasets import load_all_benchmarks
from src.memory_system.benchmarks.runner import (
    CANONICAL_BACKENDS,
    _classify_error,
    _contains_expected,
    _matched_rank,
    build_summary,
)
from src.memory_system.config import AppConfig
from src.memory_system.emotion_engine import CALM_EMOTION
from src.memory_system.memory_repository import MemoryRepository
from src.memory_system.models import MemoryEntry


def _conversation_key(sample: BenchmarkSample) -> str:
    return str(sample.metadata.get("conversation_index", sample.sample_id.split("-qa-")[0].replace("conv-", "")))


def _group(samples: list[BenchmarkSample], key_fn) -> dict[str, list[BenchmarkSample]]:
    grouped: dict[str, list[BenchmarkSample]] = defaultdict(list)
    for sample in samples:
        grouped[str(key_fn(sample))].append(sample)
    return grouped


def _evenly_spaced(items: list[BenchmarkSample], limit: int) -> list[BenchmarkSample]:
    if len(items) <= limit:
        return list(items)
    if limit <= 1:
        return [items[len(items) // 2]]
    indexes = sorted({round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)})
    return [items[index] for index in indexes]


def _select_subset(
    samples: list[BenchmarkSample],
    samples_per_conversation: int,
    max_conversations: int | None,
    conversations_filter: list[str] | None,
) -> list[BenchmarkSample]:
    by_conv = _group(samples, _conversation_key)
    conversations = sorted(by_conv, key=lambda value: int(value) if value.isdigit() else value)
    if conversations_filter:
        wanted = {str(item) for item in conversations_filter}
        conversations = [conversation for conversation in conversations if conversation in wanted]
    if max_conversations is not None:
        conversations = conversations[:max_conversations]
    selected: list[BenchmarkSample] = []
    for conv in conversations:
        conv_samples = sorted(by_conv[conv], key=lambda item: item.sample_id)
        by_task = _group(conv_samples, lambda sample: str(sample.metadata.get("task", "unknown")))
        tasks = sorted(by_task)
        base = max(1, samples_per_conversation // max(1, len(tasks)))
        picked: list[BenchmarkSample] = []
        for task in tasks:
            picked.extend(_evenly_spaced(sorted(by_task[task], key=lambda item: item.sample_id), base))
        if len(picked) < samples_per_conversation:
            remaining = [sample for sample in conv_samples if sample not in picked]
            picked.extend(_evenly_spaced(remaining, samples_per_conversation - len(picked)))
        selected.extend(sorted(picked, key=lambda item: item.sample_id)[:samples_per_conversation])
    return selected


def _runtime_config(label: str) -> AppConfig:
    config = AppConfig()
    runtime_dir = config.paths.data_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid4().hex[:8]
    config.paths.memory_file = runtime_dir / f"lightweight_{label}_{suffix}.json"
    config.paths.sqlite_file = runtime_dir / f"lightweight_{label}_{suffix}.sqlite3"
    config.log_level = "WARNING"
    return config


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "mean_ms": mean(values) if values else 0.0,
        "median_ms": median(values) if values else 0.0,
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values) if values else 0.0,
    }


def _load_samples() -> tuple[list[BenchmarkSample], dict[str, object]]:
    config = AppConfig()
    samples, manifests = load_all_benchmarks(
        config.paths.data_dir / "benchmarks",
        extra_roots=[config.paths.data_dir / "benchmarks" / "official"],
    )
    official = [sample for sample in samples if sample.benchmark == "locomo_official_full"]
    return official, manifests.get("locomo_official_full", {})


def _add_history(repo: MemoryRepository, user_id: str, session_id: str, history: list[str]) -> None:
    for index, turn in enumerate(history):
        repo.add_memory(
            MemoryEntry(
                text=turn,
                category="episodic",
                score=0.55,
                user_id=user_id,
                session_id=session_id,
                emotion=CALM_EMOTION,
                metadata={"source": "locomo_history", "turn_index": index},
            )
        )


def run(
    backends: list[str],
    samples_per_conversation: int,
    max_conversations: int | None,
    conversations_filter: list[str] | None,
    prefilter_enabled: bool,
    prefilter_min_records: int,
    prefilter_candidate_pool: int,
    prefilter_recency_pool: int,
    out_dir: Path,
    out_name: str,
) -> dict[str, object]:
    samples, manifest = _load_samples()
    selected = _select_subset(samples, samples_per_conversation, max_conversations, conversations_filter)
    by_conv = _group(selected, _conversation_key)
    summaries: dict[str, dict[str, object]] = {}
    detailed: dict[str, list[dict[str, object]]] = {}
    latency_summaries: dict[str, dict[str, float]] = {}
    prefilter_reports: dict[str, dict[str, object]] = {}

    for backend in backends:
        print(f"[backend] {backend}", flush=True)
        results: list[BenchmarkResult] = []
        recall_latencies: list[float] = []
        last_prefilter_report: dict[str, object] = {}
        for conv, conv_samples in sorted(by_conv.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
            print(f"  [conv {conv}] {len(conv_samples)} samples", flush=True)
            conv_samples = sorted(conv_samples, key=lambda item: item.sample_id)
            user_id = f"lightweight-{backend}-conv-{conv}"
            session_id = f"lightweight-{backend}-conv-{conv}"
            repo = MemoryRepository(
                _runtime_config(f"{backend}_{conv}"),
                retrieval_settings_override={
                    "backend": backend,
                    "prefilter": {
                        "enabled": prefilter_enabled,
                        "min_records": prefilter_min_records,
                        "candidate_pool": prefilter_candidate_pool,
                        "recency_pool": prefilter_recency_pool,
                    },
                },
            )
            _add_history(repo, user_id, session_id, conv_samples[0].history)
            for sample in conv_samples:
                recall_start = time.perf_counter()
                candidates = repo.recall_with_trace(
                    user_id=user_id,
                    text=sample.query_text,
                    emotion=CALM_EMOTION,
                    top_k=8,
                )
                recall_latencies.append((time.perf_counter() - recall_start) * 1000)
                last_prefilter_report = dict(repo._last_retrieval_prefilter_report)
                ranked = [candidate.surface_text for candidate in candidates]
                semantic_match_min = int(sample.metadata.get("semantic_match_min", 0))
                hit_at_1 = _contains_expected(ranked[:1], sample.expectation.memory_hints, semantic_match_min)
                hit_at_3 = _contains_expected(ranked[:3], sample.expectation.memory_hints, semantic_match_min)
                matched_rank = _matched_rank(ranked, sample.expectation.memory_hints, semantic_match_min)
                results.append(
                    BenchmarkResult(
                        backend=backend,
                        benchmark=sample.benchmark,
                        sample_id=sample.sample_id,
                        split=sample.split,
                        task=str(sample.metadata.get("task", "unknown")),
                        difficulty=str(sample.metadata.get("difficulty", "official")),
                        hit_at_1=hit_at_1,
                        hit_at_3=hit_at_3,
                        reciprocal_rank=(1.0 / matched_rank) if matched_rank else 0.0,
                        matched_rank=matched_rank,
                        meets_target_rank=bool(matched_rank and matched_rank <= sample.expectation.target_rank_max),
                        target_rank_max=sample.expectation.target_rank_max,
                        top_score=candidates[0].score if candidates else 0.0,
                        recalled_text=None,
                        expected_memory_hints=sample.expectation.memory_hints,
                        recalled_surface_text=ranked[0] if ranked else None,
                        conversation_key=conv,
                        error_category=None if hit_at_3 else _classify_error(sample),
                    )
                )
        summaries[backend] = build_summary(results, backend_name=backend)
        detailed[backend] = [asdict(item) for item in results]
        latency_summaries[backend] = _latency_summary(recall_latencies)
        prefilter_reports[backend] = last_prefilter_report
        _write_outputs(
            out_dir,
            manifest,
            selected,
            summaries,
            detailed,
            latency_summaries,
            prefilter_reports,
            samples_per_conversation,
            max_conversations,
            conversations_filter,
            prefilter_enabled,
            prefilter_min_records,
            prefilter_candidate_pool,
            prefilter_recency_pool,
            out_name,
        )
    return {
        "manifest": manifest,
        "selected": selected,
        "summaries": summaries,
        "detailed": detailed,
        "latency_summaries": latency_summaries,
        "prefilter_reports": prefilter_reports,
    }


def _write_outputs(
    out_dir: Path,
    manifest: dict[str, object],
    selected: list[BenchmarkSample],
    summaries: dict[str, dict[str, object]],
    detailed: dict[str, list[dict[str, object]]],
    latency_summaries: dict[str, dict[str, float]],
    prefilter_reports: dict[str, dict[str, object]],
    samples_per_conversation: int,
    max_conversations: int | None,
    conversations_filter: list[str] | None,
    prefilter_enabled: bool,
    prefilter_min_records: int,
    prefilter_candidate_pool: int,
    prefilter_recency_pool: int,
    out_name: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": "lightweight retrieval-only baseline; history inserted once per conversation via MemoryRepository.add_memory",
        "samples_per_conversation": samples_per_conversation,
        "max_conversations": max_conversations,
        "conversations_filter": conversations_filter,
        "prefilter": {
            "enabled": prefilter_enabled,
            "min_records": prefilter_min_records,
            "candidate_pool": prefilter_candidate_pool,
            "recency_pool": prefilter_recency_pool,
            "last_reports": prefilter_reports,
        },
        "total_selected": len(selected),
        "selected_sample_ids": [sample.sample_id for sample in selected],
        "manifest": manifest,
        "summaries": summaries,
        "latency_summaries": latency_summaries,
        "detailed": detailed,
    }
    json_path = out_dir / f"{out_name}.json"
    md_path = out_dir / f"{out_name}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Lightweight LoCoMo Baseline",
        "",
        f"- Total selected: {len(selected)}",
        f"- Samples per conversation: {samples_per_conversation}",
        f"- Max conversations: {max_conversations if max_conversations is not None else 'all'}",
        f"- Conversations: {', '.join(conversations_filter) if conversations_filter else 'all'}",
        f"- Indexed prefilter enabled: {prefilter_enabled}",
        f"- Indexed prefilter candidate pool: {prefilter_candidate_pool}",
        "",
        "## Results",
    ]
    for backend, summary in summaries.items():
        latency = latency_summaries.get(backend, {})
        lines.append(
            f"- {backend}: Hit@1={summary['hit_at_1']:.3f}, Hit@3={summary['hit_at_3']:.3f}, "
            f"MRR={summary['mrr']:.3f}, Pass@Target={summary['pass_at_target_rank']:.3f}, "
            f"RecallP95={latency.get('p95_ms', 0.0):.3f}ms"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight retrieval-only LoCoMo baseline.")
    parser.add_argument("--backend", action="append", choices=CANONICAL_BACKENDS, dest="backends")
    parser.add_argument("--samples-per-conversation", type=int, default=2)
    parser.add_argument("--max-conversations", type=int)
    parser.add_argument("--conversation", action="append", dest="conversations")
    parser.add_argument("--prefilter-enabled", action="store_true")
    parser.add_argument("--prefilter-min-records", type=int, default=512)
    parser.add_argument("--prefilter-candidate-pool", type=int, default=128)
    parser.add_argument("--prefilter-recency-pool", type=int, default=16)
    parser.add_argument("--out-dir", default="logs/paper_baselines")
    parser.add_argument("--out-name", default="lightweight_locomo_baseline")
    args = parser.parse_args()
    backends = args.backends or list(CANONICAL_BACKENDS)
    result = run(
        backends,
        args.samples_per_conversation,
        args.max_conversations,
        args.conversations,
        args.prefilter_enabled,
        args.prefilter_min_records,
        args.prefilter_candidate_pool,
        args.prefilter_recency_pool,
        Path(args.out_dir),
        args.out_name,
    )
    compact = {
        backend: {
            "total": summary["total"],
            "hit_at_1": summary["hit_at_1"],
            "hit_at_3": summary["hit_at_3"],
            "mrr": summary["mrr"],
            "pass_at_target_rank": summary["pass_at_target_rank"],
            "recall_p95_ms": result["latency_summaries"].get(backend, {}).get("p95_ms"),
        }
        for backend, summary in result["summaries"].items()
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
