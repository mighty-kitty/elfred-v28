from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


MONTH_PATTERN = (
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december"
)
SURFACE_DATE_RE = re.compile(
    rf"\[(?P<time>[^]]*?) on (?P<day>\d{{1,2}}) (?P<month>{MONTH_PATTERN}), (?P<year>\d{{4}})\]",
    re.IGNORECASE,
)
DAY_FIRST_DATE_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{MONTH_PATTERN})[,]?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
MONTH_FIRST_DATE_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}}),\s*(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
MONTH_YEAR_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
NUMERIC_DAYS_AGO_RE = re.compile(r"\b(?P<count>\d+)\s+days?\s+ago\b", re.IGNORECASE)
WORD_DAYS_AGO_RE = re.compile(
    r"\b(?P<count>one|two|three|four|five|six|seven|eight|nine|ten)\s+days?\s+ago\b",
    re.IGNORECASE,
)
NUMERIC_YEARS_AGO_RE = re.compile(r"\b(?P<count>\d+)\s+years?\s+ago\b", re.IGNORECASE)
WORD_YEARS_AGO_RE = re.compile(
    r"\b(?P<count>one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\s+ago\b",
    re.IGNORECASE,
)
FOR_YEARS_RE = re.compile(
    r"\bfor\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\b",
    re.IGNORECASE,
)
WEEK_BEFORE_DATE_RE = re.compile(
    rf"\b(?:the\s+)?week\s+before\s+(?P<date>(?:\d{{1,2}}\s+(?:{MONTH_PATTERN})[,]?\s+\d{{4}})|(?:(?:{MONTH_PATTERN})\s+\d{{1,2}},\s*\d{{4}}))\b",
    re.IGNORECASE,
)
WEEKEND_BEFORE_DATE_RE = re.compile(
    rf"\b(?:the\s+)?weekend\s+before\s+(?P<date>(?:\d{{1,2}}\s+(?:{MONTH_PATTERN})[,]?\s+\d{{4}})|(?:(?:{MONTH_PATTERN})\s+\d{{1,2}},\s*\d{{4}}))\b",
    re.IGNORECASE,
)
WEEKENDS_BEFORE_DATE_RE = re.compile(
    rf"\b(?P<count>\d+|one|two|three|four)\s+weekends?\s+before\s+(?P<date>(?:\d{{1,2}}\s+(?:{MONTH_PATTERN})[,]?\s+\d{{4}})|(?:(?:{MONTH_PATTERN})\s+\d{{1,2}},\s*\d{{4}}))\b",
    re.IGNORECASE,
)
WEEKDAY_BEFORE_DATE_RE = re.compile(
    rf"\b(?:the\s+)?(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+before\s+(?P<date>(?:\d{{1,2}}\s+(?:{MONTH_PATTERN})[,]?\s+\d{{4}})|(?:(?:{MONTH_PATTERN})\s+\d{{1,2}},\s*\d{{4}}))\b",
    re.IGNORECASE,
)
LAST_WEEKDAY_RE = re.compile(
    r"\blast\s+(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
SUMMER_MONTHS = {"june", "july", "august"}


@dataclass
class TemporalFeatures:
    aliases: list[str] = field(default_factory=list)
    markers: set[str] = field(default_factory=set)
    has_relative_signal: bool = False
    has_duration_signal: bool = False
    has_future_signal: bool = False


def _coerce_count(raw: str) -> int | None:
    lowered = raw.lower().strip()
    if lowered.isdigit():
        return int(lowered)
    return NUMBER_WORDS.get(lowered)


def _parse_date_text(raw: str) -> datetime | None:
    for pattern in (DAY_FIRST_DATE_RE, MONTH_FIRST_DATE_RE):
        match = pattern.search(raw)
        if not match:
            continue
        return datetime.strptime(
            f"{match.group('day')} {match.group('month')} {match.group('year')}",
            "%d %B %Y",
        )
    return None


def _format_day_label(value: datetime) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _anchor_label(value: datetime) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _previous_weekday(anchor: datetime, weekday_name: str) -> datetime:
    target_index = WEEKDAY_TO_INDEX[weekday_name.lower()]
    delta = (anchor.weekday() - target_index) % 7
    if delta == 0:
        delta = 7
    return anchor - timedelta(days=delta)


def _add_absolute_date_features(features: TemporalFeatures, value: datetime) -> None:
    features.aliases.extend(
        [
            str(value.year),
            value.strftime("%B %Y"),
            _format_day_label(value),
        ]
    )
    features.markers.update(
        {
            f"date:{value.strftime('%Y-%m-%d')}",
            f"month:{value.strftime('%Y-%m')}",
            f"month_name:{value.strftime('%B').lower()}",
            f"year:{value.year}",
        }
    )


def _add_relative_anchor_features(features: TemporalFeatures, anchor: datetime, label: str, target: datetime) -> None:
    features.has_relative_signal = True
    features.aliases.append(label)
    _add_absolute_date_features(features, target)
    features.markers.add(f"relative:{label.lower()}")
    features.markers.add(f"relative_anchor:{label.lower()}:{anchor.strftime('%Y-%m-%d')}")


def parse_surface_anchor(text: str) -> datetime | None:
    match = SURFACE_DATE_RE.search(text)
    if not match:
        return None
    return datetime.strptime(
        f"{match.group('day')} {match.group('month')} {match.group('year')}",
        "%d %B %Y",
    )


def extract_temporal_features(text: str) -> TemporalFeatures:
    features = TemporalFeatures()
    lowered = text.lower()
    anchor = parse_surface_anchor(text)
    if anchor:
        features.markers.add(f"anchor:{anchor.strftime('%Y-%m-%d')}")
        _add_absolute_date_features(features, anchor)

    explicit_dates: set[str] = set()
    for pattern in (DAY_FIRST_DATE_RE, MONTH_FIRST_DATE_RE):
        for match in pattern.finditer(text):
            parsed = _parse_date_text(match.group(0))
            if parsed is None:
                continue
            marker = parsed.strftime("%Y-%m-%d")
            if marker in explicit_dates:
                continue
            explicit_dates.add(marker)
            _add_absolute_date_features(features, parsed)

    for match in MONTH_YEAR_RE.finditer(text):
        month_value = match.group("month")
        year_value = int(match.group("year"))
        features.aliases.append(f"{month_value.title()} {year_value}")
        features.markers.add(f"month_name:{month_value.lower()}")
        features.markers.add(f"year:{year_value}")

    for match in YEAR_RE.finditer(text):
        features.aliases.append(match.group(0))
        features.markers.add(f"year:{match.group(0)}")

    if "today" in lowered and anchor:
        _add_relative_anchor_features(features, anchor, f"today {anchor.strftime('%Y-%m-%d')}", anchor)

    if "yesterday" in lowered and anchor:
        _add_relative_anchor_features(features, anchor, f"yesterday {anchor.strftime('%Y-%m-%d')}", anchor - timedelta(days=1))

    if "tomorrow" in lowered and anchor:
        features.has_future_signal = True
        _add_relative_anchor_features(features, anchor, f"tomorrow {anchor.strftime('%Y-%m-%d')}", anchor + timedelta(days=1))

    for pattern in (NUMERIC_DAYS_AGO_RE, WORD_DAYS_AGO_RE):
        for match in pattern.finditer(lowered):
            count = _coerce_count(match.group("count"))
            if count is None or not anchor:
                continue
            target = anchor - timedelta(days=count)
            _add_relative_anchor_features(features, anchor, f"{count} days before {_anchor_label(anchor)}", target)

    if "last week" in lowered and anchor:
        _add_relative_anchor_features(features, anchor, f"the week before {_anchor_label(anchor)}", anchor - timedelta(days=7))

    if "last weekend" in lowered and anchor:
        _add_relative_anchor_features(features, anchor, f"the weekend before {_anchor_label(anchor)}", anchor - timedelta(days=7))

    for match in LAST_WEEKDAY_RE.finditer(lowered):
        weekday_name = match.group("weekday").lower()
        if not anchor:
            continue
        target = _previous_weekday(anchor, weekday_name)
        _add_relative_anchor_features(features, anchor, f"the {weekday_name} before {_anchor_label(anchor)}", target)

    for match in WEEK_BEFORE_DATE_RE.finditer(text):
        target_anchor = _parse_date_text(match.group("date"))
        if target_anchor is None:
            continue
        _add_relative_anchor_features(
            features,
            target_anchor,
            f"the week before {_anchor_label(target_anchor)}",
            target_anchor - timedelta(days=7),
        )

    for match in WEEKEND_BEFORE_DATE_RE.finditer(text):
        target_anchor = _parse_date_text(match.group("date"))
        if target_anchor is None:
            continue
        _add_relative_anchor_features(
            features,
            target_anchor,
            f"the weekend before {_anchor_label(target_anchor)}",
            target_anchor - timedelta(days=7),
        )

    for match in WEEKENDS_BEFORE_DATE_RE.finditer(text):
        target_anchor = _parse_date_text(match.group("date"))
        count = _coerce_count(match.group("count"))
        if target_anchor is None or count is None:
            continue
        _add_relative_anchor_features(
            features,
            target_anchor,
            f"{count} weekends before {_anchor_label(target_anchor)}",
            target_anchor - timedelta(days=7 * count),
        )

    for match in WEEKDAY_BEFORE_DATE_RE.finditer(text):
        target_anchor = _parse_date_text(match.group("date"))
        if target_anchor is None:
            continue
        weekday_name = match.group("weekday").lower()
        _add_relative_anchor_features(
            features,
            target_anchor,
            f"the {weekday_name} before {_anchor_label(target_anchor)}",
            _previous_weekday(target_anchor, weekday_name),
        )

    if "last year" in lowered and anchor:
        features.has_relative_signal = True
        features.aliases.append(str(anchor.year - 1))
        features.markers.add(f"relative:last_year:{anchor.year}")
        features.markers.add(f"year:{anchor.year - 1}")

    if "this year" in lowered and anchor:
        features.aliases.append(str(anchor.year))
        features.markers.add(f"year:{anchor.year}")

    if "this month" in lowered and anchor:
        features.aliases.append(anchor.strftime("%B %Y"))
        features.markers.add(f"month:{anchor.strftime('%Y-%m')}")
        features.markers.add(f"month_name:{anchor.strftime('%B').lower()}")

    if "next month" in lowered and anchor:
        features.has_future_signal = True
        next_month = (anchor.replace(day=1) + timedelta(days=32)).replace(day=1)
        features.aliases.append(next_month.strftime("%B %Y"))
        features.markers.add(f"month:{next_month.strftime('%Y-%m')}")
        features.markers.add(f"month_name:{next_month.strftime('%B').lower()}")
        features.markers.add(f"year:{next_month.year}")

    for pattern in (NUMERIC_YEARS_AGO_RE, WORD_YEARS_AGO_RE):
        for match in pattern.finditer(lowered):
            count = _coerce_count(match.group("count"))
            if count is None:
                continue
            features.has_duration_signal = True
            features.aliases.append(f"{count} years ago")
            features.markers.add(f"duration:years_ago:{count}")
            if anchor:
                features.markers.add(f"year:{anchor.year - count}")
                features.aliases.append(str(anchor.year - count))

    for match in FOR_YEARS_RE.finditer(lowered):
        count = _coerce_count(match.group("count"))
        if count is None:
            continue
        features.has_duration_signal = True
        features.aliases.append(f"{count} years")
        features.markers.add(f"duration:years:{count}")

    if "going to" in lowered or "will " in lowered:
        features.has_future_signal = True

    features.aliases = [alias for alias in dict.fromkeys(alias for alias in features.aliases if alias)]
    return features


def derive_temporal_aliases(text: str) -> list[str]:
    return extract_temporal_features(text).aliases


def extract_temporal_markers(text: str) -> set[str]:
    return extract_temporal_features(text).markers
