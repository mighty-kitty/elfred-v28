from __future__ import annotations

import json
import os
from pathlib import Path

from .base import BenchmarkExpectation, BenchmarkSample


def load_jsonl_rows(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def load_json_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("samples", "records", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def load_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl_rows(path)
    return load_json_rows(path)


def _coerce_history(value) -> list[str]:
    if isinstance(value, list):
        history: list[str] = []
        for item in value:
            if isinstance(item, str):
                history.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("utterance")
                if text:
                    history.append(str(text))
        return history
    if isinstance(value, str):
        return [value]
    return []


def _coerce_hints(row: dict[str, object]) -> list[str]:
    value = (
        row.get("expected_memory_hints")
        or row.get("gold_hints")
        or row.get("supporting_hints")
        or row.get("answers")
        or row.get("answer_aliases")
    )
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    single_value = row.get("expected_memory_hint") or row.get("answer")
    if isinstance(single_value, str):
        return [single_value]
    return []


def _build_sample(
    row: dict[str, object],
    benchmark: str,
    split: str,
    source: str,
) -> BenchmarkSample:
    metadata = dict(row.get("metadata", {})) if isinstance(row.get("metadata"), dict) else {}
    metadata.setdefault("source", source)
    if "task" in row:
        metadata.setdefault("task", str(row["task"]))
    if "difficulty" in row:
        metadata.setdefault("difficulty", str(row["difficulty"]))

    history = _coerce_history(
        row.get("history") or row.get("context") or row.get("conversation") or row.get("dialogue")
    )
    query_text = (
        row.get("query_text")
        or row.get("query")
        or row.get("question")
        or row.get("prompt")
    )
    if not isinstance(query_text, str):
        raise ValueError(f"Benchmark sample {benchmark}/{split} is missing query text")

    sample_id = row.get("sample_id") or row.get("id") or row.get("example_id")
    if not isinstance(sample_id, str):
        raise ValueError(f"Benchmark sample {benchmark}/{split} is missing sample_id")

    user_id = row.get("user_id") or row.get("speaker_id") or row.get("persona_id") or f"{benchmark}-user"
    session_id = row.get("session_id") or row.get("conversation_id") or row.get("dialogue_id") or f"{benchmark}-{split}"
    expected_hints = _coerce_hints(row)
    target_rank_max = int(row.get("target_rank_max", row.get("max_rank", 1)))

    return BenchmarkSample(
        benchmark=benchmark,
        sample_id=sample_id,
        split=str(row.get("split", split)),
        user_id=str(user_id),
        session_id=str(session_id),
        history=history,
        query_text=query_text,
        expectation=BenchmarkExpectation(
            memory_hints=expected_hints,
            target_rank_max=target_rank_max,
        ),
        metadata=metadata,
    )


def _natural_session_keys(conversation: dict[str, object]) -> list[str]:
    session_keys = [
        key
        for key, value in conversation.items()
        if key.startswith("session_") and isinstance(value, list)
    ]
    return sorted(session_keys, key=lambda item: int(item.split("_")[1]))


def _locomo_turn_lookup(conversation: dict[str, object]) -> dict[str, str]:
    turn_lookup: dict[str, str] = {}
    for session_key in _natural_session_keys(conversation):
        for turn in conversation.get(session_key, []):
            if isinstance(turn, dict) and turn.get("dia_id") and turn.get("text"):
                pieces: list[str] = []
                pieces.append(str(turn["text"]))
                if turn.get("blip_caption"):
                    pieces.append(f"image: {turn['blip_caption']}")
                if turn.get("query"):
                    pieces.append(f"query: {turn['query']}")
                turn_lookup[str(turn["dia_id"])] = " ".join(piece for piece in pieces if piece)
    return turn_lookup


def _load_official_locomo_benchmark(benchmark_dir: Path, benchmark: str, manifest: dict[str, object]) -> list[BenchmarkSample]:
    source_file = str(manifest.get("source_file", "locomo-main/data/locomo10.json"))
    rows = load_json_rows(benchmark_dir / source_file)
    if not rows:
        return []

    conversation_splits = manifest.get("conversation_splits", {})
    split_to_indexes: dict[str, set[int]] = {}
    if isinstance(conversation_splits, dict):
        for split_name, indexes in conversation_splits.items():
            if isinstance(indexes, list):
                split_to_indexes[str(split_name)] = {int(value) for value in indexes}

    samples: list[BenchmarkSample] = []
    for conversation_index, row in enumerate(rows, start=1):
        conversation = row.get("conversation", {})
        if not isinstance(conversation, dict):
            continue
        split = "test"
        for split_name, indexes in split_to_indexes.items():
            if conversation_index in indexes:
                split = split_name
                break

        history: list[str] = []
        for session_key in _natural_session_keys(conversation):
            session_timestamp = conversation.get(f"{session_key}_date_time")
            for turn in conversation.get(session_key, []):
                if not isinstance(turn, dict):
                    continue
                speaker = str(turn.get("speaker", "speaker"))
                text = str(turn.get("text", "")).strip()
                pieces: list[str] = []
                if isinstance(session_timestamp, str):
                    pieces.append(f"[{session_timestamp}]")
                if text:
                    pieces.append(f"{speaker}: {text}")
                if turn.get("blip_caption"):
                    pieces.append(f"image: {turn['blip_caption']}")
                if turn.get("query"):
                    pieces.append(f"query: {turn['query']}")
                if pieces:
                    history.append(" ".join(pieces))

        turn_lookup = _locomo_turn_lookup(conversation)
        qa_rows = row.get("qa", [])
        if not isinstance(qa_rows, list):
            continue

        for qa_index, qa_row in enumerate(qa_rows, start=1):
            if not isinstance(qa_row, dict):
                continue
            question = qa_row.get("question")
            answer = qa_row.get("answer")
            if not isinstance(question, str):
                continue
            evidence_ids = qa_row.get("evidence", [])
            evidence_texts: list[str] = []
            if isinstance(evidence_ids, list):
                for evidence_id in evidence_ids:
                    text = turn_lookup.get(str(evidence_id))
                    if text:
                        evidence_texts.append(text)

            hints: list[str] = []
            if answer is not None:
                answer_text = str(answer)
            else:
                answer_text = ""
            if answer_text:
                hints.append(answer_text)
            hints.extend(evidence_texts[:2])
            if not hints:
                continue

            category_value = int(qa_row.get("category", 0) or 0)
            semantic_match_min = 0
            if category_value == 1:
                semantic_match_min = 2
            if category_value == 3:
                semantic_match_min = 2

            samples.append(
                BenchmarkSample(
                    benchmark=benchmark,
                    sample_id=f"{row.get('sample_id', benchmark)}-qa-{qa_index:04d}",
                    split=split,
                    user_id=str(row.get("sample_id", f"{benchmark}-sample-{conversation_index:02d}")),
                    session_id=f"{row.get('sample_id', benchmark)}-{split}",
                    history=history,
                    query_text=question,
                    expectation=BenchmarkExpectation(
                        memory_hints=list(dict.fromkeys(hints)),
                        target_rank_max=int(manifest.get("target_rank_max", 3)),
                    ),
                    metadata={
                        "task": f"qa-category-{qa_row.get('category', 'unknown')}",
                        "difficulty": "official",
                        "source": str(manifest.get("dataset", benchmark)),
                        "category": qa_row.get("category"),
                        "evidence_count": len(evidence_texts),
                        "conversation_index": conversation_index,
                        "semantic_match_min": semantic_match_min,
                    },
                )
            )
    return samples


def load_manifest(base_dir: Path, benchmark: str) -> dict[str, object]:
    benchmark_dir = base_dir / benchmark
    manifest_path = benchmark_dir / "manifest.json"
    if not manifest_path.exists():
        return {"dataset": benchmark, "benchmark_id": benchmark, "splits": ["test"], "loader": "local_jsonl"}
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    payload.setdefault("benchmark_id", benchmark)
    payload.setdefault("directory_name", benchmark)
    payload.setdefault("loader", "local_jsonl")
    payload.setdefault("dataset", benchmark)
    payload.setdefault("splits", ["test"])
    return payload


def _load_local_jsonl_benchmark(benchmark_dir: Path, benchmark: str, manifest: dict[str, object]) -> list[BenchmarkSample]:
    samples: list[BenchmarkSample] = []
    split_files = manifest.get("split_files", {})
    for split in manifest.get("splits", ["test"]):
        filename = split_files.get(split, f"{split}.jsonl") if isinstance(split_files, dict) else f"{split}.jsonl"
        rows = load_rows(benchmark_dir / str(filename))
        for row in rows:
            samples.append(_build_sample(row=row, benchmark=benchmark, split=str(split), source=str(manifest.get("dataset", benchmark))))
    return samples


def _load_official_style_benchmark(benchmark_dir: Path, benchmark: str, manifest: dict[str, object]) -> list[BenchmarkSample]:
    samples: list[BenchmarkSample] = []
    split_files = manifest.get("split_files", {})
    source_label = str(manifest.get("dataset", benchmark))
    for split in manifest.get("splits", ["test"]):
        filename = split_files.get(split, f"{split}.json") if isinstance(split_files, dict) else f"{split}.json"
        rows = load_rows(benchmark_dir / str(filename))
        for row in rows:
            samples.append(_build_sample(row=row, benchmark=benchmark, split=str(split), source=source_label))
    return samples


def load_benchmark_splits(base_dir: Path, benchmark: str) -> list[BenchmarkSample]:
    manifest = load_manifest(base_dir=base_dir, benchmark=benchmark)
    benchmark_dir = base_dir / str(manifest.get("directory_name", benchmark))
    loader = str(manifest.get("loader", "local_jsonl"))
    if loader == "local_jsonl":
        return _load_local_jsonl_benchmark(benchmark_dir, benchmark, manifest)
    if loader == "official_locomo_full_v1":
        return _load_official_locomo_benchmark(benchmark_dir, benchmark, manifest)
    if loader in {"official_locomo_v1", "official_langmemeval_v1"}:
        return _load_official_style_benchmark(benchmark_dir, benchmark, manifest)
    raise ValueError(f"Unsupported benchmark loader: {loader}")


def discover_benchmarks(base_dirs: list[Path]) -> dict[str, dict[str, object]]:
    manifests: dict[str, dict[str, object]] = {}
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
        for benchmark_dir in sorted(path for path in base_dir.iterdir() if path.is_dir()):
            manifest_path = benchmark_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = load_manifest(base_dir=base_dir, benchmark=benchmark_dir.name)
            benchmark_id = str(manifest.get("benchmark_id", benchmark_dir.name))
            manifest["directory_name"] = benchmark_dir.name
            manifest["root_dir"] = str(base_dir)
            manifests[benchmark_id] = manifest
    return manifests


def resolve_benchmark_roots(base_dir: Path, extra_roots: list[Path] | None = None) -> list[Path]:
    roots = [base_dir]
    env_value = os.environ.get("MEMORY_SYSTEM_BENCHMARK_EXTRA_ROOTS", "")
    for raw_path in env_value.split(os.pathsep):
        if raw_path.strip():
            roots.append(Path(raw_path.strip()))
    for extra_root in extra_roots or []:
        roots.append(extra_root)
    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = str(root)
        if resolved not in seen:
            seen.add(resolved)
            unique_roots.append(root)
    return unique_roots


def load_all_benchmarks(base_dir: Path, extra_roots: list[Path] | None = None) -> tuple[list[BenchmarkSample], dict[str, dict[str, object]]]:
    roots = resolve_benchmark_roots(base_dir, extra_roots=extra_roots)
    manifests = discover_benchmarks(roots)
    samples: list[BenchmarkSample] = []
    for benchmark_id, manifest in manifests.items():
        root_dir = Path(str(manifest.get("root_dir", base_dir)))
        directory_name = str(manifest.get("directory_name", benchmark_id))
        loaded_samples = load_benchmark_splits(root_dir, benchmark=directory_name)
        for sample in loaded_samples:
            sample.benchmark = benchmark_id
        samples.extend(loaded_samples)
    return samples, manifests


def load_locomo(base_dir: Path) -> list[BenchmarkSample]:
    return load_benchmark_splits(base_dir, benchmark="locomo")


def load_langmemeval(base_dir: Path) -> list[BenchmarkSample]:
    return load_benchmark_splits(base_dir, benchmark="langmemeval")
