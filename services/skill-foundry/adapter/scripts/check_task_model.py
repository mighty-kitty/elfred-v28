from __future__ import annotations

import argparse
from dataclasses import replace
import json
from datetime import datetime, timezone

from adapter.config import Settings
from adapter.codex_client import CodexError
from adapter.harness import build_codex_client
from adapter.task_analyzer import CodexTaskAnalyzer, TaskAnalysisError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify one real Elfred task-model inference without user data."
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--reasoning-effort", default="")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    provider = args.provider or settings.llm_provider_id
    model = args.model or settings.llm_model_id
    if not provider or not model:
        print(json.dumps({"status": "failed", "error": "Codex provider and model are required"}))
        return 1
    settings = replace(
        settings,
        llm_provider="codex",
        llm_provider_id=provider,
        llm_model_id=model,
        llm_reasoning_effort=args.reasoning_effort or settings.llm_reasoning_effort,
        llm_timeout_seconds=args.timeout,
    )
    client = build_codex_client(settings)
    analyzer = CodexTaskAnalyzer(
        base_url="",
        api_key="",
        provider_id=provider,
        model_id=model,
        reasoning_effort=args.reasoning_effort,
        timeout_seconds=args.timeout,
        client=client,
    )
    safe_probe = {
        "event_id": "elfred-model-connectivity-probe",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "startup_preflight",
        "app": {
            "name": "Elfred",
            "category": "system",
            "window_title": "Safe model connectivity probe",
        },
        "content": {
            "content_type": "reference",
            "summary": "Safe connectivity probe",
            "clean_text": (
                "This is a synthetic Elfred connectivity probe containing no user data. "
                "It is reference text and does not request a user task."
            ),
            "tasks": [],
        },
        "privacy": {
            "requires_user_confirmation": False,
            "allowed_to_write_long_term_memory": False,
        },
    }
    try:
        client.start()
        analysis = analyzer.analyze(safe_probe, existing_tasks=[])
    except (CodexError, TaskAnalysisError) as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "provider": provider,
                    "model": model,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    finally:
        client.close()
    print(
        json.dumps(
            {
                "status": "ok",
                "provider": analysis.provider,
                "model": analysis.model,
                "context_kind": analysis.context_kind,
                "task_count": len(analysis.tasks),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
