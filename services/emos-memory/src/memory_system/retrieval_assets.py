from __future__ import annotations

import os
from pathlib import Path

from .utils.io import read_json


DEFAULT_SEMANTIC_ALIASES: dict[str, list[str]] = {
    "考试": ["考试", "考砸", "没考好", "复习", "挂科"],
    "五月天": ["五月天", "乐队", "阿信", "演唱会", "听歌"],
    "加班": ["加班", "工作", "熬夜", "凌晨", "忙到很晚"],
    "活动": ["活动", "项目", "发布会", "现场", "那件没做好的事"],
    "失眠": ["失眠", "睡不好", "睡不着", "熬夜", "夜里醒来"],
    "压力": ["压力", "焦虑", "担心", "紧张", "发愁"],
}

DEFAULT_STOP_TOKENS: list[str] = [
    "我们",
    "你们",
    "他们",
    "今天",
    "最近",
    "之前",
    "现在",
    "时候",
    "那个",
    "那次",
    "这次",
    "事情",
    "有点",
    "一直",
    "一下",
    "已经",
    "还是",
]

DEFAULT_RETRIEVAL_SETTINGS: dict[str, object] = {
    "version": 2,
    "backend": "embedding_rerank",
    "weights": {
        "lexical": 1.0,
        "fuzzy": 0.35,
        "semantic": 0.45,
        "concept": 0.30,
        "tag": 0.12,
        "phrase": 0.22,
        "question": 0.18,
        "emotion": 0.15,
        "recency": 0.08,
        "profile": 0.10,
        "abstraction": 0.20,
        "embedding": 0.60,
    },
    "embedding": {"dimensions": 96, "candidate_pool": 16},
    "prefilter": {
        "enabled": False,
        "min_records": 512,
        "candidate_pool": 128,
        "recency_pool": 16,
    },
    "history": [],
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_semantic_aliases() -> dict[str, tuple[str, ...]]:
    path = Path(
        os.environ.get(
            "MEMORY_SYSTEM_SEMANTIC_ALIASES_FILE",
            str(_project_root() / "configs" / "semantic_aliases.json"),
        )
    )
    payload = read_json(path, default=DEFAULT_SEMANTIC_ALIASES)
    return {canonical: tuple(dict.fromkeys(values)) for canonical, values in payload.items()}


def load_stop_tokens() -> set[str]:
    path = Path(
        os.environ.get(
            "MEMORY_SYSTEM_STOP_TOKENS_FILE",
            str(_project_root() / "configs" / "stop_tokens.json"),
        )
    )
    payload = read_json(path, default=DEFAULT_STOP_TOKENS)
    return set(payload)


def load_retrieval_settings() -> dict[str, object]:
    path = Path(
        os.environ.get(
            "MEMORY_SYSTEM_RETRIEVAL_SETTINGS_FILE",
            str(_project_root() / "configs" / "retrieval_settings.json"),
        )
    )
    payload = read_json(path, default=DEFAULT_RETRIEVAL_SETTINGS)
    return normalize_retrieval_settings(payload)


def normalize_retrieval_settings(payload: dict[str, object] | object) -> dict[str, object]:
    if not isinstance(payload, dict):
        payload = {}

    normalized = dict(DEFAULT_RETRIEVAL_SETTINGS)
    normalized["version"] = 2
    normalized["backend"] = str(payload.get("backend", DEFAULT_RETRIEVAL_SETTINGS["backend"]))

    default_weights = dict(DEFAULT_RETRIEVAL_SETTINGS["weights"])
    weight_values = payload.get("weights", {})
    if isinstance(weight_values, dict):
        for key, value in weight_values.items():
            if key in default_weights:
                default_weights[key] = float(value)
    normalized["weights"] = default_weights

    default_embedding = dict(DEFAULT_RETRIEVAL_SETTINGS["embedding"])
    embedding_values = payload.get("embedding", {})
    if isinstance(embedding_values, dict):
        if "dimensions" in embedding_values:
            default_embedding["dimensions"] = int(embedding_values["dimensions"])
        if "candidate_pool" in embedding_values:
            default_embedding["candidate_pool"] = int(embedding_values["candidate_pool"])
    normalized["embedding"] = default_embedding

    default_prefilter = dict(DEFAULT_RETRIEVAL_SETTINGS["prefilter"])
    prefilter_values = payload.get("prefilter", {})
    if isinstance(prefilter_values, dict):
        if "enabled" in prefilter_values:
            default_prefilter["enabled"] = bool(prefilter_values["enabled"])
        if "min_records" in prefilter_values:
            default_prefilter["min_records"] = max(1, int(prefilter_values["min_records"]))
        if "candidate_pool" in prefilter_values:
            default_prefilter["candidate_pool"] = max(1, int(prefilter_values["candidate_pool"]))
        if "recency_pool" in prefilter_values:
            default_prefilter["recency_pool"] = max(0, int(prefilter_values["recency_pool"]))
    normalized["prefilter"] = default_prefilter

    history = payload.get("history", [])
    normalized["history"] = [item for item in history if isinstance(item, dict)]
    return normalized
