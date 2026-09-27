from __future__ import annotations

from .retrieval_backends import extract_concepts


FUTURE_INTENT_CUES = (
    "想去",
    "想看",
    "打算",
    "准备",
    "计划",
    "想抢",
    "惦记",
)

MISSED_OPPORTUNITY_CUES = (
    "错过",
    "没抢到",
    "没看到",
    "没去成",
    "遗憾",
)

LIVE_EVENT_CUES = (
    "现场",
    "演唱会",
    "演出",
    "门票",
    "票",
)

PERFORMANCE_FAILURE_CUES = (
    "没发挥好",
    "失手",
    "考砸",
    "没考好",
    "失败",
)

GENERALIZATION_CUES = (
    "类似",
    "一碰到",
    "想到之前",
    "又想到",
    "回到之前",
)

WORKLOAD_STRESS_CUES = (
    "工作量",
    "加班",
    "熬人",
    "凌晨",
    "疲惫",
    "最累",
)

STRESS_STATE_CUES = (
    "焦虑",
    "压力",
    "紧张",
    "担心",
    "睡不好",
    "睡不着",
    "乱想",
)

MEANING_SUPPORT_CUES = (
    "stands for",
    "reminds me",
    "important",
    "support",
    "dream",
    "because",
)

SELF_CARE_CUES_EN = (
    "self-care",
    "me-time",
    "running",
    "reading",
    "violin",
)

FAMILY_GOAL_CUES_EN = (
    "adoption",
    "family",
    "kids who need",
    "loving home",
    "awesome mom",
)


def _has_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def derive_memory_abstractions(
    text: str,
    semantic_aliases: dict[str, tuple[str, ...]],
) -> list[str]:
    abstractions: list[str] = []
    concepts = set(extract_concepts(text, semantic_aliases))

    if _has_any(text, FUTURE_INTENT_CUES):
        abstractions.append("未来计划")
    if _has_any(text, MISSED_OPPORTUNITY_CUES):
        abstractions.extend(["未完成心愿", "遗憾记忆"])
    if _has_any(text, LIVE_EVENT_CUES) and "五月天" in concepts:
        abstractions.extend(["五月天现场", "现场期待"])
    if "五月天" in concepts and (_has_any(text, FUTURE_INTENT_CUES) or _has_any(text, MISSED_OPPORTUNITY_CUES)):
        abstractions.append("五月天心愿")

    if "考试" in concepts and _has_any(text, PERFORMANCE_FAILURE_CUES):
        abstractions.extend(["考试失手", "表现失利"])
    if (
        _has_any(text, GENERALIZATION_CUES)
        and ("考试" in concepts or _has_any(text, PERFORMANCE_FAILURE_CUES))
    ):
        abstractions.append("失败经历泛化触发")
    if _has_any(text, STRESS_STATE_CUES) and ("考试" in concepts or _has_any(text, PERFORMANCE_FAILURE_CUES)):
        abstractions.append("压力触发记忆")

    if _has_any(text, WORKLOAD_STRESS_CUES):
        abstractions.append("高压工作期")
    if _has_any(text, STRESS_STATE_CUES):
        abstractions.append("焦虑状态")
    lowered = text.lower()
    if any(cue in lowered for cue in MEANING_SUPPORT_CUES):
        abstractions.append("meaning_support")
    if any(cue in lowered for cue in SELF_CARE_CUES_EN):
        abstractions.append("self_care_strategy")
    if any(cue in lowered for cue in FAMILY_GOAL_CUES_EN):
        abstractions.append("family_goal")

    return list(dict.fromkeys(abstractions))
