from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _default_memory_file() -> Path:
    return Path(
        os.environ.get(
            "MEMORY_SYSTEM_MEMORY_FILE",
            str(Path(__file__).resolve().parents[2] / "data" / "memory_store.json"),
        )
    )


def _is_ascii_safe(path: Path) -> bool:
    return all(ord(char) < 128 for char in str(path))


def _default_sqlite_file() -> Path:
    override = os.environ.get("MEMORY_SYSTEM_SQLITE_FILE")
    if override:
        return Path(override)
    candidate = _default_memory_file().with_suffix(".sqlite3")
    if _is_ascii_safe(candidate):
        return candidate
    return Path(tempfile.gettempdir()) / "EMOS" / "runtime" / candidate.name


@dataclass
class PathsConfig:
    root_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MEMORY_SYSTEM_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data")))
    )
    logs_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MEMORY_SYSTEM_LOGS_DIR", str(Path(__file__).resolve().parents[2] / "logs")))
    )
    delivery_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("MEMORY_SYSTEM_DELIVERY_DIR", str(Path(__file__).resolve().parents[2] / "logs" / "delivery"))
        )
    )
    memory_file: Path = field(default_factory=_default_memory_file)
    sqlite_file: Path = field(default_factory=_default_sqlite_file)
    retrieval_settings_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE",
                str(Path(__file__).resolve().parents[2] / "configs" / "retrieval_settings.json"),
            )
        )
    )
    feedback_store_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MEMORY_SYSTEM_FEEDBACK_STORE_FILE",
                str(Path(__file__).resolve().parents[2] / "data" / "feedback_store.json"),
            )
        )
    )
    interaction_log_file: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MEMORY_SYSTEM_INTERACTION_LOG_FILE",
                str(Path(__file__).resolve().parents[2] / "logs" / "memory_interactions.jsonl"),
            )
        )
    )
    offline_eval_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "MEMORY_SYSTEM_OFFLINE_EVAL_DIR",
                str(Path(__file__).resolve().parents[2] / "logs" / "offline_eval"),
            )
        )
    )


@dataclass
class MemoryConfig:
    stm_max_turns: int = 6
    reflection_interval: int = 3
    emotion_threshold: float = 0.45
    recall_top_k: int = 3
    dream_decay: float = 0.9
    event_keywords: tuple[str, ...] = (
        "\u8003\u8bd5",
        "\u538b\u529b",
        "\u6d3b\u52a8",
        "\u5931\u8d25",
        "\u60c5\u7eea",
        "\u52a0\u73ed",
        "\u5931\u7720",
        "\u5b64\u72ec",
        "\u56de\u5fc6",
        "\u4e94\u6708\u5929",
    )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv_tuple(name: str) -> tuple[str, ...]:
    value = os.environ.get(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass
class SecurityConfig:
    require_write_auth: bool = field(default_factory=lambda: _env_bool("MEMORY_SYSTEM_REQUIRE_WRITE_AUTH", False))
    write_auth_secret: str = field(default_factory=lambda: os.environ.get("MEMORY_SYSTEM_WRITE_AUTH_SECRET", ""))
    write_auth_previous_secrets: tuple[str, ...] = field(
        default_factory=lambda: _env_csv_tuple("MEMORY_SYSTEM_WRITE_AUTH_PREVIOUS_SECRETS")
    )
    write_auth_max_age_seconds: int = field(
        default_factory=lambda: int(os.environ.get("MEMORY_SYSTEM_WRITE_AUTH_MAX_AGE_SECONDS", "300"))
    )


@dataclass
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    storage_backend: str = field(default_factory=lambda: os.environ.get("MEMORY_SYSTEM_STORAGE_BACKEND", "auto"))
    log_level: str = "INFO"


def ensure_workspace(config: AppConfig) -> None:
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
    config.paths.delivery_dir.mkdir(parents=True, exist_ok=True)
    config.paths.memory_file.parent.mkdir(parents=True, exist_ok=True)
    config.paths.sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    config.paths.retrieval_settings_file.parent.mkdir(parents=True, exist_ok=True)
    config.paths.feedback_store_file.parent.mkdir(parents=True, exist_ok=True)
    config.paths.interaction_log_file.parent.mkdir(parents=True, exist_ok=True)
    config.paths.offline_eval_dir.mkdir(parents=True, exist_ok=True)
