# Benchmark Protocol

## Supported Benchmark Families

- LoCoMo-style conversational memory evaluation
- LangMemEval-style language memory evaluation

## Dataset Layout

Each benchmark directory is expected to contain:

- `manifest.json`
- one or more split files referenced by the manifest, such as `dev.jsonl`, `test.jsonl`, `raw_dev.json`, or `raw_test.jsonl`

Legacy `samples.jsonl` files are deprecated and should not be used for new runs.

## Sample Schema

Each JSONL row supports:

- `sample_id`
- `split`
- `user_id`
- `session_id`
- `history`
- `query_text`
- `expected_memory_hints`
- `target_rank_max`
- `metadata`
  Typical metadata fields now include `task`, `difficulty`, and `source`.

Official-format adapters currently supported by the loader layer:

- `local_jsonl`
- `official_locomo_v1`
- `official_langmemeval_v1`
- `official_locomo_full_v1`

## Metrics

The benchmark runner reports:

- `hit_at_1`
- `hit_at_3`
- `mrr`
- `pass_at_target_rank`
- `avg_top_score`
- per-benchmark summaries
- per-split summaries
- per-task summaries
- per-difficulty summaries
- multi-backend comparison summaries

Hit and rank checks are computed against the retrieval candidate surface representation, not only the raw utterance text.
This surface representation includes the original memory text plus structured tags and abstractions used by the retriever.

## Output Artifacts

- `logs/benchmark_results.json`
- `logs/benchmark_detailed_results.json`
- `logs/benchmark_report.md`
- `logs/benchmark_comparison.json`
- `logs/benchmark_comparison.md`

## Notes

- The current benchmark datasets include expanded local evaluation sets plus official-format adapter fixtures aligned with LoCoMo and LangMemEval task styles.
- The current formal set contains `32` samples with medium/hard difficulty labels.
- The repository now also includes an import path for the official LoCoMo full QA dataset at `data/benchmarks/official/locomo`.
- `scripts/run_official_locomo.ps1` now defaults to `50` samples so official runs stay scoped until we intentionally expand them.
- `scripts/run_official_locomo_midscale.ps1` is available for stage-gate runs such as `400`-`500` official QA samples.
- The runner now compares `lexical`, `semantic`, `hybrid`, and `embedding_rerank` under isolated runtime storage so backend results do not contaminate each other.
- The runner also supports `--no-consolidation` so we can compare raw retrieval against consolidation-aware retrieval on the same official slice.
- The current benchmark snapshot reaches `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000`, `pass@TargetRank=1.000` on the 32-sample formal set.
- The current official LoCoMo scoped run over `50` samples reaches `hit@1=0.980`, `hit@3=0.980`, `MRR=0.980`, `pass@TargetRank=0.980`.
- On that same official `50`-sample slice, `qa-category-2` currently reaches `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000` after the temporal-reasoning upgrade.
- On that same official `50`-sample slice, `qa-category-3` now also reaches `hit@1=1.000`, `hit@3=1.000`, `MRR=1.000` after adding speaker-aware and inference-aware retrieval.
- Current 2026-04-16 official LoCoMo stage-gate snapshot:
  - `150` samples: `hit@1=0.860`, `hit@3=0.953`, `MRR=0.900`
  - `250` samples: `hit@1=0.796`, `hit@3=0.912`, `MRR=0.847`
  - `320` samples: `hit@1=0.800`, `hit@3=0.931`, `MRR=0.857`
  - `400` samples: `hit@1=0.828`, `hit@3=0.958`, `MRR=0.886`
- Current 2026-04-16 official `400`-sample task snapshot:
  - `qa-category-1`: `hit@1=0.962`, `hit@3=1.000`, `MRR=0.976`
  - `qa-category-2`: `hit@1=0.677`, `hit@3=0.927`, `MRR=0.788`
  - `qa-category-3`: `hit@1=0.708`, `hit@3=0.917`, `MRR=0.806`
  - `qa-category-4`: `hit@1=0.870`, `hit@3=0.965`, `MRR=0.913`
- Current 2026-04-16 official `400`-sample tail-error snapshot:
  - `summary_reasoning = 6`
  - `temporal_reasoning = 8`
  - `inference_reasoning = 2`
  - `retrieval_miss = 1`
- The current best-performing path is no longer the early consolidation-only stack.
  It is now the `embedding_rerank` backend plus:
  - query-aware attribute/object targeting
  - time-aware query expansion
  - stricter summary gating
  - answer-support reranking over the top retrieval candidates
- Additional benchmark roots can be injected with `--benchmark-root` or `MEMORY_SYSTEM_BENCHMARK_EXTRA_ROOTS`.
- If official LoCoMo or LangMemEval assets are available later, they should be converted into the same manifest-plus-splits format.
