from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from adapter.agent_models import AgentModelCatalog
from adapter.config import Settings
from adapter.codex_client import CodexClient, CodexError
from adapter.harness import build_codex_client
from adapter.session_title import generate_session_title


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=200_000)


class AgentSessionCreate(BaseModel):
    model_id: str | None = Field(default=None, min_length=1, max_length=80)


class AgentSessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AgentModelSelection(BaseModel):
    model_id: str = Field(min_length=1, max_length=80)


def _iso_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value)


def _session(
    item: dict[str, Any], models: AgentModelCatalog, model_id: str | None = None
) -> dict[str, Any]:
    selected_model_id = (
        models.resolve(model_id).id
        if model_id is not None
        else models.identify_session(item).id
    )
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "created_at": _iso_timestamp(item.get("started_at")),
        "updated_at": _iso_timestamp(
            item.get("last_active") or item.get("started_at")
        ),
        "model_id": selected_model_id,
    }


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    return "".join(
        str(part.get("text") or "")
        for part in value
        if isinstance(part, dict) and part.get("type") in {"text", "input_text"}
    )


def _message(item: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": str(item.get("id") or ""),
        "role": str(item.get("role") or ""),
        "content": _message_content(item.get("content")),
    }
    reasoning = item.get("reasoning") or item.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        result["reasoning"] = reasoning
    return result


def _has_meaningful_title(item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "").strip()
    return bool(title) and re.fullmatch(
        r"New session(?:\s*-.*)?", title, re.IGNORECASE
    ) is None


def _client(settings: Settings) -> CodexClient:
    return build_codex_client(settings)


def _upstream_error(error: CodexError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(error))


def _stream_events(events: Iterator[tuple[str, dict[str, Any]]]) -> Iterator[bytes]:
    try:
        for event_name, payload in events:
            safe_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event_name}\ndata: {safe_data}\n\n".encode("utf-8")
    except (CodexError, RuntimeError) as error:
        payload = json.dumps({"message": str(error)}, ensure_ascii=False)
        yield f"event: error\ndata: {payload}\n\n".encode("utf-8")


def register_agent_routes(
    app: FastAPI,
    settings: Settings,
    prefix: str,
    *,
    client: CodexClient | None = None,
) -> None:
    codex = client or _client(settings)
    models = AgentModelCatalog(settings)
    route = f"{prefix}/agent"

    @app.get(f"{route}/models")
    def list_models() -> dict[str, Any]:
        return models.public_payload()

    @app.get(f"{route}/health")
    def agent_health() -> dict[str, Any]:
        try:
            detail = codex.health(detailed=True)
        except (CodexError, RuntimeError) as error:
            raise _upstream_error(error) from error
        return {
            "status": "ok",
            "harness": "codex",
            "model": settings.llm_model_id,
            "detail": detail,
        }

    @app.get(f"{route}/sessions")
    def list_sessions() -> dict[str, Any]:
        sessions: list[dict[str, Any]] = []
        offset = 0
        try:
            while offset < 10_000:
                payload = codex.list_sessions(
                    source="elfred_browser", limit=200, offset=offset
                )
                page = payload.get("data")
                if not isinstance(page, list):
                    raise CodexError("Codex returned an invalid session list")
                sessions.extend(
                    _session(item, models) for item in page if isinstance(item, dict)
                )
                if not payload.get("has_more") or not page:
                    break
                offset += len(page)
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"sessions": sessions, "total": len(sessions)}

    @app.post(f"{route}/sessions", status_code=201)
    def create_session(
        request: AgentSessionCreate | None = None,
    ) -> dict[str, Any]:
        try:
            model = models.resolve(request.model_id if request else None)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            session = codex.create_session(
                source="elfred_browser", runtime=model.runtime
            )
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"session": _session(session, models, model.id)}

    @app.get(f"{route}/sessions/{{session_id}}/messages")
    def get_messages(session_id: str) -> dict[str, Any]:
        try:
            messages = codex.get_messages(session_id)
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"messages": [_message(item) for item in messages]}

    @app.patch(f"{route}/sessions/{{session_id}}")
    def update_session(
        session_id: str,
        request: AgentSessionUpdate,
    ) -> dict[str, Any]:
        try:
            return _session(
                codex.update_session(session_id, title=request.title.strip()),
                models,
            )
        except CodexError as error:
            raise _upstream_error(error) from error

    @app.post(f"{route}/sessions/{{session_id}}/model")
    def select_session_model(
        session_id: str,
        request: AgentModelSelection,
    ) -> dict[str, Any]:
        try:
            model = models.resolve(request.model_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            codex.set_session_model(session_id, model.runtime)
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"model": model.public_dict()}

    @app.delete(f"{route}/sessions/{{session_id}}")
    def delete_session(session_id: str) -> dict[str, Any]:
        try:
            deleted = codex.delete_session(session_id)
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"id": session_id, "deleted": deleted}

    @app.post(f"{route}/sessions/{{session_id}}/chat")
    def chat(session_id: str, request: AgentChatRequest) -> dict[str, Any]:
        try:
            payload = codex.chat(
                session_id, request.message, inherit_session_runtime=True
            )
        except CodexError as error:
            raise _upstream_error(error) from error
        item = payload.get("message")
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=502,
                detail="Codex returned an invalid chat response",
            )
        return _message(item)

    @app.post(f"{route}/sessions/{{session_id}}/chat/stream")
    def stream_chat(
        session_id: str,
        request: AgentChatRequest,
    ) -> StreamingResponse:
        if hasattr(codex, "iter_chat_events"):
            events = codex.iter_chat_events(session_id, request.message)
        else:
            stream = codex.stream_chat(
                session_id, request.message, inherit_session_runtime=True
            )
            events = (
                (event_name, json.loads(data))
                for event_name, data in codex.iter_sse(stream)
            )
        return StreamingResponse(
            _stream_events(events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post(f"{route}/sessions/{{session_id}}/chat/interrupt")
    def interrupt_chat(session_id: str) -> dict[str, bool]:
        try:
            interrupted = codex.interrupt_chat(session_id)
        except CodexError as error:
            raise _upstream_error(error) from error
        return {"interrupted": bool(interrupted)}

    @app.post(f"{route}/sessions/{{session_id}}/title/auto")
    def auto_title_session(session_id: str) -> dict[str, Any]:
        try:
            session = codex.get_session(session_id)
            if _has_meaningful_title(session):
                return _session(session, models)
            messages = codex.get_messages(session_id)
            user_message = next(
                (
                    _message_content(item.get("content"))
                    for item in messages
                    if isinstance(item, dict) and item.get("role") == "user"
                ),
                "",
            )
            assistant_message = next(
                (
                    _message_content(item.get("content"))
                    for item in messages
                    if isinstance(item, dict) and item.get("role") == "assistant"
                ),
                "",
            )
            if not user_message:
                return _session(session, models)
            title = generate_session_title(codex, user_message, assistant_message)
            current = codex.get_session(session_id)
            if _has_meaningful_title(current):
                return _session(current, models)
            return _session(
                codex.update_session(session_id, title=title),
                models,
            )
        except CodexError as error:
            raise _upstream_error(error) from error
