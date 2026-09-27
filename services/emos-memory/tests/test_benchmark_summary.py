from src.memory_system.benchmarks.base import BenchmarkResult
from src.memory_system.benchmarks.runner import build_summary


def test_benchmark_summary_exposes_split_and_benchmark_metrics():
    results = [
        BenchmarkResult(
            backend="hybrid",
            benchmark="locomo",
            sample_id="a",
            split="dev",
            task="episodic-recall",
            difficulty="hard",
            hit_at_1=True,
            hit_at_3=True,
            reciprocal_rank=1.0,
            matched_rank=1,
            meets_target_rank=True,
            target_rank_max=1,
            top_score=1.2,
            recalled_text="考试",
            expected_memory_hints=["考试"],
        ),
        BenchmarkResult(
            backend="hybrid",
            benchmark="langmemeval",
            sample_id="b",
            split="test",
            task="event-recall",
            difficulty="medium",
            hit_at_1=False,
            hit_at_3=True,
            reciprocal_rank=0.5,
            matched_rank=2,
            meets_target_rank=True,
            target_rank_max=2,
            top_score=0.8,
            recalled_text="活动",
            expected_memory_hints=["活动"],
        ),
    ]

    summary = build_summary(results, backend_name="hybrid")

    assert summary["total"] == 2
    assert summary["backend"] == "hybrid"
    assert "locomo" in summary["per_benchmark"]
    assert "dev" in summary["per_split"]
    assert "episodic-recall" in summary["per_task"]
    assert "hard" in summary["per_difficulty"]
    assert summary["pass_at_target_rank"] == 1.0
