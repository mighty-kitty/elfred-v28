from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter.agent_routes import register_agent_routes
from adapter.config import Settings
from adapter.codex_client import CodexRuntime
from adapter.hermes_client import HermesError


class FakeHermes:
    def __init__(self) -> None:
        self.sources: list[str] = []
        self.stream_messages: list[tuple[str, str]] = []
        self.titles = {"session-1": "Work", "session-2": ""}
        self.completed_prompts: list[str] = []
        self.created_runtimes: list[HermesRuntime | None] = []
        self.selected_runtimes: list[tuple[str, HermesRuntime]] = []
        self.chat_inherit_flags: list[bool] = []
        self.stream_inherit_flags: list[bool] = []
        self.interruptions: list[str] = []

    def health(self, *, detailed: bool = False) -> dict[str, Any]:
        assert detailed is True
        return {"status": "ready"}

    def list_sessions(
        self, *, source: str, limit: int, offset: int
    ) -> dict[str, Any]:
        self.sources.append(source)
        assert limit == 200
        if offset:
            return {"data": [], "has_more": False}
        return {
            "data": [
                {
                    "id": "session-1",
                    "title": "Work",
                    "started_at": 1_780_000_000,
                    "last_active": 1_780_000_100,
                    "source": "hermes_browser",
                    "model": "configured-model",
                    "system_prompt": "must not escape",
                }
            ],
            "has_more": False,
        }

    def create_session(
        self, *, source: str, runtime: HermesRuntime | None = None
    ) -> dict[str, Any]:
        self.sources.append(source)
        self.created_runtimes.append(runtime)
        return {
            "id": "session-2",
            "started_at": 1_780_000_200,
            "model": runtime.model if runtime else "configured-model",
        }

    def set_session_model(
        self, session_id: str, runtime: HermesRuntime
    ) -> dict[str, Any]:
        self.selected_runtimes.append((session_id, runtime))
        return {"model": runtime.model, "provider": runtime.provider}

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        assert session_id == "session-1"
        return [
            {"id": "m1", "role": "user", "content": "hello"},
            {
                "id": "m2",
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
                "reasoning": "bounded reasoning",
            },
        ]

    def get_session(self, session_id: str) -> dict[str, Any]:
        return {
            "id": session_id,
            "title": self.titles.get(session_id, ""),
            "started_at": 1_780_000_000,
            "model": "configured-model",
        }

    def complete(self, message: str, *, instructions: str | None = None) -> str:
        self.completed_prompts.append(message)
        assert instructions
        return "修复任务看板状态"

    def update_session(self, session_id: str, *, title: str) -> dict[str, Any]:
        self.titles[session_id] = title
        return {
            "id": session_id,
            "title": title,
            "started_at": 1_780_000_000,
            "model": "configured-model",
        }

    def delete_session(self, session_id: str) -> bool:
        return session_id == "session-1"

    def interrupt_chat(self, session_id: str) -> bool:
        self.interruptions.append(session_id)
        return session_id == "session-1"

    def chat(
        self,
        session_id: str,
        message: str,
        *,
        inherit_session_runtime: bool = False,
    ) -> dict[str, Any]:
        self.chat_inherit_flags.append(inherit_session_runtime)
        return {"message": {"role": "assistant", "content": message.upper()}}

    def stream_chat(
        self,
        session_id: str,
        message: str,
        *,
        inherit_session_runtime: bool = False,
    ) -> io.BytesIO:
        self.stream_inherit_flags.append(inherit_session_runtime)
        self.stream_messages.append((session_id, message))
        return io.BytesIO(
            b"event: assistant.delta\n"
            b'data: {"delta":"hi"}\n\n'
            b"event: done\n"
            b"data: {}\n\n"
        )

    @staticmethod
    def iter_sse(stream: io.BytesIO):
        from adapter.hermes_client import HermesClient

        return HermesClient.iter_sse(stream)


def make_client(
    tmp_path: Path, hermes: FakeHermes, *, deepseek_enabled: bool = False
) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "adapter.db",
        freetodo_base_url="http://127.0.0.1:8001",
        observer_base_url="http://127.0.0.1:8000",
        llm_provider="hermes",
        llm_provider_id="custom-provider",
        hermes_api_key="local-key-that-is-secret",
        llm_model_id="configured-model",
        agent_deepseek_enabled=deepseek_enabled,
    )
    app = FastAPI()
    register_agent_routes(
        app,
        settings,
        "/v1/elfred",
        client=hermes,  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_agent_bff_normalizes_sessions_messages_and_never_exposes_key(
    tmp_path: Path,
) -> None:
    hermes = FakeHermes()
    client = make_client(tmp_path, hermes)

    health = client.get("/v1/elfred/agent/health")
    sessions = client.get("/v1/elfred/agent/sessions")
    created = client.post("/v1/elfred/agent/sessions")
    messages = client.get("/v1/elfred/agent/sessions/session-1/messages")

    assert health.status_code == 200
    assert "local-key-that-is-secret" not in health.text
    assert health.json()["harness"] == "codex"
    assert sessions.json()["sessions"] == [
        {
            "id": "session-1",
            "title": "Work",
            "created_at": "2026-05-28T20:26:40+00:00",
            "updated_at": "2026-05-28T20:28:20+00:00",
            "model_id": "gpt",
        }
    ]
    assert created.status_code == 201
    assert hermes.sources == ["elfred_browser", "elfred_browser"]
    assert messages.json()["messages"][1] == {
        "id": "m2",
        "role": "assistant",
        "content": "done",
        "reasoning": "bounded reasoning",
    }


def test_agent_bff_crud_and_named_stream(tmp_path: Path) -> None:
    hermes = FakeHermes()
    client = make_client(tmp_path, hermes)

    renamed = client.patch(
        "/v1/elfred/agent/sessions/session-1", json={"title": "Renamed"}
    )
    chatted = client.post(
        "/v1/elfred/agent/sessions/session-1/chat", json={"message": "hello"}
    )
    streamed = client.post(
        "/v1/elfred/agent/sessions/session-1/chat/stream",
        json={"message": "stream me"},
    )
    interrupted = client.post(
        "/v1/elfred/agent/sessions/session-1/chat/interrupt"
    )
    deleted = client.delete("/v1/elfred/agent/sessions/session-1")

    assert renamed.json()["title"] == "Renamed"
    assert chatted.json()["content"] == "HELLO"
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: assistant.delta" in streamed.text
    assert "event: done" in streamed.text
    assert interrupted.json() == {"interrupted": True}
    assert hermes.interruptions == ["session-1"]
    assert hermes.stream_messages == [("session-1", "stream me")]
    assert hermes.chat_inherit_flags == [True]
    assert hermes.stream_inherit_flags == [True]
    assert deleted.json() == {"id": "session-1", "deleted": True}


def test_agent_model_catalog_is_safe_and_switches_only_whitelisted_models(
    tmp_path: Path,
) -> None:
    hermes = FakeHermes()
    client = make_client(tmp_path, hermes, deepseek_enabled=True)

    catalog = client.get("/v1/elfred/agent/models")
    assert catalog.status_code == 200
    assert catalog.json() == {
        "default_model_id": "gpt",
        "models": [
            {
                "id": "gpt",
                "label": "configured-model",
                "description": "当前默认模型",
                "is_default": True,
            },
            {
                "id": "deepseek-v4-flash",
                "label": "DeepSeek V4 Flash",
                "description": "DeepSeek 官方 API",
                "is_default": False,
            },
        ],
    }
    assert "custom-provider" not in catalog.text
    assert "api.deepseek.com" not in catalog.text
    assert "API key" not in catalog.text

    created = client.post(
        "/v1/elfred/agent/sessions", json={"model_id": "deepseek-v4-flash"}
    )
    assert created.status_code == 201
    assert created.json()["session"]["model_id"] == "deepseek-v4-flash"
    assert hermes.created_runtimes[-1] == CodexRuntime(
        model="deepseek-v4-flash", provider="deepseek"
    )

    switched = client.post(
        "/v1/elfred/agent/sessions/session-1/model",
        json={"model_id": "deepseek-v4-flash"},
    )
    assert switched.status_code == 200
    assert switched.json()["model"]["id"] == "deepseek-v4-flash"
    assert hermes.selected_runtimes[-1] == (
        "session-1",
        CodexRuntime(model="deepseek-v4-flash", provider="deepseek"),
    )

    rejected = client.post(
        "/v1/elfred/agent/sessions/session-1/model",
        json={"model_id": "https://attacker.invalid/model"},
    )
    assert rejected.status_code == 422
    assert len(hermes.selected_runtimes) == 1


def test_deepseek_model_is_absent_when_not_explicitly_enabled(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path, FakeHermes())

    catalog = client.get("/v1/elfred/agent/models")
    assert catalog.status_code == 200
    assert [model["id"] for model in catalog.json()["models"]] == ["gpt"]
    rejected = client.post(
        "/v1/elfred/agent/sessions", json={"model_id": "deepseek-v4-flash"}
    )
    assert rejected.status_code == 422


def test_agent_bff_maps_upstream_errors_without_secret_data(tmp_path: Path) -> None:
    class FailedHermes(FakeHermes):
        def health(self, *, detailed: bool = False) -> dict[str, Any]:
            raise HermesError("Hermes request failed with HTTP 401")

    client = make_client(tmp_path, FailedHermes())

    response = client.get("/v1/elfred/agent/health")
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Hermes request failed with HTTP 401"
    }


def test_agent_auto_titles_blank_session_from_first_exchange(tmp_path: Path) -> None:
    class BlankHermes(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.titles["session-1"] = ""

    hermes = BlankHermes()
    client = make_client(tmp_path, hermes)

    response = client.post("/v1/elfred/agent/sessions/session-1/title/auto")

    assert response.status_code == 200
    assert response.json()["title"] == "修复任务看板状态"
    assert hermes.titles["session-1"] == "修复任务看板状态"
    assert "hello" in hermes.completed_prompts[0]
    assert "done" in hermes.completed_prompts[0]


def test_agent_auto_title_never_overwrites_manual_title_race(tmp_path: Path) -> None:
    class RenamedDuringGeneration(FakeHermes):
        def __init__(self) -> None:
            super().__init__()
            self.titles["session-1"] = ""

        def complete(self, message: str, *, instructions: str | None = None) -> str:
            self.titles["session-1"] = "用户手动标题"
            return super().complete(message, instructions=instructions)

    hermes = RenamedDuringGeneration()
    client = make_client(tmp_path, hermes)

    response = client.post("/v1/elfred/agent/sessions/session-1/title/auto")

    assert response.status_code == 200
    assert response.json()["title"] == "用户手动标题"
    assert hermes.titles["session-1"] == "用户手动标题"
