"""Compatibility wrapper for the canonical emotion module."""

from .emotion_engine import CALM_EMOTION, EMOTION_RULES, detect_emotion

__all__ = ["CALM_EMOTION", "EMOTION_RULES", "detect_emotion"]
