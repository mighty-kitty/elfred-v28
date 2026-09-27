# -*- coding: utf-8 -*-
"""Elfred PA Gateway - product control plane (thin BFF).
Runtime is pluggable: v0 uses a deterministic engine; Letta can replace it later.
"""
from .config import load_env

load_env()
