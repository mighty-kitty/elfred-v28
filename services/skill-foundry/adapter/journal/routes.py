"""日报 API 路由 — 注册到 adapter 的 FastAPI app"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from adapter.journal.models import GenerateRequest, GenerateResponse


class JournalGenerateBody(BaseModel):
    date: date
    dry_run: bool = False
    max_events: int = Field(default=30, ge=1, le=500)
    todo_ids: list[int] = Field(default_factory=list, max_length=1000)
    topic_names: list[str] = Field(default_factory=list, max_length=200)


def register_journal_routes(app: Any, coordinator: Any, prefix: str = "/v1/elfred") -> None:
    """在 FastAPI app 上注册日报相关端点"""

    @app.post(f"{prefix}/journal/generate")
    def generate_journal(body: JournalGenerateBody) -> dict[str, Any]:
        """Generate or enqueue one date through the durable coordinator."""
        req = GenerateRequest(
            date=body.date.isoformat(),
            dry_run=body.dry_run,
            max_events=body.max_events,
        )
        result = coordinator.sync(req, trigger="manual")
        return _response_to_dict(result)

    @app.get(f"{prefix}/journal/status")
    async def journal_status() -> dict[str, Any]:
        """日报服务状态"""
        return coordinator.status()


def _response_to_dict(resp: GenerateResponse) -> dict[str, Any]:
    return {
        "status": resp.status,
        "journal_id": resp.journal_id,
        "payload": resp.payload,
        "warnings": resp.warnings,
        "used_fallback": resp.used_fallback,
    }
