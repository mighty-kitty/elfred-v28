from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EmotionSignal:
    label: str
    score: float
    triggers: list[str] = field(default_factory=list)


@dataclass
class MemoryEntry:
    text: str
    category: str
    score: float
    user_id: str
    session_id: str
    emotion: str = "\u5e73\u9759"
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MemoryEntry":
        return cls(**value)


@dataclass
class SemanticProfile:
    user_id: str
    facts: dict[str, list[str]] = field(default_factory=dict)
    keywords: dict[str, int] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SemanticProfile":
        return cls(**value)


@dataclass
class MemoryBlock:
    user_id: str
    label: str
    value: str
    description: str = ""
    tier: str = "agent_pinned"
    priority: int = 50
    read_only: bool = False
    updated_at: str = field(default_factory=utc_now)
    source: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MemoryBlock":
        return cls(**value)


@dataclass
class RetrievalCandidate:
    memory_id: str
    text: str
    surface_text: str
    category: str
    score: float
    backend: str
    lexical_score: float
    fuzzy_score: float = 0.0
    semantic_score: float = 0.0
    embedding_score: float = 0.0
    concept_hits: list[str] = field(default_factory=list)
    tag_hits: list[str] = field(default_factory=list)
    keyword_hits: list[str] = field(default_factory=list)
    abstraction_hits: list[str] = field(default_factory=list)
    relation_hits: list[str] = field(default_factory=list)
    attribute_hits: list[str] = field(default_factory=list)
    emotion_bonus: float = 0.0
    recency_bonus: float = 0.0
    profile_bonus: float = 0.0
    abstraction_bonus: float = 0.0
    attribute_bonus: float = 0.0
    summary_bonus: float = 0.0
    graph_bonus: float = 0.0
    rerank_bonus: float = 0.0
    feedback_bonus: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessResult:
    observation: str
    emotion: EmotionSignal
    memory_committed: bool
    recalled_memory: MemoryEntry | None
    retrieval_candidates: list[RetrievalCandidate]
    reflection: str | None
    semantic_profile: SemanticProfile
    episodic_memory_count: int
