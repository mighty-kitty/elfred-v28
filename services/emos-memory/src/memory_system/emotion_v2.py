from __future__ import annotations

from .models import EmotionSignal


CALM_EMOTION = "平静"

EMOTION_RULES: dict[str, tuple[str, ...]] = {
    "开心": ("开心", "高兴", "期待", "喜欢", "激动", "快乐", "兴奋"),
    "难过": ("难过", "失眠", "低落", "孤独", "想哭", "难受", "委屈"),
    "愤怒": ("生气", "火大", "崩溃", "受不了", "烦死了"),
    "焦虑": ("压力", "焦虑", "担心", "考试", "加班", "睡不好", "睡不着"),
    "感激": ("谢谢", "陪我", "安慰", "理解", "支持"),
}


def detect_emotion(text: str) -> EmotionSignal:
    lowered = text.strip().lower()
    best_label = CALM_EMOTION
    best_hits: list[str] = []

    for label, keywords in EMOTION_RULES.items():
        hits = [word for word in keywords if word.lower() in lowered]
        if len(hits) > len(best_hits):
            best_label = label
            best_hits = hits

    if best_hits:
        score = min(0.35 + 0.15 * len(best_hits), 0.95)
    else:
        score = 0.2 if len(text) > 20 else 0.1

    return EmotionSignal(label=best_label, score=score, triggers=best_hits)
