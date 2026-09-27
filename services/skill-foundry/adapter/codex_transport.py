from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodexTransportError(RuntimeError):
    """A safe error raised when the local Codex app-server is unavailable."""


@dataclass(frozen=True)
class CodexProcessStatus:
    ready: bool
    pid: int | None
    version: str
    detail: str = ""


class CodexAppServerTransport:
    """Thread-safe JSON-RPC bridge to one local ``codex app-server --stdio`` process."""

    def __init__(
        self,
        executable: str,
        codex_home: Path,
        working_directory: Path,
        environment: dict[str, str],
        *,
        timeout_seconds: float = 120.0,
        stderr_path: Path | None = None,
    ) -> None:
        self.executable = str(executable)
        self.codex_home = Path(codex_home)
        self.working_directory = Path(working_directory)
        self.environment = {key: value for key, value in environment.items() if value}
        self.timeout_seconds = timeout_seconds
        self.stderr_path = stderr_path
        self._process: subprocess.Popen[str] | None = None
        self._stderr_file: Any | None = None
        self._reader: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._subscribers: dict[str, set[queue.Queue[dict[str, Any]]]] = {}
        self._closed = threading.Event()
        self._ready = False
        self._version = ""
        self._last_error = ""

    def start(self) -> None:
        with self._state_lock:
            if self._ready and self._process and self._process.poll() is None:
                return
            self.close()
            self.codex_home.mkdir(parents=True, exist_ok=True)
            if self.stderr_path:
                self.stderr_path.parent.mkdir(parents=True, exist_ok=True)
                self._stderr_file = self.stderr_path.open("a", encoding="utf-8")
            child_env = os.environ.copy()
            child_env.update(self.environment)
            child_env["CODEX_HOME"] = str(self.codex_home)
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._closed.clear()
            self._last_error = ""
            command = self._app_server_command(self.executable)
            self._process = subprocess.Popen(
                command,
                cwd=self.working_directory,
                env=child_env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr_file or subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            self._reader = threading.Thread(
                target=self._read_loop,
                name="elfred-codex-app-server-reader",
                daemon=True,
            )
            self._reader.start()

        try:
            response = self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "elfred-adapter",
                        "title": "Elfred Adapter",
                        "version": "1",
                    },
                    "capabilities": {},
                },
            )
            result = response.get("result")
            if not isinstance(result, dict):
                raise CodexTransportError("Codex returned an invalid initialize response")
            self._version = str(result.get("userAgent") or "")
            self.notify("initialized", {})
            self._ready = True
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        with self._state_lock:
            self._ready = False
            self._closed.set()
            process = self._process
            self._process = None
            if process:
                try:
                    if process.stdin:
                        process.stdin.close()
                except OSError:
                    pass
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            if self._reader and self._reader is not threading.current_thread():
                self._reader.join(timeout=2)
            self._reader = None
            if self._stderr_file:
                self._stderr_file.close()
                self._stderr_file = None
            self._fail_pending("Codex app-server stopped")
            self._subscribers.clear()

    def status(self) -> CodexProcessStatus:
        process = self._process
        alive = process is not None and process.poll() is None
        return CodexProcessStatus(
            ready=self._ready and alive,
            pid=process.pid if alive else None,
            version=self._version,
            detail=self._last_error,
        )

    def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self._ensure_running()
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._state_lock:
            request_id = self._next_id
            self._next_id += 1
            self._pending[request_id] = response_queue
        try:
            self._write({"id": request_id, "method": method, "params": params})
            try:
                response = response_queue.get(timeout=timeout_seconds or self.timeout_seconds)
            except queue.Empty as error:
                raise CodexTransportError(f"Codex request timed out: {method}") from error
            if "_transport_error" in response:
                raise CodexTransportError(str(response["_transport_error"]))
            if "error" in response:
                raise CodexTransportError(self._safe_error(response.get("error")))
            return response
        finally:
            with self._state_lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._ensure_running()
        self._write({"method": method, "params": params})

    def subscribe(self, thread_id: str) -> tuple[queue.Queue[dict[str, Any]], Callable[[], None]]:
        channel: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._state_lock:
            self._subscribers.setdefault(thread_id, set()).add(channel)

        def unsubscribe() -> None:
            with self._state_lock:
                channels = self._subscribers.get(thread_id)
                if not channels:
                    return
                channels.discard(channel)
                if not channels:
                    self._subscribers.pop(thread_id, None)

        return channel, unsubscribe

    def _ensure_running(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            detail = self._last_error or "Codex app-server is not running"
            raise CodexTransportError(detail)

    def _write(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise CodexTransportError("Codex app-server is not running")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._write_lock:
                process.stdin.write(encoded + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            self._last_error = "Codex app-server connection closed"
            self._fail_pending(self._last_error)
            raise CodexTransportError(self._last_error) from error

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for raw in process.stdout:
                if self._closed.is_set():
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    self._last_error = "Codex app-server emitted invalid JSON"
                    continue
                if not isinstance(message, dict):
                    continue
                if "id" in message and "method" not in message:
                    self._deliver_response(message)
                elif "id" in message and "method" in message:
                    self._reject_server_request(message)
                elif isinstance(message.get("method"), str):
                    self._deliver_notification(message)
        finally:
            if not self._closed.is_set():
                self._last_error = "Codex app-server exited unexpectedly"
            self._fail_pending(self._last_error or "Codex app-server stopped")

    def _deliver_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        with self._state_lock:
            channel = self._pending.get(request_id)
        if channel:
            channel.put(message)

    def _deliver_notification(self, message: dict[str, Any]) -> None:
        params = message.get("params")
        thread_id = params.get("threadId") if isinstance(params, dict) else None
        if not isinstance(thread_id, str):
            return
        with self._state_lock:
            targets = tuple(self._subscribers.get(thread_id, ()))
        for target in targets:
            target.put(message)

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        try:
            self._write(
                {
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": "Elfred does not permit interactive Codex approvals",
                    },
                }
            )
        except CodexTransportError:
            pass

    def _fail_pending(self, detail: str) -> None:
        with self._state_lock:
            pending = tuple(self._pending.values())
        for channel in pending:
            try:
                channel.put_nowait({"_transport_error": detail})
            except queue.Full:
                pass

    @staticmethod
    def _safe_error(value: Any) -> str:
        if isinstance(value, dict):
            code = value.get("code")
            message = str(value.get("message") or "Codex request failed")
            return f"Codex request failed{f' ({code})' if code is not None else ''}: {message[:300]}"
        return "Codex request failed"

    @staticmethod
    def _app_server_command(executable: str) -> list[str]:
        command = [executable, "app-server", "--stdio", "--strict-config"]
        if Path(executable).suffix.casefold() != ".cmd":
            return command
        return [
            os.environ.get("ComSpec", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            "call " + subprocess.list2cmdline(command),
        ]
