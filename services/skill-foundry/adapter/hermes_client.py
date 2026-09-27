from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterator


class HermesError(RuntimeError):
    pass


@dataclass(frozen=True)
class HermesRuntime:
    model: str = ""
    provider: str = ""
    reasoning_effort: str = ""

    def __post_init__(self) -> None:
        allowed = {"", "none", "minimal", "low", "medium", "high", "xhigh"}
        if self.reasoning_effort not in allowed:
            raise ValueError(
                "ELFRED_LLM_REASONING_EFFORT must be one of "
                "none, minimal, low, medium, high, xhigh"
            )

    def request_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.model:
            fields["model"] = self.model
        if self.provider:
            fields["provider"] = self.provider
        if self.model and self.provider:
            fields["require_model_lock"] = True
        if self.reasoning_effort:
            fields["model_options"] = {
                "reasoning_effort": self.reasoning_effort
            }
        return fields


class HermesClient:
    """Small authenticated client for Hermes' stable Session API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        runtime: HermesRuntime | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.runtime = runtime or HermesRuntime()
        self.timeout_seconds = timeout_seconds

    def health(self, *, detailed: bool = False) -> dict[str, Any]:
        path = "/health/detailed" if detailed else "/health"
        return self.request_json("GET", path, authenticated=detailed)

    def list_sessions(
        self,
        *,
        source: str = "hermes_browser",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(
            {"source": source, "limit": limit, "offset": offset}
        )
        return self.request_json("GET", f"/api/sessions?{query}")

    def create_session(
        self,
        *,
        source: str,
        title: str | None = None,
        system_prompt: str | None = None,
        runtime: HermesRuntime | None = None,
    ) -> dict[str, Any]:
        selected_runtime = runtime or self.runtime
        body: dict[str, Any] = {"source": source, **selected_runtime.request_fields()}
        if title is not None:
            body["title"] = title
        if system_prompt is not None:
            body["system_prompt"] = system_prompt
        payload = self.request_json("POST", "/api/sessions", body)
        session = payload.get("session")
        if not isinstance(session, dict) or not session.get("id"):
            raise HermesError("Hermes did not return a session")
        return session

    def get_session(self, session_id: str) -> dict[str, Any]:
        payload = self.request_json("GET", self._session_path(session_id))
        session = payload.get("session")
        if not isinstance(session, dict):
            raise HermesError("Hermes returned an invalid session")
        return session

    def update_session(self, session_id: str, *, title: str) -> dict[str, Any]:
        payload = self.request_json(
            "PATCH", self._session_path(session_id), {"title": title}
        )
        session = payload.get("session")
        if not isinstance(session, dict):
            raise HermesError("Hermes returned an invalid session")
        return session

    def delete_session(self, session_id: str) -> bool:
        payload = self.request_json("DELETE", self._session_path(session_id))
        return bool(payload.get("deleted"))

    def set_session_model(
        self, session_id: str, runtime: HermesRuntime
    ) -> dict[str, Any]:
        fields = runtime.request_fields()
        if not fields.get("require_model_lock"):
            raise HermesError("A model and provider are required for model selection")
        return self.request_json("POST", self._session_path(session_id, "/model"), fields)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        payload = self.request_json(
            "GET", self._session_path(session_id, "/messages")
        )
        messages = payload.get("data")
        if not isinstance(messages, list):
            raise HermesError("Hermes returned an invalid message list")
        return [item for item in messages if isinstance(item, dict)]

    def chat(
        self,
        session_id: str,
        message: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        inherit_session_runtime: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"message": message}
        if not inherit_session_runtime:
            body.update(self.runtime.request_fields())
        if instructions is not None:
            body["instructions"] = instructions
        return self.request_json(
            "POST", self._session_path(session_id, "/chat"), body
        )

    def stream_chat(
        self,
        session_id: str,
        message: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        inherit_session_runtime: bool = False,
    ) -> BinaryIO:
        body: dict[str, Any] = {"message": message}
        if not inherit_session_runtime:
            body.update(self.runtime.request_fields())
        if instructions is not None:
            body["instructions"] = instructions
        return self.open_stream(
            "POST", self._session_path(session_id, "/chat/stream"), body
        )

    def complete(
        self,
        message: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
    ) -> str:
        session = self.create_session(source="api_server")
        session_id = str(session["id"])
        try:
            payload = self.chat(session_id, message, instructions=instructions)
            response = payload.get("message")
            content = response.get("content") if isinstance(response, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise HermesError("Hermes returned no assistant text")
            return content
        finally:
            try:
                self.delete_session(session_id)
            except HermesError:
                pass

    def request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        request = self._request(method, path, body, authenticated=authenticated)
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise HermesError(self._safe_error(error)) from error
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as error:
            raise HermesError("Hermes returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise HermesError("Hermes returned a non-object response")
        return payload

    def open_stream(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> BinaryIO:
        request = self._request(method, path, body)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout_seconds)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise HermesError(self._safe_error(error)) from error

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        *,
        authenticated: bool = True,
    ) -> urllib.request.Request:
        headers = {"Accept": "application/json"}
        if authenticated:
            if not self.api_key:
                raise HermesError("Hermes API key is not configured")
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

    @staticmethod
    def iter_sse(stream: BinaryIO) -> Iterator[tuple[str, str]]:
        event_name = "message"
        data_lines: list[str] = []
        for raw_line in stream:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if data_lines:
                    yield event_name, "\n".join(data_lines)
                event_name = "message"
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            yield event_name, "\n".join(data_lines)

    @staticmethod
    def _safe_error(error: BaseException) -> str:
        if isinstance(error, urllib.error.HTTPError):
            return f"Hermes request failed with HTTP {error.code}"
        if isinstance(error, urllib.error.URLError):
            return f"Hermes request failed: {error.reason}"
        return "Hermes request timed out"

    @staticmethod
    def _session_path(session_id: str, suffix: str = "") -> str:
        encoded = urllib.parse.quote(session_id, safe="")
        return f"/api/sessions/{encoded}{suffix}"
