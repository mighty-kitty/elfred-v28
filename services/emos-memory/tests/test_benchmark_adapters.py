from src.memory_system.benchmarks.datasets import load_all_benchmarks
from src.memory_system.config import AppConfig


def test_benchmark_discovery_loads_local_and_official_style_fixtures():
    base_dir = AppConfig().paths.data_dir / "benchmarks"
    samples, manifests = load_all_benchmarks(base_dir)

    assert "locomo" in manifests
    assert "langmemeval" in manifests
    assert "locomo_official_fixture" in manifests
    assert "langmemeval_official_fixture" in manifests
    assert len(samples) >= 32
    assert any(sample.sample_id == "locomo-official-dev-001" for sample in samples)
    assert any(sample.sample_id == "langmemeval-official-test-002" for sample in samples)


def test_benchmark_discovery_loads_official_locomo_full_dataset():
    config = AppConfig()
    base_dir = config.paths.data_dir / "benchmarks"
    official_root = base_dir / "official"
    samples, manifests = load_all_benchmarks(base_dir, extra_roots=[official_root])

    assert "locomo_official_full" in manifests
    locomo_official_samples = [sample for sample in samples if sample.benchmark == "locomo_official_full"]
    assert len(locomo_official_samples) == 1986
    assert locomo_official_samples[0].expectation.memory_hints


def test_official_locomo_full_includes_category_5_evidence_backed_questions():
    config = AppConfig()
    base_dir = config.paths.data_dir / "benchmarks"
    official_root = base_dir / "official"
    samples, _ = load_all_benchmarks(base_dir, extra_roots=[official_root])

    locomo_official_samples = [sample for sample in samples if sample.benchmark == "locomo_official_full"]
    category_5_samples = [sample for sample in locomo_official_samples if sample.metadata.get("task") == "qa-category-5"]

    assert len(category_5_samples) == 446
    target = next(sample for sample in category_5_samples if sample.sample_id == "conv-26-qa-0154")
    assert "Researching adoption agencies" in target.expectation.memory_hints[0]
