from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from adapter.identity import resolve_adapter_database_path


_PRODUCT_ENV_PREFIX = "ELFRED"
_PREVIOUS_ENV_PREFIX = bytes.fromhex("616c66726564").decode("ascii").upper()


def _env_value(name: str, default: str | None = None) -> str | None:
    current = os.getenv(name)
    if current is not None:
        return current
    product_prefix = f"{_PRODUCT_ENV_PREFIX}_"
    if name.startswith(product_prefix):
        previous_name = f"{_PREVIOUS_ENV_PREFIX}_{name.removeprefix(product_prefix)}"
        return os.getenv(previous_name, default)
    return default


def _adapter_host() -> str:
    host = str(_env_value("ELFRED_ADAPTER_HOST", "127.0.0.1") or "").strip()
    if host.casefold() == "localhost":
        return host
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ValueError(
            "ELFRED_ADAPTER_HOST must be a loopback address because the local "
            "Adapter exposes authenticated Codex capabilities."
        )
    return host


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env_value(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip() for item in (_env_value(name, "") or "").split(",") if item.strip()
    )


@dataclass(frozen=True)
class Settings:
    db_path: Path
    freetodo_base_url: str
    observer_base_url: str
    skill_root: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    active_backend: str = "freetodo"
    llm_provider: str = "deterministic"
    active_task_threshold: float = 0.70
    request_timeout_seconds: float = 8.0
    codex_executable: str = "codex"
    codex_home: Path | None = None
    codex_stderr_log: Path | None = None
    # Deprecated migration fields; production never reads them.
    hermes_base_url: str = ""
    hermes_api_key: str = ""
    llm_provider_id: str = ""
    llm_model_id: str = ""
    llm_reasoning_effort: str = ""
    llm_cloud_consent: bool = False
    agent_deepseek_enabled: bool = False
    task_analysis_cloud_apps: tuple[str, ...] = ()
    llm_timeout_seconds: float = 120.0
    analysis_worker_interval_seconds: float = 0.0
    analysis_lease_seconds: int = 180
    analysis_max_attempts: int = 4
    analysis_retry_base_seconds: float = 5.0
    task_merge_confidence_threshold: float = 0.86
    task_candidate_limit: int = 30
    observer_auto_sync_interval_seconds: float = 0.0
    observer_auto_sync_limit: int = 50
    observer_auto_sync_backfill: bool = False
    skill_generation_provider: str = "auto"
    skill_model_provider_id: str = ""
    skill_model_id: str = ""
    skill_vision_provider_id: str = ""
    skill_vision_model_id: str = ""
    skill_include_screenshots: bool = True
    skill_max_model_images: int = 24
    skill_max_evidence_chars: int = 60000
    skill_passive_enabled: bool = False
    skill_passive_interval_seconds: float = 15.0
    skill_passive_min_tasks: int = 2
    skill_passive_max_tasks: int = 20
    skill_passive_similarity_threshold: float = 0.38
    skill_match_min_score: float = 0.20
    skill_auto_execute_min_score: float = 0.55
    skill_classification_provider: str = "auto"
    skill_classification_max_chars: int = 2400
    # 日报
    journal_enabled: bool = False
    journal_max_events: int = 30
    journal_generation_hour: int = 0
    journal_timezone: str = "+08:00"
    journal_vision_provider_id: str = ""
    journal_vision_model_id: str = ""
    journal_max_model_images: int = 6
    journal_max_image_bytes: int = 3 * 1024 * 1024
    journal_worker_interval_seconds: float = 2.0
    journal_lease_seconds: int = 600
    journal_max_attempts: int = 6
    journal_retry_base_seconds: float = 10.0
    # Journal -> four logical hardware adapters
    hardware_output_enabled: bool = True
    hardware_output_auto_plan_on_journal: bool = True
    hardware_output_config_path: Path | None = None
    hardware_output_llm_enabled: bool = False
    hardware_output_worker_interval_seconds: float = 0.5
    hardware_output_http_timeout_seconds: float = 5.0
    hardware_output_max_attempts: int = 2
    k3_log_url: str = ""
    k3_log_hmac_secret: str = ""
    k3_log_timeout_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        host = _adapter_host()
        root = Path(__file__).resolve().parents[1]
        repo_root = Path(__file__).resolve().parents[3]
        db = resolve_adapter_database_path(
            Path(
                _env_value(
                    "ELFRED_ADAPTER_DB",
                    str(root / "data" / "elfred_adapter.db"),
                )
            )
        )
        skill_root = Path(_env_value("ELFRED_SKILLS_DIR", str(repo_root / "skills")))
        hardware_config = Path(
            _env_value(
                "ELFRED_HARDWARE_CONFIG",
                str(root / "config" / "hardware_output.local.json"),
            )
        )
        return cls(
            db_path=db.resolve(),
            freetodo_base_url=_env_value(
                "FREETODO_BASE_URL", "http://127.0.0.1:8001"
            ).rstrip("/"),
            observer_base_url=_env_value(
                "OBSERVER_BASE_URL", "http://127.0.0.1:8000"
            ).rstrip("/"),
            skill_root=skill_root.resolve(),
            host=host,
            port=int(_env_value("ELFRED_ADAPTER_PORT", "8765")),
            active_backend=_env_value("ELFRED_CONTEXT_BACKEND", "freetodo"),
            llm_provider=_env_value("ELFRED_LLM_PROVIDER", "deterministic"),
            active_task_threshold=float(
                _env_value("ELFRED_ACTIVE_TASK_THRESHOLD", "0.70")
            ),
            request_timeout_seconds=float(_env_value("ELFRED_HTTP_TIMEOUT", "8")),
            codex_executable=_env_value("ELFRED_CODEX_EXE", "codex"),
            codex_home=Path(
                _env_value("ELFRED_CODEX_HOME", str(root / ".demo" / "codex"))
            ).resolve(),
            codex_stderr_log=Path(
                _env_value(
                    "ELFRED_CODEX_STDERR_LOG",
                    str(root / ".demo" / "logs" / "codex-app-server.err.log"),
                )
            ).resolve(),
            llm_provider_id=_env_value("ELFRED_LLM_PROVIDER_ID", ""),
            llm_model_id=_env_value("ELFRED_LLM_MODEL", ""),
            llm_reasoning_effort=_env_value("ELFRED_LLM_REASONING_EFFORT", ""),
            llm_cloud_consent=_env_bool("ELFRED_LLM_CLOUD_CONSENT", False),
            agent_deepseek_enabled=_env_bool(
                "ELFRED_AGENT_DEEPSEEK_ENABLED", False
            ),
            task_analysis_cloud_apps=_env_csv("ELFRED_TASK_ANALYSIS_CLOUD_APPS"),
            llm_timeout_seconds=float(_env_value("ELFRED_LLM_TIMEOUT", "120")),
            analysis_worker_interval_seconds=float(
                _env_value("ELFRED_ANALYSIS_WORKER_INTERVAL", "0")
            ),
            analysis_lease_seconds=int(
                _env_value("ELFRED_ANALYSIS_LEASE_SECONDS", "180")
            ),
            analysis_max_attempts=int(_env_value("ELFRED_ANALYSIS_MAX_ATTEMPTS", "4")),
            analysis_retry_base_seconds=float(
                _env_value("ELFRED_ANALYSIS_RETRY_BASE_SECONDS", "5")
            ),
            task_merge_confidence_threshold=float(
                _env_value("ELFRED_TASK_MERGE_CONFIDENCE", "0.86")
            ),
            task_candidate_limit=int(_env_value("ELFRED_TASK_CANDIDATE_LIMIT", "30")),
            observer_auto_sync_interval_seconds=float(
                _env_value("ELFRED_OBSERVER_AUTO_SYNC_INTERVAL", "0")
            ),
            observer_auto_sync_limit=int(
                _env_value("ELFRED_OBSERVER_AUTO_SYNC_LIMIT", "50")
            ),
            observer_auto_sync_backfill=_env_bool(
                "ELFRED_OBSERVER_AUTO_SYNC_BACKFILL", False
            ),
            skill_generation_provider=_env_value(
                "ELFRED_SKILL_GENERATION_PROVIDER", "auto"
            ),
            skill_model_provider_id=_env_value("ELFRED_SKILL_MODEL_PROVIDER_ID", ""),
            skill_model_id=_env_value("ELFRED_SKILL_MODEL_ID", ""),
            skill_vision_provider_id=_env_value("ELFRED_SKILL_VISION_PROVIDER_ID", ""),
            skill_vision_model_id=_env_value("ELFRED_SKILL_VISION_MODEL_ID", ""),
            skill_include_screenshots=_env_bool(
                "ELFRED_SKILL_INCLUDE_SCREENSHOTS", True
            ),
            skill_max_model_images=int(
                _env_value("ELFRED_SKILL_MAX_MODEL_IMAGES", "24")
            ),
            skill_max_evidence_chars=int(
                _env_value("ELFRED_SKILL_MAX_EVIDENCE_CHARS", "60000")
            ),
            skill_passive_enabled=_env_bool("ELFRED_SKILL_PASSIVE_ENABLED", True),
            skill_passive_interval_seconds=float(
                _env_value("ELFRED_SKILL_PASSIVE_INTERVAL", "15")
            ),
            skill_passive_min_tasks=int(
                _env_value("ELFRED_SKILL_PASSIVE_MIN_TASKS", "2")
            ),
            skill_passive_max_tasks=int(
                _env_value("ELFRED_SKILL_PASSIVE_MAX_TASKS", "20")
            ),
            skill_passive_similarity_threshold=float(
                _env_value("ELFRED_SKILL_PASSIVE_SIMILARITY", "0.38")
            ),
            skill_match_min_score=float(
                _env_value("ELFRED_SKILL_MATCH_MIN_SCORE", "0.20")
            ),
            skill_auto_execute_min_score=float(
                _env_value("ELFRED_SKILL_AUTO_EXECUTE_MIN_SCORE", "0.55")
            ),
            skill_classification_provider=_env_value(
                "ELFRED_SKILL_CLASSIFICATION_PROVIDER", "auto"
            ),
            skill_classification_max_chars=int(
                _env_value("ELFRED_SKILL_CLASSIFICATION_MAX_CHARS", "2400")
            ),
            journal_enabled=_env_bool("ELFRED_JOURNAL_ENABLED", False),
            journal_max_events=int(_env_value("ELFRED_JOURNAL_MAX_EVENTS", "30")),
            journal_generation_hour=int(
                _env_value("ELFRED_JOURNAL_GENERATION_HOUR", "0")
            ),
            journal_timezone=_env_value("ELFRED_JOURNAL_TIMEZONE", "+08:00"),
            journal_vision_provider_id=_env_value(
                "ELFRED_JOURNAL_VISION_PROVIDER_ID",
                _env_value("ELFRED_SKILL_VISION_PROVIDER_ID", ""),
            ),
            journal_vision_model_id=_env_value(
                "ELFRED_JOURNAL_VISION_MODEL_ID",
                _env_value("ELFRED_SKILL_VISION_MODEL_ID", ""),
            ),
            journal_max_model_images=int(
                _env_value("ELFRED_JOURNAL_MAX_MODEL_IMAGES", "6")
            ),
            journal_max_image_bytes=int(
                _env_value("ELFRED_JOURNAL_MAX_IMAGE_BYTES", str(3 * 1024 * 1024))
            ),
            journal_worker_interval_seconds=float(
                _env_value("ELFRED_JOURNAL_WORKER_INTERVAL", "2")
            ),
            journal_lease_seconds=int(
                _env_value("ELFRED_JOURNAL_LEASE_SECONDS", "600")
            ),
            journal_max_attempts=int(_env_value("ELFRED_JOURNAL_MAX_ATTEMPTS", "6")),
            journal_retry_base_seconds=float(
                _env_value("ELFRED_JOURNAL_RETRY_BASE_SECONDS", "10")
            ),
            hardware_output_enabled=_env_bool(
                "ELFRED_HARDWARE_OUTPUT_ENABLED",
                True,
            ),
            hardware_output_auto_plan_on_journal=_env_bool(
                "ELFRED_HARDWARE_AUTO_PLAN_ON_JOURNAL",
                True,
            ),
            hardware_output_config_path=hardware_config.resolve(),
            hardware_output_llm_enabled=_env_bool(
                "ELFRED_HARDWARE_LLM_ENABLED",
                False,
            ),
            hardware_output_worker_interval_seconds=float(
                _env_value("ELFRED_HARDWARE_WORKER_INTERVAL", "0.5")
            ),
            hardware_output_http_timeout_seconds=float(
                _env_value("ELFRED_HARDWARE_HTTP_TIMEOUT", "5")
            ),
            hardware_output_max_attempts=int(
                _env_value("ELFRED_HARDWARE_MAX_ATTEMPTS", "2")
            ),
            k3_log_url=_env_value("ELFRED_K3_LOG_URL", "").rstrip("/"),
            k3_log_hmac_secret=_env_value("ELFRED_K3_LOG_HMAC_SECRET", ""),
            k3_log_timeout_seconds=float(_env_value("ELFRED_K3_LOG_TIMEOUT", "2")),
        )
