from __future__ import annotations

import os
from pathlib import Path

from adapter.codex_client import CodexClient, CodexRuntime
from adapter.codex_transport import CodexAppServerTransport
from adapter.config import Settings


def build_codex_client(settings: Settings) -> CodexClient:
    """Create the sole local Codex process owner for an Adapter instance."""

    repo_root = Path(__file__).resolve().parents[3]
    home = settings.codex_home or repo_root / ".demo" / "codex"
    environment = {
        "ELFRED_LLM_API_KEY": os.getenv("ELFRED_LLM_API_KEY", ""),
        "ELFRED_DEEPSEEK_API_KEY": os.getenv("ELFRED_DEEPSEEK_API_KEY", ""),
    }
    transport = CodexAppServerTransport(
        settings.codex_executable,
        home,
        repo_root,
        environment,
        timeout_seconds=settings.llm_timeout_seconds,
        stderr_path=settings.codex_stderr_log,
    )
    return CodexClient(
        transport,
        runtime=CodexRuntime(
            model=settings.llm_model_id,
            provider=settings.llm_provider_id,
            reasoning_effort=settings.llm_reasoning_effort,
        ),
        working_directory=str(repo_root),
        timeout_seconds=settings.llm_timeout_seconds,
    )
