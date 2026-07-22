#!/usr/bin/env python3
"""Search Nyaa RSS and rank anime release candidates.

This helper intentionally omits magnet links unless both --include-magnets and
--legal-ok are supplied by the caller.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Iterable


NYAA_RSS = "https://nyaa.si/"
NYAA_NS = "{https://nyaa.si/xmlns/nyaa}"

ASCII_CHINESE_PATTERNS = {
    "CHS": r"(?<![a-z0-9])chs(?![a-z0-9])",
    "CHT": r"(?<![a-z0-9])cht(?![a-z0-9])",
    "SC": r"(?<![a-z0-9])sc(?![a-z0-9])",
    "TC": r"(?<![a-z0-9])tc(?![a-z0-9])",
    "GB": r"(?<![a-z0-9])gb(?![a-z0-9])",
    "BIG5": r"(?<![a-z0-9])big5(?![a-z0-9])",
    "Chinese": r"(?<![a-z0-9])chinese(?![a-z0-9])",
    "zh-cn": r"(?<![a-z0-9])zh-cn(?![a-z0-9])",
    "zh-tw": r"(?<![a-z0-9])zh-tw(?![a-z0-9])",
}
UNICODE_CHINESE_MARKERS = (
    "\u7b80\u7e41",
    "\u4e2d\u6587\u5b57\u5e55",
    "\u4e2d\u6587",
    "\u5167\u5c01",
    "\u5185\u5c01",
    "\u5916\u6302",
    "\u5916\u639b",
    "\u7b80",
    "\u7e41",
)
DETAIL_SUBTITLE_CONTEXT_PATTERNS = (
    r"subtitle(?:s| languages?)?",
    r"sub languages?",
    r"text\s*#",
    r"caption(?:s)?",
    "\u5b57\u5e55",
    "\u5185\u5c01",
    "\u5167\u5c01",
    "\u5916\u6302",
    "\u5916\u639b",
)
DETAIL_SUBTITLE_MODE_PATTERN = (
    r"(?:hard|soft)[-_ ]?sub|hardsub|softsub|"
    "\u5185\u5d4c|\u5167\u5d4c|\u5185\u5c01|\u5167\u5c01|\u5916\u6302|\u5916\u639b"
)
DETAIL_CHINESE_NEGATION_PATTERN = (
    r"(?:no|not|without|exclude(?:s|d)?|except)\s+(?:simplified\s+|traditional\s+)?chinese|"
    r"chinese(?:\s+subtitle(?:s)?)?\s*(?::|=|-)?\s*(?:no|none|false|absent|not\s+included)|"
    "\u65e0\u4e2d\u6587|\u7121\u4e2d\u6587|\u4e0d\u542b\u4e2d\u6587|\u4e0d\u5305\u542b\u4e2d\u6587"
)
DETAIL_AUDIO_CONTEXT_PATTERN = (
    r"(?<![a-z0-9])(?:audio|dub(?:bed)?)(?![a-z0-9])|"
    "\u97f3\u8f68|\u97f3\u8ecc|\u97f3\u9891|\u97f3\u983b|\u914d\u97f3"
)
DETAIL_SUBTITLE_FILE_PATTERN = r"\.(?:ass|ssa|srt|vtt|sup)(?:\b|$)"
DETAIL_CHINESE_PATTERNS = {
    "Chinese": r"(?<![a-z0-9])chinese(?![a-z0-9])",
    "Simplified Chinese": r"(?<![a-z0-9])simplified[-_ ]+chinese(?![a-z0-9])",
    "Traditional Chinese": r"(?<![a-z0-9])traditional[-_ ]+chinese(?![a-z0-9])",
    "zh-cn": r"(?<![a-z0-9])zh[-_ ]?cn(?![a-z0-9])",
    "zh-tw": r"(?<![a-z0-9])zh[-_ ]?tw(?![a-z0-9])",
    "zh-Hans": r"(?<![a-z0-9])zh[-_ ]?hans(?![a-z0-9])",
    "zh-Hant": r"(?<![a-z0-9])zh[-_ ]?hant(?![a-z0-9])",
    "CHS": r"(?<![a-z0-9])chs(?![a-z0-9])",
    "CHT": r"(?<![a-z0-9])cht(?![a-z0-9])",
    "BIG5": r"(?<![a-z0-9])big5(?![a-z0-9])",
}
DETAIL_CHINESE_LITERALS = (
    "\u4e2d\u6587",
    "\u4e2d\u6587\u5b57\u5e55",
    "\u7b80\u4f53",
    "\u7c21\u9ad4",
    "\u7e41\u4f53",
    "\u7e41\u9ad4",
    "\u7b80\u4e2d",
    "\u7e41\u4e2d",
    "\u7b80\u65e5",
    "\u7e41\u65e5",
    "\u7b80\u7e41",
    "\u7c21\u7e41",
)
ORIGINAL_AUDIO_PATTERNS = {
    "Japanese": r"(?<![a-z0-9])(?:japanese|jpn|jap|jp|ja)(?![a-z0-9])",
    "JPN audio": r"(?<![a-z0-9])(?:jpn|jap|jp|ja)[-_ ]?audio(?![a-z0-9])",
    "日本語": "\u65e5\u672c\u8a9e",
    "日语": "\u65e5\u8bed",
    "原声": "\u539f\u58f0",
    "原配": "\u539f\u914d",
}
DUB_ONLY_PATTERNS = {
    "English dub": r"(?<![a-z0-9])english[-_ ]?dub(?:bed)?(?![a-z0-9])",
    "Chinese dub": r"(?<![a-z0-9])chinese[-_ ]?dub(?:bed)?(?![a-z0-9])",
    "Dubbed": r"(?<![a-z0-9])dubbed(?![a-z0-9])",
    "国语": "\u56fd\u8bed",
    "國語": "\u570b\u8a9e",
    "粤语": "\u7ca4\u8bed",
    "粵語": "\u7cb5\u8a9e",
    "中配": "\u4e2d\u914d",
}
MULTI_AUDIO_PATTERN = r"(?<![a-z0-9])(?:dual|multi)[-_ ]?audio(?![a-z0-9])"

TIER_PROFILES = {
    # Use actual single-episode size. Short runtimes never reduce these floors.
    "browse": {"label": "casual/space-saving", "ideal_gib_per_episode": (1.0, 2.0)},
    "watch": {"label": "normal watching", "ideal_gib_per_episode": (2.0, 4.0)},
    "premium": {"label": "premium/BD-like", "ideal_gib_per_episode": (6.0, 999.0)},
}
DEFAULT_TIER_MIN_GIB = {"browse": 1.0, "watch": 2.0, "premium": 6.0}
TIER_ALIASES = {
    "casual": "browse",
    "browse": "browse",
    "look": "browse",
    "normal": "watch",
    "watch": "watch",
    "good": "watch",
    "premium": "premium",
    "best": "premium",
    "4k": "premium",
    "bd": "premium",
}


@dataclass
class Candidate:
    rank: int
    score: float
    title: str
    group: str | None
    resolution: str | None
    codec: str | None
    bit_depth: str | None
    audio_signal: str
    subtitle_signal: str
    size: str | None
    size_bytes: int | None
    size_basis: str
    bitrate_note: str
    tier_fit: str
    seeders: int
    leechers: int
    downloads: int
    published: str | None
    category: str | None
    url: str | None
    magnet: str | None
    matched_queries: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    detail_checked: bool = False
    detail_chinese_confirmed: bool = False
    detail_subtitle_signal: str | None = None


@dataclass(frozen=True)
class NyaaFileEntry:
    name: str
    size: str
    size_bytes: int | None


def text_of(parent: ET.Element, tag: str, default: str = "") -> str:
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else default


def nyaa_text(parent: ET.Element, name: str, default: str = "") -> str:
    node = parent.find(f"{NYAA_NS}{name}")
    return (node.text or "").strip() if node is not None else default


def as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_size(value: str) -> int | None:
    if not value:
        return None
    match = re.search(r"([\d.]+)\s*([kmgt]i?b)", value, re.I)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).lower()
    powers = {"kb": 1, "kib": 1, "mb": 2, "mib": 2, "gb": 3, "gib": 3, "tb": 4, "tib": 4}
    base = 1024 if "i" in unit else 1000
    return int(amount * (base ** powers[unit]))


def bytes_to_gib(size_bytes: int) -> float:
    return size_bytes / (1024**3)


def detect_group(title: str) -> str | None:
    match = re.match(r"^\s*[\[\u3010]([^\]\u3011]{1,64})[\]\u3011]", title)
    if match:
        return match.group(1).strip()
    for suffix_group in ("VARYG", "Tsundere-Raws", "NanDesuKa"):
        if re.search(rf"[- ]{re.escape(suffix_group)}(?:\s|$|\()", title, re.I):
            return suffix_group
    return None


def detect_resolution(title: str) -> str | None:
    match = re.search(r"(2160p|1440p|1080p|720p|480p|\d{3,4}x\d{3,4})", title, re.I)
    return match.group(1) if match else None


def detect_codec(title: str) -> str | None:
    lowered = title.lower()
    if any(token in lowered for token in ("hevc", "h.265", "h265", "x265")):
        return "HEVC"
    if any(token in lowered for token in ("avc", "h.264", "h264", "x264")):
        return "AVC"
    if "av1" in lowered:
        return "AV1"
    return None


def detect_bit_depth(title: str) -> str | None:
    match = re.search(r"(8|10|12)\s*-?\s*bit", title, re.I)
    return f"{match.group(1)}bit" if match else None


def detect_chinese(title: str) -> tuple[bool, str]:
    hits = [name for name, pattern in ASCII_CHINESE_PATTERNS.items() if re.search(pattern, title, re.I)]
    hits.extend(marker for marker in UNICODE_CHINESE_MARKERS if marker in title)
    if hits:
        return True, ", ".join(dict.fromkeys(hits))
    return False, "not confirmed"


def strip_html_to_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"</(?:p|div|li|tr|h\d)>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"[ \t]+", " ", value)).replace("\r", "")


def extract_nyaa_description(page_html: str) -> str:
    """Extract the release title, description, and file list from one Nyaa detail page."""
    patterns = (
        r"<h3[^>]*class=[\"'][^\"']*panel-title[^\"']*[\"'][^>]*>(.*?)</h3>",
        r"<div[^>]+id=[\"']torrent-description[\"'][^>]*>(.*?)</div>",
        r"<div[^>]+class=[\"'][^\"']*torrent-file-list[^\"']*[\"'][^>]*>(.*?)</div>",
    )
    fragments: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, page_html, re.I | re.S)
        if match:
            fragments.append(match.group(1))
    return strip_html_to_text("\n".join(fragments) if fragments else page_html)


def fetch_nyaa_detail_page(url: str, timeout: int | float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "CodexSkill/1.1 (+https://nyaa.si/)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def fetch_nyaa_detail_text(url: str, timeout: int | float) -> str:
    return extract_nyaa_description(fetch_nyaa_detail_page(url, timeout))


class _NyaaFileListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.panel_depth = 0
        self.li_stack: list[dict[str, object]] = []
        self.entries: list[NyaaFileEntry] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").casefold().split())
        if tag.casefold() == "div" and "torrent-file-list" in classes:
            self.panel_depth = 1
            return
        if not self.panel_depth:
            return
        if tag.casefold() == "div":
            self.panel_depth += 1
        elif tag.casefold() == "li":
            self.li_stack.append({"text": [], "size": [], "in_size": False})
        elif tag.casefold() == "span" and self.li_stack and "file-size" in classes:
            self.li_stack[-1]["in_size"] = True

    def handle_endtag(self, tag: str) -> None:
        if not self.panel_depth:
            return
        lowered = tag.casefold()
        if lowered == "span" and self.li_stack:
            self.li_stack[-1]["in_size"] = False
        elif lowered == "li" and self.li_stack:
            node = self.li_stack.pop()
            size = " ".join(node["size"]).strip().strip("()")  # type: ignore[arg-type]
            leaf = " ".join(node["text"]).strip().strip("/\\")  # type: ignore[arg-type]
            if size and leaf:
                parents = [
                    " ".join(parent["text"]).strip().strip("/\\")  # type: ignore[arg-type]
                    for parent in self.li_stack
                ]
                name = "/".join(part for part in [*parents, leaf] if part)
                self.entries.append(
                    NyaaFileEntry(name=name, size=size, size_bytes=parse_size(size))
                )
        elif lowered == "div":
            self.panel_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.panel_depth or not self.li_stack or not data.strip():
            return
        key = "size" if self.li_stack[-1]["in_size"] else "text"
        self.li_stack[-1][key].append(data.strip())  # type: ignore[union-attr]


def extract_nyaa_file_entries(page_html: str) -> list[NyaaFileEntry]:
    """Return structured file rows, retaining nested directory names."""
    parser = _NyaaFileListParser()
    parser.feed(page_html)
    parser.close()
    return parser.entries


def detect_chinese_in_detail(detail_text: str) -> tuple[bool, str]:
    lines = [line.strip() for line in detail_text.splitlines() if line.strip()]
    hits: list[str] = []
    for index, line in enumerate(lines):
        line_hits = [name for name, pattern in DETAIL_CHINESE_PATTERNS.items() if re.search(pattern, line, re.I)]
        line_hits.extend(marker for marker in DETAIL_CHINESE_LITERALS if marker in line)
        if not line_hits:
            continue
        prior_window = " | ".join(lines[max(0, index - 3) : index + 1])
        surrounding_window = " | ".join(lines[max(0, index - 3) : min(len(lines), index + 4)])
        if re.search(DETAIL_CHINESE_NEGATION_PATTERN, line, re.I):
            continue
        line_has_context = any(
            re.search(pattern, line, re.I) for pattern in DETAIL_SUBTITLE_CONTEXT_PATTERNS
        )
        prior_has_context = any(
            re.search(pattern, prior_window, re.I) for pattern in DETAIL_SUBTITLE_CONTEXT_PATTERNS
        )
        surrounding_has_context = any(
            re.search(pattern, surrounding_window, re.I)
            for pattern in DETAIL_SUBTITLE_CONTEXT_PATTERNS
        )
        surrounding_has_mode = bool(
            re.search(DETAIL_SUBTITLE_MODE_PATTERN, surrounding_window, re.I)
        )
        direct_subtitle_file = bool(re.search(DETAIL_SUBTITLE_FILE_PATTERN, line, re.I))
        audio_only_line = bool(re.search(DETAIL_AUDIO_CONTEXT_PATTERN, line, re.I)) and not line_has_context
        if audio_only_line:
            continue
        if (
            line_has_context
            or direct_subtitle_file
            or prior_has_context
            or (surrounding_has_context and surrounding_has_mode)
        ):
            hits.extend(line_hits)
    if hits:
        return True, "detail-page: " + ", ".join(dict.fromkeys(hits))
    return False, "detail-page: not confirmed"


def apply_detail_subtitle_signal(candidate: Candidate, detail_text: str, want_zh: bool, airing_priority: bool) -> None:
    has_zh, signal = detect_chinese_in_detail(detail_text)
    candidate.detail_checked = True
    candidate.detail_chinese_confirmed = has_zh
    candidate.detail_subtitle_signal = signal
    if not has_zh:
        candidate.reasons.append(signal)
        return

    if candidate.subtitle_signal == "not confirmed":
        candidate.subtitle_signal = signal
    else:
        candidate.subtitle_signal = f"{candidate.subtitle_signal}; {signal}"

    if candidate.tier_fit != "in-tier":
        candidate.reasons.append(f"Chinese/mixed subtitles confirmed in Nyaa details but not used for rank outside quality tier: {signal}")
        return

    if want_zh:
        subtitle_bonus = 8.0 if airing_priority else 1.5
        candidate.score += subtitle_bonus
        reason_prefix = "airing same-tier" if airing_priority else "same-tier"
        candidate.reasons.append(f"{reason_prefix} Chinese/mixed subtitle tie-breaker from Nyaa details: {signal}")
    else:
        subtitle_bonus = 2.0 if airing_priority else 0.5
        candidate.score += subtitle_bonus
        reason_prefix = "airing same-tier" if airing_priority else "same-tier"
        candidate.reasons.append(f"{reason_prefix} subtitle signal in Nyaa details: {signal}")


def detect_audio(title: str) -> tuple[float, str]:
    original_hits = [name for name, pattern in ORIGINAL_AUDIO_PATTERNS.items() if re.search(pattern, title, re.I)]
    dub_hits = [name for name, pattern in DUB_ONLY_PATTERNS.items() if re.search(pattern, title, re.I)]
    multi_audio = bool(re.search(MULTI_AUDIO_PATTERN, title, re.I))

    if original_hits:
        return 12.0, "original audio confirmed: " + ", ".join(dict.fromkeys(original_hits))
    if multi_audio and not dub_hits:
        return 7.0, "dual/multi audio; original audio likely but not explicit"
    if multi_audio and dub_hits:
        return 4.0, "dual/multi audio with dub signal: " + ", ".join(dict.fromkeys(dub_hits))
    if dub_hits:
        return -28.0, "dub-only/alternate dub signal: " + ", ".join(dict.fromkeys(dub_hits))
    return 0.0, "original audio not stated"


def looks_batch(title: str) -> bool:
    from release_identity import EpisodeKind, parse_release_identity

    return parse_release_identity(title).kind is EpisodeKind.BATCH


def normalize_tier(tier: str) -> str:
    normalized = tier.strip().lower()
    if normalized not in TIER_ALIASES:
        allowed = ", ".join(sorted(TIER_PROFILES))
        raise argparse.ArgumentTypeError(f"unknown tier '{tier}', choose one of: {allowed}")
    return TIER_ALIASES[normalized]


def bitrate_size_score(
    size_bytes: int | None,
    tier: str,
    _duration_min: float,
    episodes: int | None,
    batch: bool,
) -> tuple[float, str, str, str]:
    if size_bytes is None:
        return -40, "size unavailable; bitrate cannot be judged", "unknown", "unknown"

    total_gib = bytes_to_gib(size_bytes)
    if episodes and episodes > 0:
        comparable_gib = total_gib / episodes
        basis = f"{comparable_gib:.2f} GiB/episode from {episodes}-episode batch"
    elif batch:
        return -25, "batch size without --episodes; bitrate not comparable", f"{total_gib:.2f} GiB batch", "unknown"
    else:
        comparable_gib = total_gib
        basis = f"{comparable_gib:.2f} GiB single release"

    profile = TIER_PROFILES[tier]
    ideal = profile["ideal_gib_per_episode"]
    target_mid = (ideal[0] + ideal[1]) / 2

    if ideal[0] <= comparable_gib <= ideal[1]:
        center_distance = abs(comparable_gib - target_mid) / max(target_mid, 0.01)
        return 80 - min(10, center_distance * 10), f"bitrate/size matches {profile['label']} tier", basis, "in-tier"
    if comparable_gib < ideal[0]:
        return -70, f"below {profile['label']} tier size target; belongs to a lower tier", basis, "below"
    return -35, f"above {profile['label']} tier size target; belongs to a higher tier", basis, "above"


def comparable_gib_per_episode(candidate: Candidate, episodes: int | None) -> float | None:
    if candidate.size_bytes is None:
        return None
    total_gib = bytes_to_gib(candidate.size_bytes)
    if episodes and episodes > 0:
        return total_gib / episodes
    if looks_batch(candidate.title):
        return None
    return total_gib


def normalize_season_number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def has_season_marker(title: str, season_number: int) -> bool:
    roman_markers = {
        2: ("ii", "Ⅱ"),
        3: ("iii", "Ⅲ"),
        4: ("iv", "Ⅳ"),
        5: ("v", "Ⅴ"),
    }
    chinese_markers = {
        1: ("一", "壹"),
        2: ("二", "两", "貳", "贰"),
        3: ("三", "叁"),
        4: ("四", "肆"),
        5: ("五", "伍"),
    }
    return any(
        re.search(pattern, title)
        for pattern in (
            rf"(?<![a-z0-9])s0*{season_number}(?![a-z0-9])",
            rf"(?<![a-z0-9])season\s*0*{season_number}(?![a-z0-9])",
            rf"第\s*{season_number}\s*季",
            *(
                rf"第\s*{re.escape(marker)}\s*季"
                for marker in chinese_markers.get(season_number, ())
            ),
            *(
                rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])"
                for marker in roman_markers.get(season_number, ())
            ),
        )
    )


def generic_episode_match(title: str, episode: int) -> bool:
    return bool(
        re.search(
            rf"(?:^|[\s_\-\[\]\(\)【】第])0*{episode}(?:v\d+)?(?:$|[\s_\-\]\)】话話集])",
            title,
        )
    )


def target_episode_label(season: str | None, episode: int | None) -> str:
    if episode is None:
        return season or "requested target"
    season_number = normalize_season_number(season)
    if season_number is not None:
        return f"S{season_number:02d}E{episode:02d}"
    return f"E{episode:02d}"


def magnet_from_hash(info_hash: str, title: str) -> str | None:
    if not info_hash:
        return None
    return "magnet:?xt=urn:btih:{}&dn={}".format(info_hash, urllib.parse.quote(title))


def normalize_nyaa_url(link: str, guid: str) -> str | None:
    source = guid or link
    if not source:
        return None
    match = re.search(r"nyaa\.si/(?:view|download)/(\d+)(?:\.torrent)?", source)
    if match:
        return f"https://nyaa.si/view/{match.group(1)}"
    return source


def build_url(query: str, category: str, nyaa_filter: str) -> str:
    params = {"page": "rss", "q": query, "c": category, "f": nyaa_filter}
    return NYAA_RSS + "?" + urllib.parse.urlencode(params)


def fetch_rss(query: str, category: str, nyaa_filter: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        build_url(query, category, nyaa_filter),
        headers={"User-Agent": "CodexSkill/1.1 (+https://nyaa.si/)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def score_item(
    item: ET.Element,
    query: str,
    want_zh: bool,
    airing_priority: bool,
    desired_resolution: str | None,
    tier: str,
    duration_min: float,
    episodes: int | None,
    prefer_groups: Iterable[str],
    avoid_groups: Iterable[str],
    include_magnets: bool,
) -> Candidate:
    title = text_of(item, "title")
    link = text_of(item, "link")
    guid = text_of(item, "guid")
    url = normalize_nyaa_url(link, guid)
    size = nyaa_text(item, "size") or None
    size_bytes = parse_size(size or "")
    seeders = as_int(nyaa_text(item, "seeders"))
    leechers = as_int(nyaa_text(item, "leechers"))
    downloads = as_int(nyaa_text(item, "downloads"))
    category = nyaa_text(item, "category") or None
    info_hash = nyaa_text(item, "infoHash")
    published_raw = text_of(item, "pubDate")

    try:
        published = parsedate_to_datetime(published_raw).date().isoformat() if published_raw else None
    except (TypeError, ValueError):
        published = published_raw or None

    group = detect_group(title)
    resolution = detect_resolution(title)
    codec = detect_codec(title)
    bit_depth = detect_bit_depth(title)
    audio_score, audio_signal = detect_audio(title)
    has_zh, subtitle_signal = detect_chinese(title)
    batch = looks_batch(title)
    size_score, size_note, size_basis, tier_fit = bitrate_size_score(size_bytes, tier, duration_min, episodes, batch)

    score = 0.0
    reasons: list[str] = []

    score += size_score
    reasons.append(size_note)

    swarm_score = min(18.0, math.log2(seeders + 1) * 3)
    download_score = min(10.0, math.log10(downloads + 1) * 3)
    leech_score = min(2.0, math.log2(leechers + 1) * 0.5)
    score += swarm_score + download_score + leech_score
    reasons.append(f"{seeders} seeders, {downloads} downloads")

    normalized_group = (group or "").lower()
    preferred = {g.lower() for g in prefer_groups}
    avoided = {g.lower() for g in avoid_groups}
    if normalized_group and normalized_group in preferred and tier_fit == "in-tier":
        score += 14
        reasons.append(f"preferred group: {group}")
    elif normalized_group and normalized_group in preferred:
        reasons.append(f"preferred group not used for rank outside quality tier: {group}")
    if normalized_group and normalized_group in avoided:
        score -= 25
        reasons.append(f"avoided group: {group}")

    if audio_score:
        score += audio_score
    reasons.append(audio_signal)

    if desired_resolution and resolution and desired_resolution.lower() == resolution.lower():
        score += 8
        reasons.append(f"matches {desired_resolution}")
    elif not desired_resolution and resolution:
        if tier == "premium" and "2160" in resolution:
            score += 8
            reasons.append("2160p detected for premium tier")
        elif tier != "premium" and "1080" in resolution:
            score += 5
            reasons.append("1080p detected")

    if codec in {"HEVC", "AV1"}:
        score += 4
        reasons.append(codec)
    elif codec == "AVC":
        score += 2
        reasons.append(codec)
    if bit_depth in {"10bit", "12bit"}:
        score += 3
        reasons.append(bit_depth)

    if want_zh and has_zh:
        if tier_fit == "in-tier":
            subtitle_bonus = 5.0 if airing_priority else 1.0
            score += subtitle_bonus
            reason_prefix = "airing same-tier" if airing_priority else "same-tier"
            reasons.append(f"{reason_prefix} Chinese/mixed subtitle tie-breaker: {subtitle_signal}")
        else:
            reasons.append(f"Chinese/mixed subtitle signal not used for rank outside quality tier: {subtitle_signal}")
    elif has_zh:
        if tier_fit == "in-tier":
            subtitle_bonus = 1.5 if airing_priority else 0.25
            score += subtitle_bonus
            reason_prefix = "airing same-tier" if airing_priority else "same-tier"
            reasons.append(f"{reason_prefix} subtitle signal: {subtitle_signal}")
        else:
            reasons.append(f"subtitle signal not used for rank outside quality tier: {subtitle_signal}")
    elif want_zh:
        reasons.append("Chinese/mixed subtitles not confirmed")

    magnet = magnet_from_hash(info_hash, title) if include_magnets else None
    return Candidate(
        rank=0,
        score=round(score, 2),
        title=title,
        group=group,
        resolution=resolution,
        codec=codec,
        bit_depth=bit_depth,
        audio_signal=audio_signal,
        subtitle_signal=subtitle_signal,
        size=size,
        size_bytes=size_bytes,
        size_basis=size_basis,
        bitrate_note=size_note,
        tier_fit=tier_fit,
        seeders=seeders,
        leechers=leechers,
        downloads=downloads,
        published=published,
        category=category,
        url=url,
        magnet=magnet,
        matched_queries=[query],
        reasons=reasons,
    )


def merge_candidate(existing: Candidate, incoming: Candidate) -> Candidate:
    existing.matched_queries.extend(q for q in incoming.matched_queries if q not in existing.matched_queries)
    if incoming.score > existing.score:
        incoming.matched_queries = existing.matched_queries
        return incoming
    return existing


def render_markdown(candidates: list[Candidate], include_magnets: bool, magnet_only: bool) -> str:
    if not candidates:
        return "No matching Nyaa RSS results found."

    lines: list[str] = []
    for candidate in candidates:
        meta = " ".join(part for part in (candidate.resolution, candidate.codec, candidate.bit_depth) if part)
        suffix = f" ({meta})" if meta else ""
        lines.append(f"{candidate.rank}. {candidate.title}{suffix}")
        lines.append(
            "   Score: {score} | Group: {group} | Size: {size} | Basis: {basis}".format(
                score=candidate.score,
                group=candidate.group or "unknown",
                size=candidate.size or "unknown",
                basis=candidate.size_basis,
            )
        )
        lines.append(
            "   Seeds: {seeders} | Downloads: {downloads} | Audio: {audio} | Chinese/mixed subs: {zh}".format(
                seeders=candidate.seeders,
                downloads=candidate.downloads,
                audio=candidate.audio_signal,
                zh=candidate.subtitle_signal,
            )
        )
        if candidate.matched_queries:
            lines.append(f"   Query: {', '.join(candidate.matched_queries)}")
        if candidate.published or candidate.category:
            lines.append(f"   Published: {candidate.published or 'unknown'} | Category: {candidate.category or 'unknown'}")
        lines.append(f"   Why: {'; '.join(candidate.reasons)}")
        if include_magnets and candidate.magnet:
            lines.append(f"   Magnet: {candidate.magnet}")
        if candidate.url and not magnet_only:
            lines.append(f"   Nyaa: {candidate.url}")
        lines.append("")
    return "\n".join(lines).rstrip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search and rank lawful Nyaa anime releases.")
    parser.add_argument("query", help="Primary anime/work title or search query. Prefer famous English/romaji titles.")
    parser.add_argument("--alias", action="append", default=[], help="Additional famous title/search alias; repeatable.")
    parser.add_argument("--category", default="1_0", help="Nyaa category, default anime all: 1_0.")
    parser.add_argument("--filter", default="0", help="Nyaa filter: 0 all, 1 no remakes, 2 trusted only.")
    parser.add_argument("--limit", type=int, default=10, help="Number of ranked results to print.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds per query.")
    parser.add_argument("--want-zh", action="store_true", help="Use Chinese or mixed subtitle signals only as a near-tie breaker.")
    parser.add_argument(
        "--require-zh",
        action="store_true",
        help="Require Simplified or Traditional Chinese subtitles confirmed from the Nyaa detail page.",
    )
    parser.add_argument("--airing-priority", action="store_true", help="For current-season/new anime, raise same-quality Chinese subtitle/detail priority without crossing quality tiers.")
    parser.add_argument("--resolution", help="Desired resolution, e.g. 1080p or 2160p.")
    parser.add_argument("--tier", type=normalize_tier, default="browse", help="Need tier: browse, watch, or premium. Default: browse.")
    parser.add_argument("--season", help="Target season such as S02; filters obvious other-season results.")
    parser.add_argument("--episode", type=int, help="Target episode; filters previous/other episodes from noisy RSS results.")
    parser.add_argument("--duration-min", type=float, default=22.0, help="Runtime metadata only; quality tiers use actual file size. Default: 22.")
    parser.add_argument("--episodes", type=int, help="Episode count for batch scoring; divides total size by this count.")
    parser.add_argument("--min-gib-per-episode", type=float, help="Hard lower size floor in GiB per 22-minute episode.")
    parser.add_argument("--max-gib-per-episode", type=float, help="Optional hard upper size bound in GiB per episode.")
    parser.add_argument("--prefer-group", action="append", default=[], help="Preferred release group; repeatable.")
    parser.add_argument("--avoid-group", action="append", default=[], help="Avoided release group; repeatable.")
    parser.add_argument("--inspect-details", action="store_true", help="Fetch Nyaa detail pages and detect subtitle language signals in descriptions.")
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=5,
        help="Maximum candidates for ordinary detail inspection; strict Chinese checks use adaptive batches.",
    )
    parser.add_argument(
        "--detail-budget-seconds",
        type=float,
        default=30.0,
        help="Wall-clock budget for a strict Chinese-subtitle detail check.",
    )
    parser.add_argument(
        "--intent",
        choices=["specific_episode", "next_tracked", "latest_regular", "season_browse", "season_batch"],
        help="Structured selection intent. Defaults to specific_episode when --episode is set.",
    )
    parser.add_argument("--include-specials", action="store_true", help="Select special/OVA candidates after explicit confirmation.")
    parser.add_argument("--whole-season", action="store_true", help="Select one verified complete-season package.")
    parser.add_argument("--report", action="store_true", help="Emit structured selection and filter diagnostics.")
    parser.add_argument("--include-magnets", action="store_true", help="Print magnet links.")
    parser.add_argument("--magnet-only", action="store_true", help="When printing magnets, omit Nyaa page links.")
    parser.add_argument("--legal-ok", action="store_true", help="Confirm the caller has lawful access to these releases.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.require_zh:
        args.want_zh = True
        args.inspect_details = True
        args.detail_limit = max(args.detail_limit, 5)
    if args.include_magnets and not args.legal_ok:
        print("Refusing to print magnet links without --legal-ok. Re-run without --include-magnets for metadata only.", file=sys.stderr)
        return 2
    if args.magnet_only and not args.include_magnets:
        print("--magnet-only requires --include-magnets and --legal-ok.", file=sys.stderr)
        return 2
    explicit_min = args.min_gib_per_episode
    explicit_max = args.max_gib_per_episode
    if explicit_min is not None and explicit_max is not None and explicit_max < explicit_min:
        print("--max-gib-per-episode must be greater than or equal to --min-gib-per-episode.", file=sys.stderr)
        return 2
    args.size_policy_source = (
        "explicit" if explicit_min is not None or explicit_max is not None else "tier"
    )
    if args.size_policy_source == "tier":
        args.min_gib_per_episode = DEFAULT_TIER_MIN_GIB[args.tier]
    from release_search_core import SearchIntent, search_release_report

    intent = args.intent or (
        SearchIntent.SPECIFIC_EPISODE.value
        if args.episode is not None
        else (
            SearchIntent.SEASON_BATCH.value
            if args.whole_season
            else SearchIntent.SEASON_BROWSE.value
        )
    )
    report = search_release_report(
        args,
        intent=intent,
        requested_episode=args.episode,
        include_specials=args.include_specials,
    )
    if report.failures:
        print("Search warnings: " + " | ".join(report.failures), file=sys.stderr)

    if args.report:
        print(json.dumps(report.as_dict(explain=True), ensure_ascii=False, indent=2))
    else:
        candidates = [item.candidate for item in report.selected]
        if args.magnet_only:
            for candidate in candidates:
                candidate.url = None
        if args.json:
            print(json.dumps([asdict(candidate) for candidate in candidates], ensure_ascii=False, indent=2))
        else:
            print(render_markdown(candidates, include_magnets=args.include_magnets, magnet_only=args.magnet_only))

    return {
        "network_error": 1,
        "release_unqualified": 3,
        "subtitle_unqualified": 3,
        "subtitle_check_incomplete": 3,
        "season_check_incomplete": 3,
        "no_complete_season_release": 4,
        "no_nyaa_release_for_target": 4,
    }.get(report.status, 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
