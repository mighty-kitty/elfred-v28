from src.memory_system.benchmarks.base import BenchmarkResult
from src.memory_system.benchmarks.runner import build_summary


def test_benchmark_summary_includes_conversation_and_error_taxonomy():
    results = [
        BenchmarkResult(
            backend="embedding_rerank",
            benchmark="locomo_official_full",
            sample_id="a",
            split="test",
            task="qa-category-4",
            difficulty="official",
            hit_at_1=False,
            hit_at_3=False,
            reciprocal_rank=0.0,
            matched_rank=None,
            meets_target_rank=False,
            target_rank_max=3,
            top_score=0.4,
            recalled_text=None,
            expected_memory_hints=["self-care"],
            recalled_surface_text=None,
            conversation_key="6",
            error_category="summary_reasoning",
        ),
        BenchmarkResult(
            backend="embedding_rerank",
            benchmark="locomo_official_full",
            sample_id="b",
            split="test",
            task="qa-category-2",
            difficulty="official",
            hit_at_1=True,
            hit_at_3=True,
            reciprocal_rank=1.0,
            matched_rank=1,
            meets_target_rank=True,
            target_rank_max=3,
            top_score=1.3,
            recalled_text="10 July 2023",
            expected_memory_hints=["10 July 2023"],
            recalled_surface_text="10 July 2023",
            conversation_key="6",
            error_category=None,
        ),
    ]

    summary = build_summary(results, backend_name="embedding_rerank")

    assert "6" in summary["per_conversation"]
    assert "summary_reasoning" in summary["error_taxonomy"]
    assert summary["error_taxonomy"]["summary_reasoning"]["total"] == 1
