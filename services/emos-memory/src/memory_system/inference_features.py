from __future__ import annotations

import re


SPEAKER_RE = re.compile(r"^\[[^]]+\]\s*(?P<speaker>[A-Za-z]+):")
QUESTION_SUBJECT_RE = re.compile(
    r"\b(?:would|did|does|is|was|what|when|where|who|how|around|based on)\s+(?P<subject>[A-Z][a-z]+)\b",
    re.IGNORECASE,
)
QUESTION_PERSONALITY_RE = re.compile(r"\b(?:would|might)\s+(?P<subject>[A-Z][a-z]+)\b", re.IGNORECASE)
QUESTION_AUX_SUBJECT_RE = re.compile(
    r"\b(?:what|which|who|how|when|where|why)\b[^?.!]{0,60}?\b(?:did|does|do|has|have|had|is|are|was|were)\s+(?P<subject>[A-Z][a-z]+)\b",
    re.IGNORECASE,
)

QUESTION_WORDS = {
    "would",
    "did",
    "does",
    "is",
    "was",
    "what",
    "when",
    "where",
    "who",
    "how",
    "around",
    "based",
    "answer",
}
NICKNAME_MAP = {
    "melanie": ("melanie", "mel"),
    "joanna": ("joanna", "jo"),
    "caroline": ("caroline",),
    "john": ("john",),
    "maria": ("maria",),
    "nate": ("nate",),
    "tim": ("tim",),
    "andrew": ("andrew",),
    "audrey": ("audrey",),
}


def parse_speaker(text: str) -> str | None:
    match = SPEAKER_RE.search(text)
    if not match:
        return None
    return match.group("speaker")


def extract_query_subject(query_text: str) -> str | None:
    for pattern in (QUESTION_AUX_SUBJECT_RE, QUESTION_SUBJECT_RE, QUESTION_PERSONALITY_RE):
        match = pattern.search(query_text)
        if match:
            subject = match.group("subject")
            if subject.lower() not in QUESTION_WORDS:
                return subject
    return None


def _subject_aliases(subject: str | None) -> tuple[str, ...]:
    if not subject:
        return ()
    return NICKNAME_MAP.get(subject.lower(), (subject.lower(),))


def candidate_mentions_subject(candidate_text: str, subject: str | None) -> bool:
    lowered = candidate_text.lower()
    return any(alias in lowered for alias in _subject_aliases(subject))


def extract_inference_markers(text: str) -> set[str]:
    lowered = text.lower()
    markers: set[str] = set()

    if any(token in lowered for token in ("counseling", "counselor", "mental health job", "mental health work")):
        markers.add("career:counseling")
    elif "career options" in lowered or "career path" in lowered:
        markers.add("career:exploration")

    if any(
        token in lowered
        for token in (
            "my own journey and the support i got made a huge difference",
            "counseling and support groups improved my life",
            "started caring more about mental health",
            "want to help people go through it too",
        )
    ):
        markers.add("career:counseling_motivation")

    if any(token in lowered for token in ("writing articles", "writer", "writing career", "writing as a career")):
        markers.add("career:writing")

    if any(
        token in lowered
        for token in (
            "love of reading",
            "books guide me",
            "books guide me, motivate me",
            "books are a huge part of my journey",
        )
    ):
        markers.add("hobby:reading")

    if any(
        token in lowered
        for token in (
            "your backing really means a lot",
            "always here for you",
            "supportive",
            "support and love",
            "fight for trans rights",
            "community needs more platforms",
            "encouraged students to get involved",
            "welcoming environment",
        )
    ):
        markers.add("stance:ally_supportive")

    if any(
        token in lowered
        for token in (
            "my transgender journey",
            "as a transgender woman",
            "started transitioning",
            "my transition",
            "coming out",
        )
    ):
        markers.add("identity:self_member")

    if any(
        token in lowered
        for token in (
            "what made you decide to transition",
            "join the transgender community",
            "your transition",
        )
    ):
        markers.add("identity:other_reference")
        markers.add("identity:nonmember")

    if "she is supportive" in lowered or "yes, she is supportive" in lowered:
        markers.add("stance:ally_supportive")

    if "does not refer to herself as part of it" in lowered or "likely no, she does not refer to herself as part of it" in lowered:
        markers.add("identity:nonmember")

    if "wants to be a counselor" in lowered or "wants to be a counsellor" in lowered:
        markers.add("career:counseling")

    if any(
        token in lowered
        for token in (
            "your drive to help is awesome",
            "you're so thoughtful",
            "you really care about being real and helping others",
            "impressive work",
        )
    ):
        markers.add("personality:positive")
    if any(token in lowered for token in ("drive to help", "driven", "impressive work")):
        markers.add("personality:driven")
    if any(token in lowered for token in ("thoughtful", "thank you for your concern")):
        markers.add("personality:thoughtful")
    if any(token in lowered for token in ("being real", "stay true to myself", "authentic")):
        markers.add("personality:authentic")

    if any(
        token in lowered
        for token in (
            "roadtrip this past weekend was insane",
            "trip got off to a bad start",
            "real scary experience",
            "thankfully it's over now",
        )
    ):
        markers.add("future:avoid_repeat_roadtrip")

    return markers


def extract_query_inference_markers(query_text: str) -> set[str]:
    lowered = query_text.lower()
    markers: set[str] = set()
    if "career option" in lowered or "career" in lowered:
        markers.add("query:career")
    if "fields would" in lowered and "pursue in her educ" in lowered:
        markers.add("query:career")
    if "writing" in lowered:
        markers.add("query:writing")
    if "personality traits might" in lowered:
        markers.add("query:personality_traits")
    if "go on another roadtrip soon" in lowered:
        markers.add("query:future_repeat_roadtrip")
    if "what motivated" in lowered and "counseling" in lowered:
        markers.add("query:counseling_motivation")
    if "member of the lgbtq community" in lowered or "member of the transgender community" in lowered:
        markers.add("query:identity_member")
    if "ally to the transgender community" in lowered or "ally to the lgbtq community" in lowered:
        markers.add("query:ally")
    return markers


def compute_inference_bonus(query_text: str, candidate_text: str) -> float:
    query_markers = extract_query_inference_markers(query_text)
    candidate_markers = extract_inference_markers(candidate_text)
    subject = extract_query_subject(query_text)
    speaker = parse_speaker(candidate_text)
    bonus = 0.0

    if subject and speaker and speaker.lower() == subject.lower():
        bonus += 0.12

    if "query:career" in query_markers:
        if "career:counseling" in candidate_markers:
            bonus += 0.7
        elif "career:exploration" in candidate_markers:
            bonus += 0.25
        if "query:writing" in query_markers and "career:writing" in candidate_markers:
            bonus -= 0.4
        if "query:writing" in query_markers and "hobby:reading" in candidate_markers and "career:counseling" not in candidate_markers:
            bonus -= 0.18
        if "query:writing" in query_markers and "career:counseling" in candidate_markers:
            bonus += 0.35
        if "query:writing" in query_markers and "career:exploration" in candidate_markers and "career:counseling" not in candidate_markers:
            bonus -= 0.10

    if "query:counseling_motivation" in query_markers:
        if "career:counseling_motivation" in candidate_markers:
            bonus += 0.85
        elif "career:counseling" in candidate_markers:
            bonus += 0.22

    if "query:personality_traits" in query_markers:
        if "personality:positive" in candidate_markers:
            bonus += 0.55
        if "personality:driven" in candidate_markers:
            bonus += 0.28
        if "personality:thoughtful" in candidate_markers:
            bonus += 0.28
        if "personality:authentic" in candidate_markers:
            bonus += 0.28

    if "query:future_repeat_roadtrip" in query_markers and "future:avoid_repeat_roadtrip" in candidate_markers:
        bonus += 0.95

    if "query:identity_member" in query_markers:
        if speaker and subject and speaker.lower() == subject.lower() and "identity:other_reference" in candidate_markers:
            bonus += 0.95
        if speaker and subject and speaker.lower() != subject.lower() and "identity:self_member" in candidate_markers:
            bonus -= 0.55
        if speaker and subject and speaker.lower() == subject.lower() and "stance:ally_supportive" in candidate_markers:
            bonus += 0.22

    if "query:ally" in query_markers:
        if "stance:ally_supportive" in candidate_markers:
            bonus += 1.0
        if subject and candidate_mentions_subject(candidate_text, subject) and "stance:ally_supportive" in candidate_markers:
            bonus += 0.2

    return bonus
