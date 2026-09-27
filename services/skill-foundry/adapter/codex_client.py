from __future__ import annotations

import queue
import time
from dataclasses import dataclass
from typing import Any, Iterator

from adapter.codex_transport import CodexAppServerTransport, CodexTransportError


class CodexError(RuntimeError):
    """A domain error that is safe to return from the Adapter boundary."""


@dataclass(frozen=True)
class CodexRuntime:
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
        if bool(self.model) != bool(self.provider):
            raise ValueError("A Codex runtime requires both model and provider")


class CodexClient:
    """Harness-neutral Adapter facade over Codex app-server threads and turns.

    The public methods deliberately match the former session client closely so
    task analysis, journals, Skill Foundry and the browser keep their behavior.
    Codex itself is always invoked in a non-interactive read-only sandbox.
    """

    def __init__(
        self,
        transport: CodexAppServerTransport,
        *,
        runtime: CodexRuntime,
        working_directory: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.transport = transport
        self.runtime = runtime
        self.working_directory = working_directory
        self.timeout_seconds = timeout_seconds
        self._runtimes: dict[str, CodexRuntime] = {}
        self._active_turns: dict[str, str] = {}

    def start(self) -> None:
        try:
            self.transport.start()
        except CodexTransportError as error:
            raise CodexError(str(error)) from error

    def close(self) -> None:
        self.transport.close()

    def health(self, *, detailed: bool = False) -> dict[str, Any]:
        self.start()
        status = self.transport.status()
        result: dict[str, Any] = {
            "ready": status.ready,
            "pid": status.pid,
            "version": status.version,
        }
        if detailed and status.detail:
            result["detail"] = status.detail
        return result

    def list_sessions(
        self,
        *,
        source: str = "elfred_browser",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        del source
        cursor: str | None = None
        skipped = 0
        sessions: list[dict[str, Any]] = []
        has_more = False
        try:
            while len(sessions) < limit:
                result = self._request(
                    "thread/list", {"cursor": cursor, "limit": min(100, limit)}
                ).get("result", {})
                page = result.get("data") if isinstance(result, dict) else None
                if not isinstance(page, list):
                    raise CodexError("Codex returned an invalid thread list")
                for thread in page:
                    if not isinstance(thread, dict):
                        continue
                    if skipped < offset:
                        skipped += 1
                        continue
                    sessions.append(self._session(thread))
                    if len(sessions) >= limit:
                        break
                cursor = result.get("nextCursor") if isinstance(result, dict) else None
                if not cursor or len(sessions) >= limit:
                    has_more = bool(cursor)
                    break
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        return {"data": sessions, "has_more": has_more}

    def create_session(
        self,
        *,
        source: str,
        title: str | None = None,
        system_prompt: str | None = None,
        runtime: CodexRuntime | None = None,
    ) -> dict[str, Any]:
        del source
        selected = runtime or self.runtime
        params = self._thread_params(selected)
        if system_prompt:
            params["developerInstructions"] = system_prompt
        try:
            result = self._request("thread/start", params).get("result", {})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise CodexError("Codex did not return a thread")
        thread_id = str(thread["id"])
        self._runtimes[thread_id] = selected
        if title and title.strip():
            thread = self.update_session(thread_id, title=title.strip())
        return self._session(thread, selected)

    def get_session(self, session_id: str) -> dict[str, Any]:
        try:
            result = self._request(
                "thread/read", {"threadId": session_id, "includeTurns": False}
            ).get("result", {})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict):
            raise CodexError("Codex returned an invalid thread")
        return self._session(thread)

    def update_session(self, session_id: str, *, title: str) -> dict[str, Any]:
        try:
            result = self._request(
                "thread/name/set", {"threadId": session_id, "name": title}
            ).get("result", {})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict):
            return self.get_session(session_id)
        return self._session(thread)

    def delete_session(self, session_id: str) -> bool:
        try:
            self._request("thread/delete", {"threadId": session_id})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        self._runtimes.pop(session_id, None)
        self._active_turns.pop(session_id, None)
        return True

    def set_session_model(
        self, session_id: str, runtime: CodexRuntime
    ) -> dict[str, Any]:
        try:
            result = self._request(
                "thread/resume", {"threadId": session_id, **self._thread_params(runtime)}
            ).get("result", {})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict):
            raise CodexError("Codex returned an invalid resumed thread")
        self._runtimes[session_id] = runtime
        return self._session(thread, runtime)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        try:
            result = self._request(
                "thread/read", {"threadId": session_id, "includeTurns": True}
            ).get("result", {})
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        thread = result.get("thread") if isinstance(result, dict) else None
        if not isinstance(thread, dict):
            raise CodexError("Codex returned an invalid thread")
        messages: list[dict[str, Any]] = []
        turns = thread.get("turns")
        for turn in turns if isinstance(turns, list) else []:
            if not isinstance(turn, dict):
                continue
            for item in turn.get("items") if isinstance(turn.get("items"), list) else []:
                message = self._message(item)
                if message is not None:
                    messages.append(message)
        return messages

    def chat(
        self,
        session_id: str,
        message: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        inherit_session_runtime: bool = False,
    ) -> dict[str, Any]:
        del instructions, inherit_session_runtime
        assistant = "".join(
            data.get("delta", "")
            for event, data in self.iter_chat_events(session_id, message)
            if event == "assistant.delta"
        )
        if not assistant.strip():
            raise CodexError("Codex returned no assistant text")
        return {"message": {"id": "", "role": "assistant", "content": assistant}}

    def iter_chat_events(
        self, session_id: str, message: str | list[dict[str, Any]]
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        channel, unsubscribe = self.transport.subscribe(session_id)
        turn_id = ""
        try:
            runtime = self._runtimes.get(session_id, self.runtime)
            params: dict[str, Any] = {
                "threadId": session_id,
                "input": self._input_items(message),
            }
            if runtime.model:
                params["model"] = runtime.model
            if runtime.reasoning_effort:
                params["effort"] = runtime.reasoning_effort
            result = self._request("turn/start", params).get("result", {})
            turn = result.get("turn") if isinstance(result, dict) else None
            if not isinstance(turn, dict):
                raise CodexError("Codex did not return a turn")
            turn_id = str(turn.get("id") or turn.get("turnId") or "")
            if not turn_id:
                raise CodexError("Codex did not return a turn id")
            self._active_turns[session_id] = turn_id
            yield "message.started", {"session_id": session_id}
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexError("Codex turn timed out")
                try:
                    notification = channel.get(timeout=remaining)
                except queue.Empty as error:
                    raise CodexError("Codex turn timed out") from error
                event = self._stream_event(notification)
                if event is None:
                    continue
                event_name, payload, terminal = event
                yield event_name, payload
                if terminal:
                    if event_name == "assistant.completed":
                        yield "done", {}
                    return
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        finally:
            if turn_id and self._active_turns.get(session_id) == turn_id:
                self._active_turns.pop(session_id, None)
            unsubscribe()

    def interrupt_chat(self, session_id: str) -> bool:
        turn_id = self._active_turns.get(session_id)
        if not turn_id:
            return False
        try:
            self._request(
                "turn/interrupt",
                {"threadId": session_id, "turnId": turn_id},
            )
        except CodexTransportError as error:
            raise CodexError(str(error)) from error
        return True

    def complete(
        self,
        message: str | list[dict[str, Any]],
        *,
        instructions: str | None = None,
        runtime: CodexRuntime | None = None,
    ) -> str:
        session = self.create_session(
            source="background", system_prompt=instructions, runtime=runtime or self.runtime
        )
        session_id = str(session["id"])
        try:
            return str(self.chat(session_id, message)["message"]["content"])
        finally:
            try:
                self.delete_session(session_id)
            except CodexError:
                pass

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.start()
        return self.transport.request(method, params, timeout_seconds=self.timeout_seconds)

    def _thread_params(self, runtime: CodexRuntime) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": self.working_directory,
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "ephemeral": False,
            "model": runtime.model,
            "modelProvider": runtime.provider,
        }
        if runtime.reasoning_effort:
            params["config"] = {"model_reasoning_effort": runtime.reasoning_effort}
        return params

    def _session(
        self, thread: dict[str, Any], runtime: CodexRuntime | None = None
    ) -> dict[str, Any]:
        selected = runtime or self._runtimes.get(str(thread.get("id")), self.runtime)
        return {
            "id": str(thread.get("id") or ""),
            "title": str(thread.get("name") or thread.get("preview") or "New session"),
            "started_at": thread.get("createdAt"),
            "last_active": thread.get("updatedAt") or thread.get("createdAt"),
            "model": selected.model,
            "provider": selected.provider,
        }

    @staticmethod
    def _input_items(value: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(value, str):
            return [{"type": "text", "text": value}]
        items: list[dict[str, Any]] = []
        for part in value:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"text", "input_text"}:
                text = str(part.get("text") or "")
                if text:
                    items.append({"type": "text", "text": text})
            elif part.get("type") == "image_url":
                image = part.get("image_url")
                url = image.get("url") if isinstance(image, dict) else None
                if isinstance(url, str) and url:
                    items.append({"type": "image", "url": url, "detail": "low"})
        if not items:
            raise CodexError("Codex requires a text prompt")
        return items

    @staticmethod
    def _message(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        item_type = item.get("type")
        if item_type == "userMessage":
            content = CodexClient._content_text(item.get("content"))
            return {"id": str(item.get("id") or ""), "role": "user", "content": content}
        if item_type == "agentMessage":
            return {
                "id": str(item.get("id") or ""),
                "role": "assistant",
                "content": str(item.get("text") or ""),
            }
        return None

    @staticmethod
    def _content_text(content: Any) -> str:
        if not isinstance(content, list):
            return ""
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )

    @staticmethod
    def _stream_event(
        notification: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bool] | None:
        method = notification.get("method")
        params = notification.get("params")
        if not isinstance(params, dict):
            return None
        if method == "item/agentMessage/delta":
            delta = str(params.get("delta") or "")
            return ("assistant.delta", {"delta": delta}, False) if delta else None
        if method == "turn/completed":
            return "assistant.completed", {}, True
        if method == "turn/failed":
            return "error", {"message": "Codex turn failed"}, True
        if method == "error":
            return "error", {"message": str(params.get("message") or "Codex error")}, True
        return None
