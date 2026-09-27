from __future__ import annotations

import base64
from typing import Any

import pytest

import adapter.journal.generator as generator_module
from adapter.hermes_client import HermesError
from adapter.journal.generator import JournalGenerationError, JournalGenerator
from adapter.journal.images import JournalImage


class FakeHermesClient:
    def __init__(self, outcomes: list[str | BaseException]) -> None:
        self.outcomes = list(outcomes)
        self.configurations: list[dict[str, Any]] = []
        self.messages: list[str | list[dict[str, Any]]] = []

    def __call__(
        self,
        base_url: str,
        api_key: str,
        *,
        runtime,
        timeout_seconds: float,
    ) -> FakeHermesClient:
        self.configurations.append(
            {
                "base_url": base_url,
                "api_key": api_key,
                "runtime": runtime,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self

    def complete(self, message: str | list[dict[str, Any]]) -> str:
        self.messages.append(message)
        if not self.outcomes:
            raise AssertionError("unexpected Hermes completion call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _make_generator() -> JournalGenerator:
    return JournalGenerator(
        "http://mock:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        timeout_seconds=30,
        reasoning_effort="low",
    )


def test_generate_uses_hermes_runtime_and_returns_completion(
    monkeypatch,
) -> None:
    client = FakeHermesClient(['{"summary_line":"today"}'])
    monkeypatch.setattr(generator_module, "HermesClient", client)

    result = _make_generator().generate("test prompt")

    assert result == '{"summary_line":"today"}'
    assert client.messages == ["test prompt"]
    assert len(client.configurations) == 1
    configuration = client.configurations[0]
    assert configuration["base_url"] == "http://mock:8642"
    assert configuration["api_key"] == "test-hermes-key"
    assert configuration["timeout_seconds"] == 30
    assert configuration["runtime"].provider == "sub2api"
    assert configuration["runtime"].model == "test-model"
    assert configuration["runtime"].reasoning_effort == "low"


def test_generate_retries_one_transient_hermes_failure(
    monkeypatch,
) -> None:
    client = FakeHermesClient(
        [HermesError("temporary failure"), '{"summary_line":"recovered"}']
    )
    sleeps: list[float] = []
    monkeypatch.setattr(generator_module, "HermesClient", client)
    monkeypatch.setattr(generator_module.time, "sleep", sleeps.append)

    result = _make_generator().generate("test prompt")

    assert result == '{"summary_line":"recovered"}'
    assert client.messages == ["test prompt", "test prompt"]
    assert sleeps == [5]


def test_generate_with_images_uses_vision_runtime_and_image_url_parts(
    monkeypatch,
) -> None:
    image_data = b"\xff\xd8representative-frame\xff\xd9"
    image = JournalImage(
        session_id="a" * 32,
        frame_id="b" * 32,
        created_at="2026-08-02T09:15:00+08:00",
        filename="xiao-20260802091500-frame.jpg",
        mime="image/jpeg",
        data=image_data,
    )
    generator = JournalGenerator(
        "http://mock:8642",
        "test-hermes-key",
        "sub2api",
        "test-model",
        timeout_seconds=30,
        reasoning_effort="low",
        vision_provider_id="sub2api-vision",
        vision_model_id="test-vision-model",
    )
    client = FakeHermesClient(["{}"])
    monkeypatch.setattr(generator_module, "HermesClient", client)

    assert generator.generate_with_images("journal evidence", [image]) == "{}"

    runtime = client.configurations[0]["runtime"]
    assert runtime.provider == "sub2api-vision"
    assert runtime.model == "test-vision-model"
    assert runtime.reasoning_effort == "low"
    message = client.messages[0]
    assert isinstance(message, list)
    assert len(message) == 2
    text_part, image_part = message
    assert text_part["type"] == "text"
    assert "journal evidence" in text_part["text"]
    assert image.filename in text_part["text"]
    assert image.created_at in text_part["text"]
    assert image.session_id in text_part["text"]
    assert "C:\\" not in text_part["text"]
    assert "frame_id" not in text_part["text"]
    assert image_part == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/jpeg;base64,"
            + base64.b64encode(image_data).decode("ascii"),
        },
    }


def test_generate_raises_after_two_hermes_failures(monkeypatch) -> None:
    client = FakeHermesClient(
        [HermesError("first failure"), HermesError("second failure")]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(generator_module, "HermesClient", client)
    monkeypatch.setattr(generator_module.time, "sleep", sleeps.append)

    with pytest.raises(JournalGenerationError, match="after 2 attempts") as captured:
        _make_generator().generate("test")

    assert isinstance(captured.value.__cause__, HermesError)
    assert client.messages == ["test", "test"]
    assert sleeps == [5]
