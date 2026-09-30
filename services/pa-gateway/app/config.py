# -*- coding: utf-8 -*-
"""Runtime configuration.

load_env() runs once from app/__init__.py, i.e. before any submodule reads its
environment at import time (db path, planner choice, connector URLs).
Secrets live in .env, which is gitignored (execution book WP-00).

模型配置（规划用到的那把 key）不需要单独再配一份：服务自己的 .env 优先，
没有就在仓库根目录的 .env.local / .env 里找应用已经配好的 ELFRED_MODEL_*。
"""
from __future__ import annotations
import os

_loaded = False


def load_env() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is optional
        return
    gateway_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_dir = os.path.dirname(os.path.dirname(gateway_dir))
    # 依次尝试：应用根目录的 .env.local → 根目录 .env → 本服务 .env。
    # override=False：真实进程环境永远优先，先加载的值优先（.env.local 优先于 .env）。
    for path in (
        os.path.join(repo_dir, ".env.local"),
        os.path.join(repo_dir, ".env"),
        os.path.join(gateway_dir, ".env"),
    ):
        if os.path.exists(path):
            load_dotenv(path, override=False)
