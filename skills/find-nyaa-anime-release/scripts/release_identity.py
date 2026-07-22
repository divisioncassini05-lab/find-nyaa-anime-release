"""Parse release titles into season, episode, and special/regular identity."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


class EpisodeKind(str, Enum):
    REGULAR = "regular"
    SPECIAL = "special"
    BATCH = "batch"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    EXPLICIT = "explicit"
    WEAK = "weak"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReleaseIdentity:
    raw_title: str
    season: int | None
    season_confidence: Confidence
    episode: Decimal | None
    episode_confidence: Confidence
    kind: EpisodeKind
    special_markers: tuple[str, ...] = ()
    episode_start: Decimal | None = None
    episode_end: Decimal | None = None
    covered_seasons: tuple[int, ...] = ()
    coverage_confidence: Confidence = Confidence.UNKNOWN

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["season_confidence"] = self.season_confidence.value
        payload["episode_confidence"] = self.episode_confidence.value
        payload["kind"] = self.kind.value
        payload["episode"] = str(self.episode) if self.episode is not None else None
        payload["episode_start"] = str(self.episode_start) if self.episode_start is not None else None
        payload["episode_end"] = str(self.episode_end) if self.episode_end is not None else None
        payload["covered_seasons"] = list(self.covered_seasons)
        payload["coverage_confidence"] = self.coverage_confidence.value
        payload["special_markers"] = list(self.special_markers)
        return payload


_ROMAN_SEASONS = {
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}
_CJK_NUMBERS = {
    "\u96f6": 0,
    "\u4e00": 1,
    "\u4e8c": 2,
    "\u4e09": 3,
    "\u56db": 4,
    "\u4e94": 5,
    "\u516d": 6,
    "\u4e03": 7,
    "\u516b": 8,
    "\u4e5d": 9,
    "\u5341": 10,
    "\u62fe": 10,
    "\u58f9": 1,
    "\u8d30": 2,
    "\u53c1": 3,
    "\u8086": 4,
    "\u4f0d": 5,
}
_CJK_NUMBER_CLASS = "".join(_CJK_NUMBERS)
_SPECIAL_PATTERNS = {
    "sp": r"(?<![a-z0-9])sp(?:ecial)?s*\d*(?![a-z0-9])",
    "ova": r"(?<![a-z0-9])ova\d*(?![a-z0-9])",
    "oad": r"(?<![a-z0-9])oad\d*(?![a-z0-9])",
    "ncop": r"(?<![a-z0-9])ncop\d*(?![a-z0-9])",
    "nced": r"(?<![a-z0-9])nced\d*(?![a-z0-9])",
    "recap": r"(?<![a-z0-9])(?:recap|bonus|extra|special)(?![a-z0-9])",
    "special_cjk": r"(?:\u7279\u5178|\u7279\u522b\u7bc7|\u7dcf\u96c6\u7bc7|\u603b\u96c6\u7bc7|\u56de\u9867\u7bc7)",
}
_BATCH_PATTERN = re.compile(
    r"\b(?:batch|complete|collection|all\s+episodes?)\b|\u5408\u96c6|\u5168\u96c6|\u5168\u8a71|\u5168\u8bdd|\u5b63\u5ea6\u5168\u96c6",
    re.I,
)
_RANGE_SEPARATOR = r"[-~\u2013\u2014\u301c]"
_TECHNICAL_NUMBER_PATTERNS = (
    re.compile(r"(?<![a-z0-9])\d{1,3}(?:\.\d+)?\s*(?:-\s*)?bit\b", re.I),
    re.compile(r"(?<![a-z0-9])\d{1,3}(?:\.\d+)?\s*(?:fps|hz|khz|kbps|mbps)\b", re.I),
    re.compile(
        r"(?<![a-z0-9])(?:aac|flac|opus|pcm|dts(?:-hd)?|ac-?3|e-?ac-?3|ddp|truehd)"
        r"\s*\d(?:\.\d+)?\b",
        re.I,
    ),
)


def _number_from_token(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    normalized = value.casefold()
    if normalized in _CJK_NUMBERS:
        return _CJK_NUMBERS[normalized]
    for ten_marker in ("\u5341", "\u62fe"):
        if ten_marker not in normalized:
            continue
        left, right = normalized.split(ten_marker, 1)
        if len(left) > 1 or len(right) > 1:
            return None
        tens = _CJK_NUMBERS.get(left, 1) if left else 1
        ones = _CJK_NUMBERS.get(right, 0) if right else 0
        if tens is None or ones is None or tens >= 10 or ones >= 10:
            return None
        return tens * 10 + ones
    return None


def normalize_season_number(value: str | None) -> int | None:
    """Normalize CLI/state season labels such as S04, 4th season, IV, and Chinese labels."""
    if not value:
        return None
    lower = value.casefold().strip()
    for pattern in (
        r"(?<![a-z0-9])s0*(?P<number>\d{1,2})(?![a-z0-9])",
        r"(?<![a-z0-9])season\s*0*(?P<number>\d{1,2})(?![a-z0-9])",
        r"(?<![a-z0-9])(?P<number>\d{1,2})(?:st|nd|rd|th)\s+season(?![a-z0-9])",
        rf"\u7b2c\s*(?P<number>\d+|[{_CJK_NUMBER_CLASS}]+)\s*(?:\u5b63|\u671f)",
    ):
        match = re.search(pattern, lower, re.I)
        if match:
            number = _number_from_token(match.group("number"))
            if number:
                return number
    for roman, number in _ROMAN_SEASONS.items():
        if re.fullmatch(roman, lower, re.I):
            return number
    match = re.search(r"\d+", lower)
    return int(match.group(0)) if match else None


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _covered_seasons_from_title(title: str, season: int | None) -> tuple[int, ...]:
    lower = title.casefold()
    explicit = [int(value) for value in re.findall(r"(?<![a-z0-9])s0*(\d{1,2})(?![a-z0-9])", lower)]
    range_match = re.search(
        rf"(?<![a-z0-9])s0*(?P<start>\d{{1,2}})\s*{_RANGE_SEPARATOR}\s*s?0*(?P<end>\d{{1,2}})(?![a-z0-9])",
        lower,
        re.I,
    )
    if range_match:
        start = int(range_match.group("start"))
        end = int(range_match.group("end"))
        if 0 < start <= end <= 20:
            explicit.extend(range(start, end + 1))
    if season is not None:
        explicit.append(season)
    return tuple(sorted(dict.fromkeys(value for value in explicit if value > 0)))


def _episode_range_from_title(title: str) -> tuple[Decimal | None, Decimal | None, Confidence]:
    lower = title.casefold()
    patterns = (
        re.compile(
            rf"(?<![a-z0-9])(?:e|ep)\s*0*(?P<start>\d{{1,3}})\s*{_RANGE_SEPARATOR}\s*(?:e|ep)?\s*0*(?P<end>\d{{1,3}})(?!\d)",
            re.I,
        ),
        re.compile(
            rf"(?<![a-z0-9])0*(?P<start>\d{{1,3}})\s*{_RANGE_SEPARATOR}\s*0*(?P<end>\d{{1,3}})(?!\d)",
            re.I,
        ),
    )
    for pattern in patterns:
        for match in pattern.finditer(lower):
            prefix = lower[max(0, match.start() - 8) : match.start()]
            if re.search(r"(?:vol(?:ume)?|disc|disk|cd|season|s)\s*[._-]?\s*$", prefix, re.I):
                continue
            start = _decimal(match.group("start"))
            end = _decimal(match.group("end"))
            if start is None or end is None:
                continue
            if start < 0 or end <= start or end > Decimal("200"):
                continue
            return start, end, Confidence.EXPLICIT
    return None, None, Confidence.UNKNOWN


def _season_from_title(title: str) -> tuple[int | None, Confidence, tuple[int, int] | None]:
    lower = title.casefold()
    patterns = (
        (
            Confidence.EXPLICIT,
            re.compile(r"(?<![a-z0-9])s0*(?P<number>\d{1,2})(?=\s*(?:e\d|\b))", re.I),
        ),
        (
            Confidence.EXPLICIT,
            re.compile(r"(?<![a-z0-9])(?P<number>\d{1,2})(?:st|nd|rd|th)\s+season(?![a-z0-9])", re.I),
        ),
        (
            Confidence.EXPLICIT,
            re.compile(r"(?<![a-z0-9])season\s*0*(?P<number>\d{1,2})(?![a-z0-9])", re.I),
        ),
        (
            Confidence.EXPLICIT,
            re.compile(rf"\u7b2c\s*(?P<number>\d+|[{_CJK_NUMBER_CLASS}]+)\s*(?:\u5b63|\u671f)"),
        ),
    )
    for confidence, pattern in patterns:
        match = pattern.search(lower)
        if not match:
            continue
        number = _number_from_token(match.group("number"))
        if number:
            return number, confidence, match.span()

    for roman, number in _ROMAN_SEASONS.items():
        match = re.search(rf"(?<![a-z0-9]){roman}(?![a-z0-9])", lower)
        if match:
            return number, Confidence.WEAK, match.span()
    return None, Confidence.UNKNOWN, None


def _episode_from_title(
    title: str, season_span: tuple[int, int] | None
) -> tuple[Decimal | None, Confidence]:
    lower = title.casefold()
    explicit_patterns = (
        re.compile(
            r"(?<![a-z0-9])s0*\d{1,2}\s*e(?:p(?:isode)?)?\s*0*(?P<episode>\d+(?:\.\d+)?)(?:v\d+)?(?![a-z0-9])",
            re.I,
        ),
        re.compile(r"(?<![a-z0-9])\d{1,2}x0*(?P<episode>\d+(?:\.\d+)?)(?:v\d+)?(?![a-z0-9])", re.I),
        re.compile(r"(?<![a-z0-9])(?:episode|ep|e)\s*0*(?P<episode>\d+(?:\.\d+)?)(?:v\d+)?(?![a-z0-9])", re.I),
    )
    for pattern in explicit_patterns:
        match = pattern.search(lower)
        if match:
            return _decimal(match.group("episode")), Confidence.EXPLICIT

    if season_span is not None:
        after_season = lower[season_span[1] :]
        match = re.match(
            r"\s*(?:[-_:]\s*|\s+)(?P<episode>\d+(?:\.\d+)?)(?:v\d+)?(?=\s*(?:\[|\(|\{|sp\b|\.[a-z0-9]{2,5}\b|$))",
            after_season,
            re.I,
        )
        if match:
            return _decimal(match.group("episode")), Confidence.EXPLICIT

    for match in re.finditer(r"[\[\(\u3010]\s*0*(?P<episode>\d+(?:\.\d+)?)(?:v\d+)?\s*[\]\)\u3011]", lower):
        value = _decimal(match.group("episode"))
        if value is not None and value < Decimal("100"):
            return value, Confidence.WEAK

    technical_spans = [
        technical_match.span()
        for pattern in _TECHNICAL_NUMBER_PATTERNS
        for technical_match in pattern.finditer(lower)
    ]
    for match in re.finditer(
        r"(?:^|[\s_-])0*(?P<episode>\d{1,3}(?:\.\d+)?)(?:v\d+)?(?=$|[.\s_\-\[\]\(\)\u3010\u3011])",
        lower,
    ):
        if season_span and season_span[0] <= match.start("episode") < season_span[1]:
            continue
        episode_span = match.span("episode")
        if any(
            episode_span[0] < technical_end and technical_start < episode_span[1]
            for technical_start, technical_end in technical_spans
        ):
            continue
        value = _decimal(match.group("episode"))
        if value is not None and value < Decimal("100"):
            return value, Confidence.WEAK
    return None, Confidence.UNKNOWN


def parse_release_identity(title: str) -> ReleaseIdentity:
    season, season_confidence, season_span = _season_from_title(title)
    covered_seasons = _covered_seasons_from_title(title, season)
    episode_start, episode_end, range_confidence = _episode_range_from_title(title)
    episode, episode_confidence = _episode_from_title(title, season_span)
    lower = title.casefold()
    special_markers = tuple(
        name for name, pattern in _SPECIAL_PATTERNS.items() if re.search(pattern, lower, re.I)
    )
    if episode is not None and episode != episode.to_integral_value():
        special_markers = tuple(dict.fromkeys([*special_markers, "decimal_episode"]))

    season_only_package = bool(
        season is not None
        and season_confidence is Confidence.EXPLICIT
        and episode is None
        and not special_markers
    )
    batch_marked = bool(
        episode_start is not None
        or len(covered_seasons) > 1
        or _BATCH_PATTERN.search(title)
        or season_only_package
    )
    if batch_marked:
        kind = EpisodeKind.BATCH
        episode = None
        episode_confidence = Confidence.UNKNOWN
    elif special_markers:
        kind = EpisodeKind.SPECIAL
    elif episode is not None:
        kind = EpisodeKind.REGULAR
    else:
        kind = EpisodeKind.UNKNOWN
    coverage_confidence = range_confidence
    if coverage_confidence is Confidence.UNKNOWN and batch_marked:
        coverage_confidence = Confidence.WEAK
    return ReleaseIdentity(
        raw_title=title,
        season=season,
        season_confidence=season_confidence,
        episode=episode,
        episode_confidence=episode_confidence,
        kind=kind,
        special_markers=special_markers,
        episode_start=episode_start,
        episode_end=episode_end,
        covered_seasons=covered_seasons,
        coverage_confidence=coverage_confidence,
    )


def season_relation(identity: ReleaseIdentity, requested_season: int | None) -> str:
    if requested_season is None:
        return "not_requested"
    if identity.covered_seasons:
        return "match" if requested_season in identity.covered_seasons else "other"
    if identity.season is None:
        return "unknown"
    return "match" if identity.season == requested_season else "other"


def is_exact_regular_episode(
    identity: ReleaseIdentity, requested_season: int | None, requested_episode: int | None
) -> bool:
    if identity.kind is not EpisodeKind.REGULAR or identity.episode is None:
        return False
    if requested_season is not None and season_relation(identity, requested_season) != "match":
        return False
    return requested_episode is None or identity.episode == Decimal(requested_episode)
