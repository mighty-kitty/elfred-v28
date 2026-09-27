from src.memory_system.benchmarks.datasets import load_langmemeval, load_locomo, load_manifest
from src.memory_system.config import AppConfig


def test_benchmark_manifests_match_expanded_local_sets():
    base_dir = AppConfig().paths.data_dir / "benchmarks"

    locomo_manifest = load_manifest(base_dir, "locomo")
    langmemeval_manifest = load_manifest(base_dir, "langmemeval")
    locomo_samples = load_locomo(base_dir)
    langmemeval_samples = load_langmemeval(base_dir)

    assert len(locomo_samples) == sum(locomo_manifest["sample_counts"].values())
    assert len(langmemeval_samples) == sum(langmemeval_manifest["sample_counts"].values())
    assert len(locomo_samples) >= 12
    assert len(langmemeval_samples) >= 12
