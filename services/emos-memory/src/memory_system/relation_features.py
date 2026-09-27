from __future__ import annotations

import re
from collections import Counter


SPEAKER_RE = re.compile(r"^\[[^]]+\]\s*(?P<speaker>[A-Za-z]+):")
NAME_RE = re.compile(r"\b[A-Z][a-z]+\b")

TOPIC_CUES: dict[str, tuple[str, ...]] = {
    "topic:exam": ("考试", "test", "exam", "revision", "study"),
    "topic:stress": ("压力", "焦虑", "stress", "anxious", "overwhelmed"),
    "topic:music": ("五月天", "乐队", "music", "song", "listen"),
    "topic:support": ("支持", "陪", "support", "always here", "backing"),
    "topic:identity": ("transgender", "lgbtq", "pride", "coming out", "transition"),
    "topic:work": ("加班", "工作", "overtime", "workload", "office"),
    "topic:career": ("career", "counseling", "writer", "job", "profession"),
    "topic:family": ("family", "adoption", "wedding", "partner", "parents"),
    "topic:hobby": ("painting", "pottery", "camping", "workshop", "conference"),
    "topic:meaning": ("meaning", "stands for", "reminds me", "dream", "important", "support", "love"),
}

OBJECT_CUES: dict[str, tuple[str, ...]] = {
    "object:necklace": ("necklace",),
    "object:bowl": ("bowl", "hand-painted bowl"),
    "object:agency": ("agency", "adoption agency", "adoption agencies"),
    "object:workshop": ("workshop", "counseling workshop"),
    "object:group": ("support group", "adoption advice/assistance group", "activist group"),
    "object:camping_trip": ("camping trip", "went camping", "roasted marshmallows", "campfire", "went on a hike"),
}

ATTRIBUTE_CUES: dict[str, tuple[str, ...]] = {
    "attribute:symbolism": ("stands for", "symbolize", "symbolism", "reminds me"),
    "attribute:origin": ("home country", "from sweden", "grandma", "roots"),
    "attribute:inclusivity": ("inclusive", "inclusivity", "support for lgbtq", "lgbtq folks"),
    "attribute:selfcare": ("self-care", "me-time", "stay present", "look after myself"),
    "attribute:family_goal": ("loving home", "kids who need", "awesome mom", "family for kids"),
    "attribute:detail_list": ("such as", "including", "for activities", "reminds me of"),
}

INTENT_CUES: dict[str, tuple[str, ...]] = {
    "intent:future": ("想去", "打算", "准备", "计划", "will", "going to", "plan to", "looking into", "researching", "applied to", "thinking of", "first step towards"),
    "intent:regret": ("遗憾", "错过", "没做好", "regret", "missed", "should have"),
    "intent:summary": ("总是", "经常", "usually", "generally", "overall"),
}

STATE_CUES: dict[str, tuple[str, ...]] = {
    "state:positive": ("开心", "高兴", "excited", "grateful", "happy"),
    "state:negative": ("难过", "烦", "sad", "upset", "lonely"),
    "state:stress": ("压力", "焦虑", "紧张", "stress", "anxious"),
    "state:supportive": ("支持", "陪伴", "always here", "supportive", "fight for"),
}


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def parse_speaker_marker(text: str) -> str | None:
    match = SPEAKER_RE.search(text)
    if not match:
        return None
    return f"speaker:{match.group('speaker').lower()}"


def extract_relation_markers(text: str, tags: list[str] | None = None, abstractions: list[str] | None = None) -> list[str]:
    markers: list[str] = []
    speaker_marker = parse_speaker_marker(text)
    if speaker_marker:
        markers.append(speaker_marker)

    for cue, patterns in TOPIC_CUES.items():
        if _match_any(text, patterns):
            markers.append(cue)

    for cue, patterns in OBJECT_CUES.items():
        if _match_any(text, patterns):
            markers.append(cue)

    for cue, patterns in ATTRIBUTE_CUES.items():
        if _match_any(text, patterns):
            markers.append(cue)

    for cue, patterns in INTENT_CUES.items():
        if _match_any(text, patterns):
            markers.append(cue)

    for cue, patterns in STATE_CUES.items():
        if _match_any(text, patterns):
            markers.append(cue)

    for name in NAME_RE.findall(text):
        markers.append(f"entity:{name.lower()}")

    for tag in tags or []:
        markers.append(f"tag:{tag}")

    for abstraction in abstractions or []:
        markers.append(f"abstraction:{abstraction}")

    return list(dict.fromkeys(markers))


def summarize_relation_markers(marker_lists: list[list[str]], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for markers in marker_lists:
        counter.update(markers)
    return [marker for marker, _ in counter.most_common(limit)]
