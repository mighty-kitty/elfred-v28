from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapter.config import Settings
from adapter.codex_client import CodexRuntime


DEFAULT_AGENT_MODEL_ID = "gpt"
DEEPSEEK_AGENT_MODEL_ID = "deepseek-v4-flash"


@dataclass(frozen=True)
class AgentModel:
    id: str
    label: str
    description: str
    provider: str
    model: str
    reasoning_effort: str = ""
    is_default: bool = False

    @property
    def runtime(self) -> CodexRuntime:
        return CodexRuntime(
            model=self.model,
            provider=self.provider,
            reasoning_effort=self.reasoning_effort,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "is_default": self.is_default,
        }


class AgentModelCatalog:
    def __init__(self, settings: Settings) -> None:
        deepseek_primary = (
            str(settings.llm_provider_id).casefold().strip() == "deepseek"
            and str(settings.llm_model_id).casefold().strip() == "deepseek-v4-flash"
        )
        if deepseek_primary:
            default = AgentModel(
                id=DEEPSEEK_AGENT_MODEL_ID,
                label="DeepSeek V4 Flash",
                description="当前默认模型",
                provider="deepseek",
                model="deepseek-v4-flash",
                is_default=True,
            )
            models = [default]
        else:
            default = AgentModel(
                id=DEFAULT_AGENT_MODEL_ID,
                label=_default_model_label(settings.llm_model_id),
                description="当前默认模型",
                provider=settings.llm_provider_id,
                model=settings.llm_model_id,
                reasoning_effort=settings.llm_reasoning_effort,
                is_default=True,
            )
            models = [default]
            if settings.agent_deepseek_enabled:
                models.append(
                    AgentModel(
                        id=DEEPSEEK_AGENT_MODEL_ID,
                        label="DeepSeek V4 Flash",
                        description="DeepSeek 官方 API",
                        provider="deepseek",
                        model="deepseek-v4-flash",
                    )
                )
        self._models = tuple(models)
        self._by_id = {model.id: model for model in models}
        self.default = default

    def public_payload(self) -> dict[str, Any]:
        return {
            "models": [model.public_dict() for model in self._models],
            "default_model_id": self.default.id,
        }

    def resolve(self, model_id: str | None) -> AgentModel:
        if model_id is None or not model_id.strip():
            return self.default
        try:
            return self._by_id[model_id.strip()]
        except KeyError as error:
            raise ValueError("Unsupported agent model") from error

    def identify_session(self, session: dict[str, Any]) -> AgentModel:
        upstream_model = str(session.get("model") or "").strip()
        if upstream_model:
            for model in self._models:
                if model.model == upstream_model:
                    return model
        return self.default


def _default_model_label(model_id: str) -> str:
    normalized = str(model_id or "").strip()
    if normalized.casefold() == "gpt-5.6-luna":
        return "GPT-5.6 Luna"
    return normalized or "默认模型"
