from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchmarkExpectation:
    memory_hints: list[str]
    target_rank_max: int = 1


@dataclass
class BenchmarkSample:
    benchmark: str
    sample_id: str
    split: str
    user_id: str
    session_id: str
    history: list[str]
    query_text: str
    expectation: BenchmarkExpectation
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    backend: str
    benchmark: str
    sample_id: str
    split: str
    task: str
    difficulty: str
    hit_at_1: bool
    hit_at_3: bool
    reciprocal_rank: float
    matched_rank: int | None
    meets_target_rank: bool
    target_rank_max: int
    top_score: float
    recalled_text: str | None
    expected_memory_hints: list[str]
    recalled_surface_text: str | None = None
    conversation_key: str | None = None
    error_category: str | None = None
