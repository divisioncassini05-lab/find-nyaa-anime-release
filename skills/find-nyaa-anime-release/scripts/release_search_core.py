"""Reusable RSS collection, release classification, and selection core."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import search_nyaa_releases as nyaa
from release_identity import EpisodeKind, ReleaseIdentity, normalize_season_number, parse_release_identity, season_relation


RAW_CACHE_VERSION = 2
RAW_CACHE_SECONDS = 5 * 60
MAX_RAW_CACHE_ENTRIES = 120
TIER_SIZE_BOUNDS: dict[str, tuple[float, float | None]] = {
    "browse": (1.0, 2.0),
    "watch": (2.0, 4.0),
    "premium": (6.0, None),
}


class SearchIntent(str, Enum):
    SPECIFIC_EPISODE = "specific_episode"
    NEXT_TRACKED = "next_tracked"
    LATEST_REGULAR = "latest_regular"
    SEASON_BROWSE = "season_browse"
    SEASON_BATCH = "season_batch"


@dataclass(frozen=True)
class SearchContext:
    canonical_title: str | None = None
    aliases: tuple[str, ...] = ()
    search_titles: tuple[str, ...] = ()
    related_titles: tuple[str, ...] = ()
    mainline_scope: str = "unknown"
    resolved_season: int | None = None
    expected_episodes: int | None = None
    flexible_title_match: bool = False


@dataclass(frozen=True)
class SizePolicy:
    source: str
    hard_min_gib: float | None
    hard_max_gib: float | None
    preferred_min_gib: float
    preferred_max_gib: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeasonCoverage:
    scope: str
    target_season: int | None
    expected_episodes: int | None
    covered_episodes: tuple[int, ...] = ()
    covered_seasons: tuple[int, ...] = ()
    confidence: str = "unknown"
    main_file_count: int = 0
    min_gib_per_episode: float | None = None
    max_gib_per_episode: float | None = None
    source_exempt: bool = False
    complete: bool = False
    quality_fit: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["covered_episodes"] = list(self.covered_episodes)
        payload["covered_seasons"] = list(self.covered_seasons)
        return payload


@dataclass(frozen=True)
class WorkMatchEvidence:
    outcome: str
    positive_source: str | None = None
    positive_title: str | None = None
    positive_length: int = 0
    related_title: str | None = None
    related_length: int = 0
    decision: str = "no_evidence"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassifiedCandidate:
    candidate: nyaa.Candidate
    identity: ReleaseIdentity
    season_match: str
    effective_season: int | None = None
    season_source: str = "unknown"
    work_match: str = "unknown"
    coverage: SeasonCoverage | None = None
    work_match_evidence: WorkMatchEvidence | None = None

    def as_dict(
        self,
        include_reasons: bool = False,
        include_work_evidence: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "title": self.candidate.title,
            "size": self.candidate.size,
            "seeders": self.candidate.seeders,
            "resolution": self.candidate.resolution,
            "url": self.candidate.url,
            "magnet": self.candidate.magnet,
            "published": self.candidate.published,
            "score": self.candidate.score,
            "identity": self.identity.as_dict(),
            "season_match": self.season_match,
            "effective_season": self.effective_season,
            "season_source": self.season_source,
            "work_match": self.work_match,
            "coverage": self.coverage.as_dict() if self.coverage else None,
        }
        if include_reasons:
            payload["reasons"] = self.candidate.reasons
        if include_work_evidence and self.work_match_evidence is not None:
            payload["work_match_evidence"] = self.work_match_evidence.as_dict()
        return payload


@dataclass
class ReleaseSearchReport:
    intent: SearchIntent
    requested_season: int | None
    requested_episode: int | None
    status: str
    selected: list[ClassifiedCandidate]
    choices: list[ClassifiedCandidate]
    diagnostics: dict[str, Any]
    failures: list[str]
    cache: str

    def as_dict(self, explain: bool = False) -> dict[str, Any]:
        return {
            "status": self.status,
            "intent": self.intent.value,
            "requested_season": self.requested_season,
            "requested_episode": self.requested_episode,
            "selected": [item.as_dict(explain, explain) for item in self.selected],
            "choices": [item.as_dict(True, explain) for item in self.choices[:2]],
            "diagnostic": self.diagnostics,
            "failures": self.failures[:2],
            "cache": self.cache,
        }


@dataclass
class DetailInspectionResult:
    attempted_count: int = 0
    checked_count: int = 0
    rejected_count: int = 0
    verified_count: int = 0
    failed_count: int = 0
    missing_url_count: int = 0
    unchecked_count: int = 0
    budget_exhausted: bool = False
    elapsed_ms: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (
            self.budget_exhausted
            or self.failed_count
            or self.missing_url_count
            or self.unchecked_count
        )

    def as_diagnostics(self) -> dict[str, Any]:
        return {
            "detail_attempted_count": self.attempted_count,
            "detail_checked_count": self.checked_count,
            "detail_failed_count": self.failed_count,
            "detail_missing_url_count": self.missing_url_count,
            "detail_unchecked_count": self.unchecked_count,
            "detail_budget_exhausted": self.budget_exhausted,
            "detail_elapsed_ms": self.elapsed_ms,
            "subtitle_rejected_count": self.rejected_count,
            "subtitle_verified_count": self.verified_count,
        }


def _load_raw_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": RAW_CACHE_VERSION, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": RAW_CACHE_VERSION, "entries": {}}
    if data.get("version") != RAW_CACHE_VERSION or not isinstance(data.get("entries"), dict):
        return {"version": RAW_CACHE_VERSION, "entries": {}}
    return data


def _save_raw_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp.replace(path)
    except OSError:
        return


def _raw_cache_key(args: argparse.Namespace) -> str:
    payload = {
        "query": args.query,
        "aliases": args.alias,
        "category": args.category,
        "filter": args.filter,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_cached_rss_items(path: Path, key: str) -> list[dict[str, str]] | None:
    cache = _load_raw_cache(path)
    now = time.time()

    def expired(entry: Any) -> bool:
        if not isinstance(entry, dict):
            return True
        try:
            return float(entry.get("expires_at", 0)) <= now
        except (TypeError, ValueError):
            return True

    entries = cache["entries"]
    expired_keys = [
        item_key
        for item_key, entry in entries.items()
        if expired(entry)
    ]
    for item_key in expired_keys:
        entries.pop(item_key, None)
    if expired_keys:
        _save_raw_cache(path, cache)
    entry = entries.get(key)
    if not isinstance(entry, dict) or not isinstance(entry.get("items"), list):
        return None
    items = [
        item
        for item in entry["items"]
        if isinstance(item, dict)
        and isinstance(item.get("query"), str)
        and isinstance(item.get("xml"), str)
    ]
    return items


def _write_cached_rss_items(path: Path, key: str, items: list[dict[str, str]]) -> None:
    cache = _load_raw_cache(path)
    entries = cache["entries"]
    now = time.time()
    entries[key] = {
        "cached_at": now,
        "expires_at": now + RAW_CACHE_SECONDS,
        "items": items,
    }
    if len(entries) > MAX_RAW_CACHE_ENTRIES:
        oldest = sorted(entries, key=lambda item_key: float(entries[item_key].get("cached_at", 0)))
        for item_key in oldest[: len(entries) - MAX_RAW_CACHE_ENTRIES]:
            entries.pop(item_key, None)
    _save_raw_cache(path, cache)


def _merge_candidates(*candidate_lists: list[nyaa.Candidate]) -> list[nyaa.Candidate]:
    merged: dict[str, nyaa.Candidate] = {}
    for candidates in candidate_lists:
        for candidate in candidates:
            key = candidate.url or candidate.title
            merged[key] = nyaa.merge_candidate(merged[key], candidate) if key in merged else candidate
    return list(merged.values())


def _score_rss_items(items: list[dict[str, str]], args: argparse.Namespace) -> list[nyaa.Candidate]:
    by_key: dict[str, nyaa.Candidate] = {}
    for raw_item in items:
        try:
            item = nyaa.ET.fromstring(raw_item["xml"])
        except nyaa.ET.ParseError:
            continue
        candidate = nyaa.score_item(
            item,
            query=raw_item["query"],
            want_zh=args.want_zh,
            airing_priority=args.airing_priority,
            desired_resolution=args.resolution,
            tier=args.tier,
            duration_min=args.duration_min,
            episodes=args.episodes,
            prefer_groups=args.prefer_group,
            avoid_groups=args.avoid_group,
            include_magnets=args.include_magnets,
        )
        candidate_key = candidate.url or candidate.title
        by_key[candidate_key] = (
            nyaa.merge_candidate(by_key[candidate_key], candidate)
            if candidate_key in by_key
            else candidate
        )
    return list(by_key.values())


def _targeted_fallback_args(
    args: argparse.Namespace, requested_season: int | None, requested_episode: int
) -> argparse.Namespace:
    episode_token = (
        f"S{requested_season:02d}E{requested_episode:02d}"
        if requested_season is not None
        else f"E{requested_episode:02d}"
    )
    payload = vars(args).copy()
    payload["query"] = f"{args.query} {episode_token}"
    payload["alias"] = []
    return argparse.Namespace(**payload)


def collect_raw_candidates(
    args: argparse.Namespace,
    cache_path: Path | None = None,
    refresh_cache: bool = False,
) -> tuple[list[nyaa.Candidate], list[str], str]:
    key = _raw_cache_key(args)
    if cache_path is not None and not refresh_cache:
        cached = _read_cached_rss_items(cache_path, key)
        if cached is not None:
            return _score_rss_items(cached, args), [], "hit"

    rss_items: list[dict[str, str]] = []
    failures: list[str] = []
    for query in dict.fromkeys([args.query, *args.alias]):
        try:
            rss = nyaa.fetch_rss(query, args.category, args.filter, args.timeout)
            root = nyaa.ET.fromstring(rss)
        except Exception as exc:  # noqa: BLE001 - reports keep network failures separate from empty results.
            failures.append(f"{query}: {exc}")
            continue
        for item in root.findall("./channel/item"):
            rss_items.append(
                {"query": query, "xml": nyaa.ET.tostring(item, encoding="unicode")}
            )
    candidates = _score_rss_items(rss_items, args)
    if cache_path is not None and rss_items:
        _write_cached_rss_items(cache_path, key, rss_items)
    return candidates, failures, "refresh" if refresh_cache else "miss"


def _compact_title(value: str, flexible: bool = False) -> str:
    folded = value.casefold()
    if flexible:
        folded = "".join(
            character
            for character in unicodedata.normalize("NFKD", folded)
            if not unicodedata.combining(character)
        )
        # Treat macron and doubled-vowel romanization as equivalent (Jādūgar / Jaadugar).
        folded = re.sub(r"([aeiou])\1+", r"\1", folded)
    return re.sub(r"[\W_]+", "", folded)


def _contains_title(release_title: str, work_title: str, flexible: bool = False) -> bool:
    compact_work = _compact_title(work_title, flexible)
    return len(compact_work) >= 4 and compact_work in _compact_title(release_title, flexible)


def _work_match_evidence(
    candidate: nyaa.Candidate,
    context: SearchContext | None,
) -> WorkMatchEvidence:
    if context is None:
        return WorkMatchEvidence(outcome="unknown", decision="no_context")
    flexible = context.flexible_title_match

    positive_matches: list[tuple[str, str, int]] = []
    if context.canonical_title and _contains_title(
        candidate.title, context.canonical_title, flexible
    ):
        positive_matches.append(
            (
                "canonical",
                context.canonical_title,
                len(_compact_title(context.canonical_title, flexible)),
            )
        )
    for source, titles in (
        ("alias", context.aliases),
        ("search_title", context.search_titles),
    ):
        for title in titles:
            if _contains_title(candidate.title, title, flexible):
                positive_matches.append(
                    (source, title, len(_compact_title(title, flexible)))
                )

    related_matches = [
        (title, len(_compact_title(title, flexible)))
        for title in context.related_titles
        if _contains_title(candidate.title, title, flexible)
    ]
    source_priority = {"canonical": 3, "alias": 2, "search_title": 1}
    best_positive = max(
        positive_matches,
        key=lambda item: (item[2], source_priority[item[0]]),
        default=None,
    )
    best_related = max(related_matches, key=lambda item: item[1], default=None)

    positive_outcome = next(
        (
            source
            for source in ("canonical", "alias", "search_title")
            if any(match_source == source for match_source, _, _ in positive_matches)
        ),
        "unknown",
    )
    if best_positive is None and best_related is None:
        return WorkMatchEvidence(outcome="unknown", decision="no_title_evidence")
    if best_positive is None:
        return WorkMatchEvidence(
            outcome="related_work",
            related_title=best_related[0],
            related_length=best_related[1],
            decision="related_only",
        )
    if best_related is None:
        return WorkMatchEvidence(
            outcome=positive_outcome,
            positive_source=best_positive[0],
            positive_title=best_positive[1],
            positive_length=best_positive[2],
            decision="positive_only",
        )

    positive_wins = best_positive[2] >= best_related[1]
    return WorkMatchEvidence(
        outcome=positive_outcome if positive_wins else "related_work",
        positive_source=best_positive[0],
        positive_title=best_positive[1],
        positive_length=best_positive[2],
        related_title=best_related[0],
        related_length=best_related[1],
        decision=(
            "positive_tie"
            if best_positive[2] == best_related[1]
            else "positive_more_specific"
            if positive_wins
            else "related_more_specific"
        ),
    )


def _work_match(candidate: nyaa.Candidate, context: SearchContext | None) -> str:
    return _work_match_evidence(candidate, context).outcome


def _classify(
    candidates: list[nyaa.Candidate],
    requested_season: int | None,
    context: SearchContext | None = None,
) -> list[ClassifiedCandidate]:
    classified: list[ClassifiedCandidate] = []
    for candidate in candidates:
        identity = parse_release_identity(candidate.title)
        work_match_evidence = _work_match_evidence(candidate, context)
        work_match = work_match_evidence.outcome
        effective_season = identity.season
        season_source = "title" if identity.season is not None else "unknown"
        season_match = season_relation(identity, requested_season)
        if work_match == "related_work":
            season_match = "other_work"
        elif requested_season is not None and requested_season in identity.covered_seasons:
            effective_season = requested_season
            season_source = "title_coverage"
            season_match = "match"
        elif (
            identity.season is None
            and identity.kind is EpisodeKind.BATCH
            and context is not None
            and context.resolved_season is not None
            and work_match == "canonical"
        ):
            effective_season = context.resolved_season
            season_source = "canonical_season_title"
            season_match = (
                "not_requested"
                if requested_season is None
                else ("match" if effective_season == requested_season else "other")
            )
        elif (
            identity.season is None
            and context is not None
            and context.mainline_scope == "single"
            and work_match in {"canonical", "alias", "search_title"}
        ):
            effective_season = context.resolved_season or requested_season or 1
            season_source = "single_mainline"
            season_match = (
                "not_requested"
                if requested_season is None
                else ("match" if effective_season == requested_season else "other")
            )
        classified.append(
            ClassifiedCandidate(
                candidate=candidate,
                identity=identity,
                season_match=season_match,
                effective_season=effective_season,
                season_source=season_source,
                work_match=work_match,
                work_match_evidence=work_match_evidence,
            )
        )
    return classified


def _in_requested_season(item: ClassifiedCandidate) -> bool:
    return item.work_match != "related_work" and item.season_match in {"match", "not_requested"}


def _is_exact_regular_episode(
    item: ClassifiedCandidate, requested_episode: int | None
) -> bool:
    if item.identity.kind is not EpisodeKind.REGULAR or item.identity.episode is None:
        return False
    if not _in_requested_season(item):
        return False
    return requested_episode is None or item.identity.episode == requested_episode


def size_policy_from_args(args: argparse.Namespace) -> SizePolicy:
    preferred_min, preferred_max = TIER_SIZE_BOUNDS[args.tier]
    source = getattr(args, "size_policy_source", "tier")
    if source == "explicit":
        return SizePolicy(
            source="explicit",
            hard_min_gib=args.min_gib_per_episode,
            hard_max_gib=getattr(args, "max_gib_per_episode", None),
            preferred_min_gib=preferred_min,
            preferred_max_gib=preferred_max,
        )
    return SizePolicy(
        source="tier",
        hard_min_gib=preferred_min,
        hard_max_gib=preferred_max,
        preferred_min_gib=preferred_min,
        preferred_max_gib=preferred_max,
    )


def _quality_filter(
    candidates: list[ClassifiedCandidate], args: argparse.Namespace, policy: SizePolicy
) -> tuple[list[ClassifiedCandidate], dict[str, int]]:
    kept: list[ClassifiedCandidate] = []
    counts = {"below_min_count": 0, "above_max_count": 0, "size_unknown_count": 0}
    for item in candidates:
        comparable = nyaa.comparable_gib_per_episode(item.candidate, args.episodes)
        if comparable is None:
            counts["size_unknown_count"] += 1
            item.candidate.reasons.append("actual single-episode size is unavailable")
            continue
        if policy.hard_min_gib is not None and comparable < policy.hard_min_gib:
            counts["below_min_count"] += 1
            item.candidate.reasons.append(
                f"below hard size minimum: {comparable:.2f} < {policy.hard_min_gib:.2f} GiB/episode"
            )
            continue
        if policy.hard_max_gib is not None and comparable > policy.hard_max_gib:
            counts["above_max_count"] += 1
            item.candidate.reasons.append(
                f"above hard size maximum: {comparable:.2f} > {policy.hard_max_gib:.2f} GiB/episode"
            )
            continue
        item.candidate.reasons.append(
            f"meets {policy.source} size policy at {comparable:.2f} GiB/episode"
        )
        kept.append(item)
    return kept, counts


_VIDEO_EXTENSIONS = {".avi", ".m2ts", ".m4v", ".mkv", ".mp4", ".ts"}
_EXTRA_DIRECTORY_PATTERN = re.compile(
    r"(?:^|[/\\])(?:bonus|extras?|ncop|nced|oad|ova|specials?|sp)(?:[/\\]|$)",
    re.I,
)
_EXTRA_BASENAME_PATTERN = re.compile(
    r"(?:^|[\s._\-\[\]()])(?:"
    r"cm\d*|creditless|menu|nc(?:op|ed)\d*|oad\d*|ova\d*|preview|pv\d*|"
    r"recap|sample|sp\d*|trailer"
    r")(?:$|[\s._\-\[\]()])",
    re.I,
)
_SOURCE_EXEMPT_PATTERN = re.compile(r"(?<![a-z0-9])(?:bdmv|remux)(?![a-z0-9])", re.I)


def _season_batch_scope(item: ClassifiedCandidate, requested_season: int | None) -> str:
    covered = item.identity.covered_seasons
    if requested_season is not None and covered:
        if requested_season not in covered:
            return "other"
        return "multi" if len(covered) > 1 else "exact"
    if requested_season is None and len(covered) > 1:
        return "multi"
    if item.effective_season is not None and (
        requested_season is None or item.effective_season == requested_season
    ):
        return "exact"
    return "unknown"


def _is_source_exempt(item: ClassifiedCandidate, args: argparse.Namespace) -> bool:
    return args.tier == "premium" and bool(_SOURCE_EXEMPT_PATTERN.search(item.candidate.title))


def _is_main_video(entry: nyaa.NyaaFileEntry) -> bool:
    normalized = entry.name.replace("\\", "/")
    suffix = Path(normalized.rsplit("/", 1)[-1]).suffix.casefold()
    basename = normalized.rsplit("/", 1)[-1]
    return (
        suffix in _VIDEO_EXTENSIONS
        and not _EXTRA_DIRECTORY_PATTERN.search(normalized)
        and not _EXTRA_BASENAME_PATTERN.search(basename)
    )


def _integer_episode(identity: ReleaseIdentity) -> int | None:
    episode = identity.episode
    if (
        identity.kind is not EpisodeKind.REGULAR
        or episode is None
        or episode != episode.to_integral_value()
    ):
        return None
    value = int(episode)
    return value if value > 0 else None


def _entry_identity(
    entry: nyaa.NyaaFileEntry,
    requested_season: int | None,
    scope: str,
) -> tuple[int | None, int | None]:
    normalized = entry.name.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    base_identity = parse_release_identity(basename)
    path_identity = parse_release_identity(normalized)
    if base_identity.kind is EpisodeKind.SPECIAL:
        return None, None
    episode = _integer_episode(base_identity) or _integer_episode(path_identity)
    if episode is None:
        return None, None
    season = base_identity.season or path_identity.season
    if season is None and len(path_identity.covered_seasons) == 1:
        season = path_identity.covered_seasons[0]
    if season is None and scope == "exact":
        season = requested_season
    return season, episode


def _title_declares_complete(identity: ReleaseIdentity, expected_episodes: int) -> bool:
    if identity.episode_start is not None and identity.episode_end is not None:
        return identity.episode_start <= Decimal(1) and identity.episode_end >= Decimal(expected_episodes)
    return identity.kind is EpisodeKind.BATCH and identity.coverage_confidence.value == "weak"


def _coverage_from_file_entries(
    item: ClassifiedCandidate,
    entries: list[nyaa.NyaaFileEntry],
    args: argparse.Namespace,
    policy: SizePolicy,
    requested_season: int | None,
    expected_episodes: int | None,
) -> SeasonCoverage:
    scope = _season_batch_scope(item, requested_season)
    source_exempt = _is_source_exempt(item, args)
    covered_seasons = item.identity.covered_seasons
    if expected_episodes is None or expected_episodes <= 0:
        return SeasonCoverage(
            scope=scope,
            target_season=requested_season,
            expected_episodes=expected_episodes,
            covered_seasons=covered_seasons,
            source_exempt=source_exempt,
            reason="expected_episode_count_unavailable",
        )

    videos = [entry for entry in entries if _is_main_video(entry)]
    if not videos:
        return SeasonCoverage(
            scope=scope,
            target_season=requested_season,
            expected_episodes=expected_episodes,
            covered_seasons=covered_seasons,
            source_exempt=source_exempt,
            reason="detail_file_list_unavailable",
        )

    mapped: dict[tuple[int | None, int], nyaa.NyaaFileEntry] = {}
    unknown_large = 0
    ambiguity_floor = max(0.5, policy.hard_min_gib or 0.0)
    for entry in videos:
        season, episode = _entry_identity(entry, requested_season, scope)
        if episode is None or (scope == "multi" and season is None):
            if entry.size_bytes is None or nyaa.bytes_to_gib(entry.size_bytes) >= ambiguity_floor:
                unknown_large += 1
            continue
        key = (season, episode)
        existing = mapped.get(key)
        if existing is None or (entry.size_bytes or 0) > (existing.size_bytes or 0):
            mapped[key] = entry

    mapped_seasons = tuple(sorted({season for season, _ in mapped if season is not None}))
    if scope == "unknown" and requested_season is not None:
        if requested_season in mapped_seasons:
            scope = "multi" if len(mapped_seasons) > 1 else "exact"
        elif len(mapped_seasons) == 1:
            scope = "other"
    if scope == "other":
        return SeasonCoverage(
            scope=scope,
            target_season=requested_season,
            expected_episodes=expected_episodes,
            covered_seasons=mapped_seasons or covered_seasons,
            main_file_count=len(mapped),
            source_exempt=source_exempt,
            reason="target_season_not_covered",
        )

    target_entries = {
        episode: entry
        for (season, episode), entry in mapped.items()
        if requested_season is None or season == requested_season
    }
    expected_set = set(range(1, expected_episodes + 1))
    covered_set = set(target_entries) & expected_set

    is_bdmv = bool(re.search(r"(?<![a-z0-9])bdmv(?![a-z0-9])", item.candidate.title, re.I))
    if (
        is_bdmv
        and scope == "exact"
        and _title_declares_complete(item.identity, expected_episodes)
        and len(videos) >= expected_episodes
    ):
        covered_set = expected_set

    sizes = [entry.size_bytes for entry in mapped.values() if entry.size_bytes is not None]
    if is_bdmv and not sizes:
        sizes = [entry.size_bytes for entry in videos if entry.size_bytes is not None]
    size_gib = [nyaa.bytes_to_gib(value) for value in sizes]
    complete = covered_set == expected_set
    if not complete:
        missing = sorted(expected_set - covered_set)
        return SeasonCoverage(
            scope=scope,
            target_season=requested_season,
            expected_episodes=expected_episodes,
            covered_episodes=tuple(sorted(covered_set)),
            covered_seasons=mapped_seasons or covered_seasons,
            confidence="verified",
            main_file_count=len(mapped) or len(videos),
            min_gib_per_episode=round(min(size_gib), 3) if size_gib else None,
            max_gib_per_episode=round(max(size_gib), 3) if size_gib else None,
            source_exempt=source_exempt,
            reason=f"missing_target_episodes:{','.join(map(str, missing[:8]))}",
        )
    if scope == "multi" and unknown_large:
        return SeasonCoverage(
            scope=scope,
            target_season=requested_season,
            expected_episodes=expected_episodes,
            covered_episodes=tuple(sorted(covered_set)),
            covered_seasons=mapped_seasons or covered_seasons,
            confidence="unknown",
            main_file_count=len(mapped),
            min_gib_per_episode=round(min(size_gib), 3) if size_gib else None,
            max_gib_per_episode=round(max(size_gib), 3) if size_gib else None,
            source_exempt=source_exempt,
            reason="unclassified_large_video_files",
        )

    all_sizes_known = bool(mapped) and all(entry.size_bytes is not None for entry in mapped.values())
    quality_fit = source_exempt
    if not source_exempt and all_sizes_known:
        quality_fit = all(
            (policy.hard_min_gib is None or value >= policy.hard_min_gib)
            and (policy.hard_max_gib is None or value <= policy.hard_max_gib)
            for value in size_gib
        )
    reason = "verified_complete_and_qualified" if quality_fit else "per_episode_size_out_of_range"
    if not source_exempt and not all_sizes_known:
        reason = "per_episode_size_unavailable"
    return SeasonCoverage(
        scope=scope,
        target_season=requested_season,
        expected_episodes=expected_episodes,
        covered_episodes=tuple(sorted(covered_set)),
        covered_seasons=mapped_seasons or covered_seasons,
        confidence="verified",
        main_file_count=len(mapped) or len(videos),
        min_gib_per_episode=round(min(size_gib), 3) if size_gib else None,
        max_gib_per_episode=round(max(size_gib), 3) if size_gib else None,
        source_exempt=source_exempt,
        complete=True,
        quality_fit=quality_fit,
        reason=reason,
    )


def _season_batch_report(
    classified: list[ClassifiedCandidate],
    args: argparse.Namespace,
    policy: SizePolicy,
    requested_season: int | None,
    context: SearchContext | None,
    diagnostics: dict[str, Any],
    failures: list[str],
    cache_state: str,
) -> ReleaseSearchReport:
    expected_episodes = (context.expected_episodes if context else None) or args.episodes
    unconfirmed_work_batches = [
        item
        for item in classified
        if item.identity.kind is EpisodeKind.BATCH
        and item.work_match == "unknown"
        and _season_batch_scope(item, requested_season) != "other"
    ]
    batches = [
        item
        for item in classified
        if item.identity.kind is EpisodeKind.BATCH
        and item.work_match != "related_work"
        and (context is None or item.work_match != "unknown")
        and _season_batch_scope(item, requested_season) != "other"
    ]
    diagnostics.update(
        {
            "batch_candidate_count": len(batches),
            "unconfirmed_work_batch_count": len(unconfirmed_work_batches),
            "expected_episode_count": expected_episodes,
            "aggregate_floor_rejected_count": 0,
            "coverage_rejected_count": 0,
            "season_detail_checked_count": 0,
            "season_detail_failed_count": 0,
            "season_detail_unchecked_count": 0,
            "season_quality_rejected_count": 0,
        }
    )
    if not batches:
        return ReleaseSearchReport(
            intent=SearchIntent.SEASON_BATCH,
            requested_season=requested_season,
            requested_episode=None,
            status=(
                "season_check_incomplete"
                if context is not None and unconfirmed_work_batches
                else "no_complete_season_release"
            ),
            selected=[],
            choices=[],
            diagnostics=diagnostics,
            failures=failures,
            cache=cache_state,
        )

    inspectable: list[ClassifiedCandidate] = []
    for item in batches:
        source_exempt = _is_source_exempt(item, args)
        if (
            not source_exempt
            and expected_episodes
            and policy.hard_min_gib is not None
            and item.candidate.size_bytes is not None
            and nyaa.bytes_to_gib(item.candidate.size_bytes)
            < expected_episodes * policy.hard_min_gib
        ):
            diagnostics["aggregate_floor_rejected_count"] += 1
            item.coverage = SeasonCoverage(
                scope=_season_batch_scope(item, requested_season),
                target_season=requested_season,
                expected_episodes=expected_episodes,
                covered_seasons=item.identity.covered_seasons,
                source_exempt=False,
                reason="aggregate_size_below_unavoidable_floor",
            )
            continue
        inspectable.append(item)

    detail_limit = max(1, int(getattr(args, "season_detail_limit", 8)))
    remaining_budget = detail_limit
    incomplete = False
    subtitle_qualified_count = 0
    quality_complete_count = 0
    qualified_by_scope: dict[str, list[ClassifiedCandidate]] = {"exact": [], "multi": []}

    for scope in ("exact", "multi", "unknown"):
        group = [item for item in inspectable if _season_batch_scope(item, requested_season) == scope]
        group = sorted(group, key=lambda value: value.candidate.score, reverse=True)
        selected_group = group[:remaining_budget]
        if len(group) > len(selected_group):
            diagnostics["season_detail_unchecked_count"] += len(group) - len(selected_group)
            incomplete = True
        remaining_budget -= len(selected_group)
        if not selected_group:
            continue

        pages: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(selected_group))) as executor:
            future_map = {
                executor.submit(nyaa.fetch_nyaa_detail_page, item.candidate.url, args.timeout): index
                for index, item in enumerate(selected_group)
                if item.candidate.url
            }
            missing_urls = len(selected_group) - len(future_map)
            if missing_urls:
                diagnostics["season_detail_failed_count"] += missing_urls
                incomplete = True
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    pages[index] = future.result()
                except Exception as exc:  # noqa: BLE001 - incomplete inspection is not no release.
                    diagnostics["season_detail_failed_count"] += 1
                    incomplete = True
                    failures.append(f"Nyaa season detail inspection failed: {exc}")

        for index, item in enumerate(selected_group):
            page_html = pages.get(index)
            if page_html is None:
                continue
            diagnostics["season_detail_checked_count"] += 1
            entries = nyaa.extract_nyaa_file_entries(page_html)
            coverage = _coverage_from_file_entries(
                item, entries, args, policy, requested_season, expected_episodes
            )
            item.coverage = coverage
            if coverage.reason in {
                "detail_file_list_unavailable",
                "expected_episode_count_unavailable",
                "per_episode_size_unavailable",
                "unclassified_large_video_files",
            }:
                incomplete = True
                continue
            if not coverage.complete:
                diagnostics["coverage_rejected_count"] += 1
                continue
            if not coverage.quality_fit:
                diagnostics["season_quality_rejected_count"] += 1
                continue
            quality_complete_count += 1
            detail_text = nyaa.extract_nyaa_description(page_html)
            nyaa.apply_detail_subtitle_signal(
                item.candidate, detail_text, args.want_zh, args.airing_priority
            )
            if getattr(args, "require_zh", False) and not item.candidate.detail_chinese_confirmed:
                continue
            if item.candidate.detail_chinese_confirmed:
                subtitle_qualified_count += 1
            effective_scope = coverage.scope if coverage.scope in {"exact", "multi"} else scope
            if effective_scope in qualified_by_scope:
                qualified_by_scope[effective_scope].append(item)

        exact = _rank(qualified_by_scope["exact"])
        if exact:
            return ReleaseSearchReport(
                intent=SearchIntent.SEASON_BATCH,
                requested_season=requested_season,
                requested_episode=None,
                status="found",
                selected=exact[: max(1, args.limit)],
                choices=[],
                diagnostics=diagnostics,
                failures=failures,
                cache=cache_state,
            )
        if scope in {"multi", "unknown"}:
            multi = _rank(qualified_by_scope["multi"])
            if multi:
                return ReleaseSearchReport(
                    intent=SearchIntent.SEASON_BATCH,
                    requested_season=requested_season,
                    requested_episode=None,
                    status="found",
                    selected=multi[: max(1, args.limit)],
                    choices=[],
                    diagnostics=diagnostics,
                    failures=failures,
                    cache=cache_state,
                )
        if remaining_budget <= 0:
            break

    if incomplete:
        status = "season_check_incomplete"
    elif getattr(args, "require_zh", False) and quality_complete_count and not subtitle_qualified_count:
        status = "subtitle_unqualified"
    elif diagnostics["aggregate_floor_rejected_count"] or diagnostics["season_quality_rejected_count"]:
        status = "release_unqualified"
    else:
        status = "no_complete_season_release"
    return ReleaseSearchReport(
        intent=SearchIntent.SEASON_BATCH,
        requested_season=requested_season,
        requested_episode=None,
        status=status,
        selected=[],
        choices=[],
        diagnostics=diagnostics,
        failures=failures,
        cache=cache_state,
    )


def _rank(items: list[ClassifiedCandidate]) -> list[ClassifiedCandidate]:
    ranked = sorted(items, key=lambda item: item.candidate.score, reverse=True)
    for index, item in enumerate(ranked, start=1):
        item.candidate.rank = index
    return ranked


def _latest_regular(items: list[ClassifiedCandidate]) -> list[ClassifiedCandidate]:
    return sorted(
        items,
        key=lambda item: (
            item.identity.episode if item.identity.episode is not None else -1,
            item.candidate.published or "",
            item.candidate.score,
        ),
        reverse=True,
    )


def _observed_target_max_gib(
    items: list[ClassifiedCandidate], requested_episode: int | None, episodes: int | None
) -> float | None:
    sizes = [
        comparable
        for item in items
        if item.work_match != "related_work"
        and item.identity.kind is EpisodeKind.REGULAR
        and item.identity.episode is not None
        and (requested_episode is None or item.identity.episode == requested_episode)
        and item.season_match not in {"other", "other_work"}
        and (comparable := nyaa.comparable_gib_per_episode(item.candidate, episodes)) is not None
    ]
    return round(max(sizes), 3) if sizes else None


def _inspect_details(
    selected: list[ClassifiedCandidate], args: argparse.Namespace
) -> DetailInspectionResult:
    result = DetailInspectionResult()
    strict = bool(getattr(args, "require_zh", False))
    if not args.inspect_details or (not strict and args.detail_limit <= 0):
        result.unchecked_count = len(selected)
        return result
    inspection_order = selected
    if strict:
        inspection_order = sorted(
            selected,
            key=lambda item: (
                item.candidate.subtitle_signal != "not confirmed",
                item.candidate.score,
            ),
            reverse=True,
        )
    else:
        inspection_order = inspection_order[: args.detail_limit]

    batch_size = max(1, int(getattr(args, "detail_batch_size", 5)))
    budget_seconds = max(0.0, float(getattr(args, "detail_budget_seconds", 30.0)))
    started = time.monotonic()
    cache: dict[str, str] = {}
    processed_count = 0
    stop = False
    for batch_start in range(0, len(inspection_order), batch_size):
        batch = inspection_order[batch_start : batch_start + batch_size]
        for item in batch:
            elapsed = time.monotonic() - started
            if strict and elapsed >= budget_seconds:
                result.budget_exhausted = True
                stop = True
                break
            processed_count += 1
            if not item.candidate.url:
                result.missing_url_count += 1
                item.candidate.reasons.append("Nyaa detail URL is unavailable")
                continue
            result.attempted_count += 1
            try:
                if item.candidate.url in cache:
                    detail_text = cache[item.candidate.url]
                else:
                    request_timeout = args.timeout
                    if strict:
                        remaining = max(0.1, budget_seconds - elapsed)
                        request_timeout = max(0.1, min(float(args.timeout), remaining))
                    detail_text = nyaa.fetch_nyaa_detail_text(
                        item.candidate.url, request_timeout
                    )
                    cache[item.candidate.url] = detail_text
                nyaa.apply_detail_subtitle_signal(
                    item.candidate, detail_text, args.want_zh, args.airing_priority
                )
                result.checked_count += 1
                if item.candidate.detail_chinese_confirmed:
                    result.verified_count += 1
                    if strict:
                        stop = True
                        break
                else:
                    result.rejected_count += 1
            except Exception as exc:  # noqa: BLE001 - failures must remain distinct from no subtitles.
                result.failed_count += 1
                message = f"Nyaa detail inspection failed for {item.candidate.url}: {exc}"
                result.failures.append(message)
                item.candidate.reasons.append(message)
        if stop:
            break

    result.unchecked_count = max(0, len(inspection_order) - processed_count)
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def search_release_report(
    args: argparse.Namespace,
    intent: SearchIntent | str = SearchIntent.SEASON_BROWSE,
    requested_episode: int | None = None,
    include_specials: bool = False,
    cache_path: Path | None = None,
    refresh_cache: bool = False,
    context: SearchContext | None = None,
) -> ReleaseSearchReport:
    intent = SearchIntent(intent)
    requested_season = normalize_season_number(args.season)
    requested_episode = requested_episode if requested_episode is not None else args.episode
    size_policy = size_policy_from_args(args)
    raw, failures, cache_state = collect_raw_candidates(args, cache_path, refresh_cache)
    if not raw:
        return ReleaseSearchReport(
            intent=intent,
            requested_season=requested_season,
            requested_episode=requested_episode,
            status="network_error" if failures else "no_rss_candidates",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0, "network_failures": len(failures)},
            failures=failures,
            cache=cache_state,
        )

    classified = _classify(raw, requested_season, context)
    in_season = [item for item in classified if _in_requested_season(item)]
    unknown_season = [item for item in classified if item.season_match == "unknown"]
    related_work = [item for item in classified if item.work_match == "related_work"]
    regular = [item for item in in_season if item.identity.kind is EpisodeKind.REGULAR]
    specials = [item for item in in_season if item.identity.kind is EpisodeKind.SPECIAL]
    unknown_identity = [
        item for item in in_season if item.identity.kind in {EpisodeKind.UNKNOWN, EpisodeKind.BATCH}
    ]
    diagnostics: dict[str, Any] = {
        "raw_count": len(classified),
        "season_matched_count": len(in_season),
        "season_unknown_count": len(unknown_season),
        "context_season_count": sum(item.season_source == "single_mainline" for item in classified),
        "related_work_count": len(related_work),
        "regular_count": len(regular),
        "special_count": len(specials),
        "unknown_count": len(unknown_identity),
        "wrong_season_count": sum(
            item.season_match == "other" for item in classified
        ),
        "quality_rejected_count": 0,
        "fallback_query_used": False,
        "observed_target_max_gib": _observed_target_max_gib(
            classified, requested_episode, args.episodes
        ),
        "size_policy": size_policy.as_dict(),
    }

    if intent is SearchIntent.SEASON_BATCH:
        return _season_batch_report(
            classified,
            args,
            size_policy,
            requested_season,
            context,
            diagnostics,
            failures,
            cache_state,
        )

    exact_regular = [
        item
        for item in regular
        if _is_exact_regular_episode(item, requested_episode)
    ]
    parse_is_uncertain = bool(unknown_identity or unknown_season)
    if (
        requested_episode is not None
        and not exact_regular
        and parse_is_uncertain
        and intent is not SearchIntent.SEASON_BROWSE
    ):
        fallback_args = _targeted_fallback_args(args, requested_season, requested_episode)
        fallback_raw, fallback_failures, fallback_cache = collect_raw_candidates(
            fallback_args, cache_path, refresh_cache
        )
        failures.extend(fallback_failures)
        raw = _merge_candidates(raw, fallback_raw)
        classified = _classify(raw, requested_season, context)
        in_season = [item for item in classified if _in_requested_season(item)]
        unknown_season = [item for item in classified if item.season_match == "unknown"]
        related_work = [item for item in classified if item.work_match == "related_work"]
        regular = [item for item in in_season if item.identity.kind is EpisodeKind.REGULAR]
        specials = [item for item in in_season if item.identity.kind is EpisodeKind.SPECIAL]
        unknown_identity = [
            item for item in in_season if item.identity.kind in {EpisodeKind.UNKNOWN, EpisodeKind.BATCH}
        ]
        diagnostics.update(
            {
                "raw_count": len(classified),
                "season_matched_count": len(in_season),
                "season_unknown_count": len(unknown_season),
                "context_season_count": sum(
                    item.season_source == "single_mainline" for item in classified
                ),
                "related_work_count": len(related_work),
                "regular_count": len(regular),
                "special_count": len(specials),
                "unknown_count": len(unknown_identity),
                "wrong_season_count": sum(
                    item.season_match == "other" for item in classified
                ),
                "fallback_query_used": True,
                "fallback_cache": fallback_cache,
                "observed_target_max_gib": _observed_target_max_gib(
                    classified, requested_episode, args.episodes
                ),
            }
        )
        cache_state = f"{cache_state}+fallback:{fallback_cache}"

    choices: list[ClassifiedCandidate] = []
    target_candidates: list[ClassifiedCandidate]
    if intent in {SearchIntent.SPECIFIC_EPISODE, SearchIntent.NEXT_TRACKED} or requested_episode is not None:
        target_candidates = [
            item
            for item in regular
            if _is_exact_regular_episode(item, requested_episode)
        ]
    elif intent is SearchIntent.LATEST_REGULAR:
        target_candidates = _latest_regular(regular)
    else:
        target_candidates = regular

    if intent is SearchIntent.LATEST_REGULAR and specials and not include_specials:
        choices = _rank(_latest_regular(regular)[:1] + _latest_regular(specials)[:1])
        return ReleaseSearchReport(
            intent=intent,
            requested_season=requested_season,
            requested_episode=requested_episode,
            status="needs_confirmation",
            selected=[],
            choices=choices,
            diagnostics=diagnostics,
            failures=failures,
            cache=cache_state,
        )

    if include_specials and specials:
        target_candidates = _latest_regular(specials)

    unconfirmed_work_candidates: list[ClassifiedCandidate] = []
    if getattr(args, "require_zh", False) and context is not None:
        unconfirmed_work_candidates = [
            item for item in target_candidates if item.work_match == "unknown"
        ]
        target_candidates = [
            item for item in target_candidates if item.work_match != "unknown"
        ]
        diagnostics["strict_work_match_required"] = True
        diagnostics["work_unconfirmed_count"] = len(unconfirmed_work_candidates)

    if not target_candidates:
        choices = _rank(
            (unconfirmed_work_candidates + specials + unknown_identity + unknown_season)[:2]
        )
        if choices:
            status = "needs_confirmation"
        elif requested_episode is not None:
            status = "no_nyaa_release_for_target"
        else:
            status = "latest_unresolved" if intent is SearchIntent.LATEST_REGULAR else "no_nyaa_release_for_target"
        return ReleaseSearchReport(
            intent=intent,
            requested_season=requested_season,
            requested_episode=requested_episode,
            status=status,
            selected=[],
            choices=choices,
            diagnostics=diagnostics,
            failures=failures,
            cache=cache_state,
        )

    qualified, size_counts = _quality_filter(target_candidates, args, size_policy)
    diagnostics.update(size_counts)
    diagnostics["quality_rejected_count"] = sum(size_counts.values())
    if not qualified:
        return ReleaseSearchReport(
            intent=intent,
            requested_season=requested_season,
            requested_episode=requested_episode,
            status="release_unqualified",
            selected=[],
            choices=_rank(target_candidates)[:2],
            diagnostics=diagnostics,
            failures=failures,
            cache=cache_state,
        )

    selected = _rank(qualified)
    detail_inspection = _inspect_details(selected, args)
    diagnostics.update(detail_inspection.as_diagnostics())
    failures.extend(detail_inspection.failures[:2])
    if getattr(args, "require_zh", False):
        verified = [item for item in selected if item.candidate.detail_chinese_confirmed]
        diagnostics.update(
            {
                "required_subtitle": "simplified_or_traditional_chinese",
            }
        )
        if not verified:
            return ReleaseSearchReport(
                intent=intent,
                requested_season=requested_season,
                requested_episode=requested_episode,
                status=(
                    "subtitle_unqualified"
                    if detail_inspection.complete
                    else "subtitle_check_incomplete"
                ),
                selected=[],
                choices=[],
                diagnostics=diagnostics,
                failures=failures,
                cache=cache_state,
            )
        selected = _rank(verified)
    selected = _rank(selected)[: max(1, args.limit)]
    return ReleaseSearchReport(
        intent=intent,
        requested_season=requested_season,
        requested_episode=requested_episode,
        status="found",
        selected=selected,
        choices=[],
        diagnostics=diagnostics,
        failures=failures,
        cache=cache_state,
    )
