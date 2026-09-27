"""config.py 单元测试 — env bool/csv 解析 + Settings 默认值"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from adapter.config import Settings, _adapter_host, _env_bool, _env_csv


def _previous_env_name(suffix: str) -> str:
    prefix = bytes.fromhex("616c66726564").decode("ascii").upper()
    return f"{prefix}_{suffix}"


def _settings_env(tmp_path: Path, **values: str) -> dict[str, str]:
    return {"ELFRED_ADAPTER_DB": str(tmp_path / "adapter.db"), **values}


# ── _env_bool ──


def test_env_bool_true_values():
    with mock.patch.dict(os.environ, {"TEST_VAR": "true"}, clear=True):
        assert _env_bool("TEST_VAR") is True
    with mock.patch.dict(os.environ, {"TEST_VAR": "1"}, clear=True):
        assert _env_bool("TEST_VAR") is True
    with mock.patch.dict(os.environ, {"TEST_VAR": "yes"}, clear=True):
        assert _env_bool("TEST_VAR") is True
    with mock.patch.dict(os.environ, {"TEST_VAR": "on"}, clear=True):
        assert _env_bool("TEST_VAR") is True
    with mock.patch.dict(os.environ, {"TEST_VAR": "TRUE"}, clear=True):
        assert _env_bool("TEST_VAR") is True


def test_env_bool_false_values():
    with mock.patch.dict(os.environ, {"TEST_VAR": "false"}, clear=True):
        assert _env_bool("TEST_VAR") is False
    with mock.patch.dict(os.environ, {"TEST_VAR": "0"}, clear=True):
        assert _env_bool("TEST_VAR") is False
    with mock.patch.dict(os.environ, {"TEST_VAR": "no"}, clear=True):
        assert _env_bool("TEST_VAR") is False


def test_env_bool_default():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _env_bool("MISSING", default=False) is False
        assert _env_bool("MISSING", default=True) is True


# ── _env_csv ──


def test_env_csv_parses_comma_separated():
    with mock.patch.dict(os.environ, {"TEST_CSV": "a, b , c"}, clear=True):
        assert _env_csv("TEST_CSV") == ("a", "b", "c")


def test_env_csv_empty():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert _env_csv("MISSING") == ()


# ── Settings.from_env defaults ──


def test_settings_defaults(tmp_path: Path):
    with mock.patch.dict(os.environ, _settings_env(tmp_path), clear=True):
        s = Settings.from_env()
        assert s.freetodo_base_url == "http://127.0.0.1:8001"
        assert s.observer_base_url == "http://127.0.0.1:8000"
        assert s.llm_provider == "deterministic"
        assert s.agent_deepseek_enabled is False
        assert s.journal_enabled is False
        assert s.hardware_output_enabled is True
        assert s.journal_generation_hour == 0
        assert s.journal_timezone == "+08:00"
        assert s.journal_vision_provider_id == ""
        assert s.journal_vision_model_id == ""
        assert s.journal_max_model_images == 6
        assert s.journal_max_image_bytes == 3 * 1024 * 1024
        assert s.journal_max_events == 30
        assert s.analysis_retry_base_seconds == 5.0


def test_settings_env_override(tmp_path: Path):
    with mock.patch.dict(
        os.environ,
        _settings_env(
            tmp_path,
            ELFRED_JOURNAL_ENABLED="true",
            ELFRED_LLM_PROVIDER="hermes",
            ELFRED_JOURNAL_MAX_EVENTS="50",
            ELFRED_ANALYSIS_RETRY_BASE_SECONDS="30",
            ELFRED_JOURNAL_VISION_PROVIDER_ID="vision-provider",
            ELFRED_JOURNAL_VISION_MODEL_ID="vision-model",
            ELFRED_JOURNAL_MAX_MODEL_IMAGES="4",
            ELFRED_JOURNAL_MAX_IMAGE_BYTES="1048576",
            ELFRED_AGENT_DEEPSEEK_ENABLED="true",
        ),
        clear=True,
    ):
        s = Settings.from_env()
        assert s.journal_enabled is True
        assert s.llm_provider == "hermes"
        assert s.journal_max_events == 50
        assert s.analysis_retry_base_seconds == 30.0
        assert s.journal_vision_provider_id == "vision-provider"
        assert s.journal_vision_model_id == "vision-model"
        assert s.journal_max_model_images == 4
        assert s.journal_max_image_bytes == 1_048_576
        assert s.agent_deepseek_enabled is True


def test_settings_journal_vision_falls_back_to_skill_vision_model(tmp_path: Path):
    with mock.patch.dict(
        os.environ,
        _settings_env(
            tmp_path,
            ELFRED_SKILL_VISION_PROVIDER_ID="shared-vision-provider",
            ELFRED_SKILL_VISION_MODEL_ID="shared-vision-model",
        ),
        clear=True,
    ):
        settings = Settings.from_env()

    assert settings.journal_vision_provider_id == "shared-vision-provider"
    assert settings.journal_vision_model_id == "shared-vision-model"


def test_settings_hardware_output_env(tmp_path: Path):
    with mock.patch.dict(
        os.environ,
        _settings_env(
            tmp_path,
            ELFRED_HARDWARE_OUTPUT_ENABLED="false",
            ELFRED_HARDWARE_AUTO_PLAN_ON_JOURNAL="false",
            ELFRED_HARDWARE_LLM_ENABLED="true",
        ),
        clear=True,
    ):
        s = Settings.from_env()
        assert s.hardware_output_enabled is False
        assert s.hardware_output_auto_plan_on_journal is False
        assert s.hardware_output_llm_enabled is True


def test_previous_product_environment_is_a_read_only_upgrade_fallback(tmp_path: Path):
    database = tmp_path / "previous-adapter.db"
    hardware = tmp_path / "previous-hardware.json"
    with mock.patch.dict(
        os.environ,
        {
            _previous_env_name("ADAPTER_DB"): str(database),
            _previous_env_name("HARDWARE_CONFIG"): str(hardware),
            _previous_env_name("JOURNAL_ENABLED"): "true",
        },
        clear=True,
    ):
        settings = Settings.from_env()

    assert settings.db_path == database.resolve()
    assert settings.hardware_output_config_path == hardware.resolve()
    assert settings.journal_enabled is True


def test_current_product_environment_wins_over_previous_name(tmp_path: Path):
    with mock.patch.dict(
        os.environ,
        {
            _previous_env_name("JOURNAL_ENABLED"): "false",
            "ELFRED_JOURNAL_ENABLED": "true",
            "ELFRED_ADAPTER_DB": str(tmp_path / "adapter.db"),
        },
        clear=True,
    ):
        settings = Settings.from_env()

    assert settings.journal_enabled is True


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.20.30.40", "::1"])
def test_adapter_host_accepts_only_explicit_loopback_hosts(host: str):
    with mock.patch.dict(os.environ, {"ELFRED_ADAPTER_HOST": host}, clear=True):
        assert _adapter_host() == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.3.6", "adapter.example.com", ""])
def test_adapter_host_rejects_network_exposure(host: str):
    with (
        mock.patch.dict(os.environ, {"ELFRED_ADAPTER_HOST": host}, clear=True),
        mock.patch("adapter.config.resolve_adapter_database_path") as resolve_database,
    ):
        with pytest.raises(ValueError, match="loopback"):
            Settings.from_env()
        resolve_database.assert_not_called()
