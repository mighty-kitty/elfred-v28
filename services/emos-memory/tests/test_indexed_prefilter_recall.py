from src.memory_system.config import AppConfig
from src.memory_system.emotion_engine import CALM_EMOTION
from src.memory_system.memory_repository import MemoryRepository
from src.memory_system.models import MemoryEntry


def _config(tmp_path):
    config = AppConfig()
    config.paths.data_dir = tmp_path / "data"
    config.paths.logs_dir = tmp_path / "logs"
    config.paths.delivery_dir = tmp_path / "delivery"
    config.paths.memory_file = config.paths.data_dir / "memory.json"
    config.paths.sqlite_file = config.paths.data_dir / "memory.sqlite3"
    config.paths.feedback_store_file = config.paths.data_dir / "feedback.json"
    config.paths.interaction_log_file = config.paths.logs_dir / "interactions.jsonl"
    config.paths.offline_eval_dir = config.paths.logs_dir / "offline_eval"
    for path in (
        config.paths.data_dir,
        config.paths.logs_dir,
        config.paths.delivery_dir,
        config.paths.offline_eval_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    config.storage_backend = "json"
    return config


def test_indexed_prefilter_keeps_relevant_memory_and_uses_cache(tmp_path):
    repo = MemoryRepository(
        _config(tmp_path),
        retrieval_settings_override={
            "backend": "hybrid",
            "prefilter": {
                "enabled": True,
                "min_records": 1,
                "candidate_pool": 8,
                "recency_pool": 2,
            },
        },
    )
    user_id = "pytest-indexed-prefilter-user"
    session_id = "pytest-indexed-prefilter-session"

    for index in range(60):
        repo.add_memory(
            MemoryEntry(
                text=f"Background preference {index}: project-{index} uses quiet blue notes.",
                category="episodic",
                score=0.5,
                user_id=user_id,
                session_id=session_id,
                emotion=CALM_EMOTION,
            )
        )
    target = MemoryEntry(
        text="The user prefers saffron lantern handoff notes for the atlas migration.",
        category="episodic",
        score=0.9,
        user_id=user_id,
        session_id=session_id,
        emotion=CALM_EMOTION,
        tags=["atlas_migration"],
        metadata={"attributes": ["attr:atlas_migration"]},
    )
    repo.add_memory(target)

    candidates = repo.recall_with_trace(
        user_id=user_id,
        text="What handoff notes does the user prefer for the atlas migration?",
        emotion=CALM_EMOTION,
        top_k=5,
    )

    assert candidates
    assert any(candidate.memory_id == target.memory_id for candidate in candidates)
    report = repo._last_retrieval_prefilter_report
    assert report["used"] is True
    assert report["cache_rebuilt"] is True
    assert report["selected_record_count"] < report["active_record_count"]

    repo.recall_with_trace(
        user_id=user_id,
        text="What handoff notes does the user prefer for the atlas migration?",
        emotion=CALM_EMOTION,
        top_k=5,
    )

    assert repo._last_retrieval_prefilter_report["cache_rebuilt"] is False
