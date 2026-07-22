#!/usr/bin/env python3
"""High-level anime release finder: resolve title, search Nyaa, update airing state."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from release_identity import EpisodeKind, normalize_season_number, parse_release_identity
from release_search_core import SearchContext, SearchIntent, search_release_report
from runtime_paths import DEFAULT_STATE
from search_nyaa_releases import DEFAULT_TIER_MIN_GIB


HERE = Path(__file__).resolve().parent
DEFAULT_CACHE = DEFAULT_STATE.parent / ".cache" / "find_nyaa_raw_cache.json"
DEFAULT_SCHEDULE_CACHE = DEFAULT_STATE.parent / ".cache" / "airing_schedule_cache.json"
DEFAULT_NICKNAME_ALIASES = HERE.parent / "references" / "anime_nickname_aliases.json"
ANILIST_API = "https://graphql.anilist.co"
BANGUMI_SEARCH_API = "https://api.bgm.tv/v0/search/subjects"
SCHEDULE_CACHE_VERSION = 4
SCHEDULE_CACHE_SECONDS = 30 * 60
MAINLINE_FORMATS = {"TV", "TV_SHORT", "ONA"}
MAINLINE_RELATION_TYPES = {"PREQUEL", "SEQUEL"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class ResolvedAnime:
    title: str
    aliases: list[str] = field(default_factory=list)
    search_titles: list[str] = field(default_factory=list)
    verified_search_titles: list[str] = field(default_factory=list)
    season: str | None = None
    current: bool = False
    trackable: bool = False
    source: str = "none"
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    duration_min: int | None = None
    bangumi_id: int | None = None
    anilist_id: int | None = None
    next_airing_episode: int | None = None
    next_airing_at: int | None = None
    mainline_scope: str = "unknown"
    related_titles: list[str] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class IdentityResolution:
    status: str
    resolved: ResolvedAnime
    state_show: dict[str, Any] | None
    tracked: bool
    input_kind: str
    sources: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    resolver: str = "not_used"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def unique(values: list[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        clean = re.sub(r"\s+", " ", value).strip()
        key = norm(clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def lookup_nickname_alias(query: str, path: Path = DEFAULT_NICKNAME_ALIASES) -> dict[str, Any] | None:
    """Resolve a curated nickname or character catchphrase without touching watch state."""
    key = norm(query)
    if not key:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        canonical = entry.get("canonical_title")
        aliases = entry.get("aliases")
        if not isinstance(canonical, str) or not isinstance(aliases, list):
            continue
        names = [canonical, *(name for name in aliases if isinstance(name, str))]
        if key in {norm(name) for name in names}:
            return {"canonical_title": canonical, "aliases": unique(names)}
    return None


def emit_json(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]", text))


def has_latin_search_text(text: str) -> bool:
    return bool(re.search(r"[a-z0-9]", text, re.I))


def is_latin_search_title(text: str) -> bool:
    return has_latin_search_text(text) and not contains_cjk(text)


def latin_search_titles(values: list[str | None]) -> list[str]:
    return [name for name in unique(values) if is_latin_search_title(name)]


def search_name_score(name: str, canonical_title: str) -> int:
    compact = norm(name)
    score = 0
    if has_latin_search_text(name):
        score += 100
    if contains_cjk(name):
        score -= 60
    if compact == norm(canonical_title):
        score += 30
    if 4 <= len(compact) <= 32:
        score += 10
    if "season" in name.casefold():
        score -= 8
    return score


def is_redundant_search_name(candidate: str, selected: list[str]) -> bool:
    candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate.casefold()))
    if len(candidate_tokens) < 2:
        return False
    for existing in selected:
        existing_tokens = set(re.findall(r"[a-z0-9]+", existing.casefold()))
        if len(existing_tokens) >= 2 and (candidate_tokens <= existing_tokens or existing_tokens <= candidate_tokens):
            return True
    return False


def select_search_names(
    title: str,
    aliases: list[str],
    query_limit: int,
    preferred: list[str] | None = None,
) -> list[str]:
    preferred_latin = latin_search_titles(preferred or [])
    names = unique([*preferred_latin, title, *aliases])
    pool = latin_search_titles(names)
    if not pool:
        return []
    ranked = sorted(
        enumerate(pool),
        key=lambda item: (
            1000 - preferred_latin.index(item[1]) if item[1] in preferred_latin else search_name_score(item[1], title),
            -item[0],
        ),
        reverse=True,
    )
    selected: list[str] = []
    for _, name in ranked:
        if is_redundant_search_name(name, selected):
            continue
        selected.append(name)
        if len(selected) >= max(1, query_limit):
            break
    return selected


STRICT_ZH_ANCHOR_STOPWORDS = {
    "anime",
    "season",
    "movie",
    "the",
    "this",
    "with",
}


def strict_zh_search_names(
    base_names: list[str],
    original_title: str,
    episode: int | None,
    release_group_hints: list[str] | None = None,
    cjk_aliases: list[str] | None = None,
) -> list[str]:
    """Add bounded release-search bridges only for explicit Chinese-subtitle requests."""
    expanded = list(base_names)
    cjk_names = [name for name in unique([original_title, *(cjk_aliases or [])]) if contains_cjk(name)]
    expanded.extend(cjk_names[:2])

    for name in base_names:
        folded = "".join(
            character
            for character in unicodedata.normalize("NFKD", name)
            if not unicodedata.combining(character)
        )
        if folded != name and is_latin_search_title(folded):
            expanded.append(folded)
            break

    anchor = None
    for name in base_names:
        for token in re.findall(r"[A-Za-z0-9]+", name):
            if len(token) >= 5 and token.casefold() not in STRICT_ZH_ANCHOR_STOPWORDS:
                anchor = token
                break
        if anchor:
            break
    if anchor:
        bridge = f"{anchor} {episode:02d}" if episode is not None else anchor
        for group in (release_group_hints or [])[:1]:
            normalized_group = group.strip().strip("[]")
            if normalized_group:
                expanded.append(f"{normalized_group} {bridge}")
        expanded.append(bridge)
    return unique(expanded)


def promote_search_titles(current: list[str], matched_queries: list[str]) -> list[str]:
    """Learn the release title that actually produced the selected Nyaa item."""
    matched_latin = latin_search_titles(matched_queries)
    current_latin = latin_search_titles(current)
    return unique([*matched_latin, *current_latin])


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "shows": []}
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    data.setdefault("version", 1)
    data.setdefault("shows", [])
    return data


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def names_for(show: dict[str, Any]) -> list[str]:
    return unique([show.get("title"), *show.get("aliases", []), *show.get("search_titles", [])])


def find_show_by_identity(
    data: dict[str, Any], bangumi_id: int | None = None, anilist_id: int | None = None
) -> dict[str, Any] | None:
    matches = []
    for show in data.get("shows", []):
        if bangumi_id and show.get("bangumi_id") == bangumi_id:
            matches.append(show)
        elif anilist_id and show.get("anilist_id") == anilist_id:
            matches.append(show)
    unique_matches = list({id(show): show for show in matches}.values())
    return unique_matches[0] if len(unique_matches) == 1 else None


def find_show(data: dict[str, Any], query: str) -> dict[str, Any] | None:
    q = norm(query)
    if not q:
        return None

    exact_matches: list[dict[str, Any]] = []
    for show in data.get("shows", []):
        for name in names_for(show):
            n = norm(name)
            if q == n:
                exact_matches.append(show)
                break
    if len(exact_matches) == 1:
        return exact_matches[0]
    if exact_matches or len(q) < 4:
        return None

    partial_matches: list[dict[str, Any]] = []
    for show in data.get("shows", []):
        for name in names_for(show):
            n = norm(name)
            if n and (q in n or n in q):
                partial_matches.append(show)
                break
    if len({id(show) for show in partial_matches}) == 1:
        return partial_matches[0]
    return None


def _name_position(text: str, name: str) -> int:
    if not name or len(norm(name)) < 4:
        return -1
    return text.casefold().find(name.casefold())


def detect_tracked_titles(data: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """Find distinct tracked works explicitly mentioned inside one request."""
    mentions: list[dict[str, Any]] = []
    for show in data.get("shows", []):
        matches = []
        for name in names_for(show):
            position = _name_position(text, name)
            if position >= 0:
                matches.append((position, -len(name), name))
        if matches:
            position, _, matched_name = min(matches)
            mentions.append(
                {
                    "title": show.get("title"),
                    "matched_name": matched_name,
                    "position": position,
                }
            )
    mentions.sort(key=lambda item: (item["position"], -len(item["matched_name"])))
    return mentions


def alias_mentions_multiple_canonical_titles(data: dict[str, Any], alias: str) -> bool:
    matches = {
        id(show)
        for show in data.get("shows", [])
        if _name_position(alias, str(show.get("title") or "")) >= 0
    }
    return len(matches) >= 2


def sanitize_state_aliases(data: dict[str, Any]) -> list[dict[str, str]]:
    removed: list[dict[str, str]] = []
    for show in data.get("shows", []):
        kept = []
        for alias in show.get("aliases", []):
            if alias_mentions_multiple_canonical_titles(data, alias):
                removed.append({"title": str(show.get("title") or ""), "alias": alias})
            else:
                kept.append(alias)
        show["aliases"] = kept
    return removed


def delete_show(data: dict[str, Any], names: list[str]) -> dict[str, Any] | None:
    for name in names:
        show = find_show(data, name)
        if show is None:
            continue
        data["shows"] = [item for item in data.get("shows", []) if item is not show]
        return show
    return None


def upsert_show(
    data: dict[str, Any],
    title: str,
    aliases: list[str],
    season: str | None,
    latest_episode: int | None,
    next_episode: int | None,
    notes: str,
    resolved: ResolvedAnime | None = None,
    status: str = "airing",
    show_hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    show = show_hint if show_hint in data.get("shows", []) else None
    if show is None:
        show = find_show_by_identity(
            data,
            resolved.bangumi_id if resolved else None,
            resolved.anilist_id if resolved else None,
        )
    if show is None:
        show = find_show(data, title)
    if show is None:
        for alias in aliases:
            show = find_show(data, alias)
            if show is not None:
                break
    if show is None:
        show = {"title": title, "aliases": [], "airing": True, "created_at": now_iso()}
        data["shows"].append(show)

    show["title"] = show.get("title") or title
    candidate_aliases = unique([*show.get("aliases", []), *aliases, title])
    show["aliases"] = [
        alias for alias in candidate_aliases if not alias_mentions_multiple_canonical_titles(data, alias)
    ]
    show["aliases"] = [alias for alias in show["aliases"] if norm(alias) != norm(show["title"])]
    if season:
        show["season"] = season
    if latest_episode is not None:
        show["latest_known_episode"] = latest_episode
    if next_episode is not None:
        show["next_episode"] = next_episode
    if resolved and resolved.episodes:
        show["total_episodes"] = resolved.episodes
    if resolved and resolved.duration_min:
        show["duration_min"] = resolved.duration_min
    if resolved and resolved.bangumi_id:
        show["bangumi_id"] = resolved.bangumi_id
    if resolved and resolved.format:
        show["format"] = resolved.format
    if resolved and resolved.anilist_id:
        show["anilist_id"] = resolved.anilist_id
    if resolved and resolved.mainline_scope != "unknown":
        show["mainline_scope"] = resolved.mainline_scope
    if resolved and resolved.related_titles:
        show["related_titles"] = resolved.related_titles
    if resolved and resolved.search_titles:
        show["search_titles"] = resolved.search_titles
    if resolved and resolved.verified_search_titles:
        show["verified_search_titles"] = resolved.verified_search_titles
    show["status"] = status
    show["airing"] = True
    show["notes"] = notes
    show["updated_at"] = now_iso()
    if resolved and (resolved.bangumi_id or resolved.anilist_id):
        duplicate_fields = ("aliases", "search_titles", "verified_search_titles", "related_titles")
        numeric_fields = ("watched_episode", "latest_known_episode", "next_episode")
        duplicates: list[dict[str, Any]] = []
        for other in data.get("shows", []):
            if other is show:
                continue
            same_bangumi = bool(resolved.bangumi_id and other.get("bangumi_id") == resolved.bangumi_id)
            same_anilist = bool(resolved.anilist_id and other.get("anilist_id") == resolved.anilist_id)
            if not (same_bangumi or same_anilist):
                continue
            duplicates.append(other)
            merged_aliases = unique([*show.get("aliases", []), other.get("title"), *other.get("aliases", [])])
            show["aliases"] = [
                alias for alias in merged_aliases if not alias_mentions_multiple_canonical_titles(data, alias)
            ]
            for field_name in duplicate_fields[1:]:
                show[field_name] = unique([*show.get(field_name, []), *other.get(field_name, [])])
            for field_name in numeric_fields:
                values = [value for value in (show.get(field_name), other.get(field_name)) if isinstance(value, int)]
                if values:
                    show[field_name] = max(values)
            for field_name in ("total_episodes", "duration_min", "format", "mainline_scope"):
                if not show.get(field_name) and other.get(field_name):
                    show[field_name] = other[field_name]
        if duplicates:
            data["shows"] = [item for item in data.get("shows", []) if item not in duplicates]
    return show


def current_anime_season(today: date) -> tuple[str, int]:
    if today.month <= 3:
        return "WINTER", today.year
    if today.month <= 6:
        return "SPRING", today.year
    if today.month <= 9:
        return "SUMMER", today.year
    return "FALL", today.year


def anilist_request(query: str, timeout: int) -> dict[str, Any]:
    gql = """
    query ($search: String) {
      Page(page: 1, perPage: 6) {
        media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
          id
          format
          status
          season
          seasonYear
          episodes
          duration
          nextAiringEpisode { episode airingAt }
          isAdult
          title { romaji english native }
          synonyms
          relations {
            edges {
              relationType
              node {
                id
                type
                format
                title { romaji english native }
                synonyms
              }
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": gql, "variables": {"search": query}}).encode("utf-8")
    request = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CodexAnimeFinder/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def anilist_media_request(media_id: int, timeout: int) -> dict[str, Any]:
    gql = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        format
        status
        season
        seasonYear
        episodes
        duration
        nextAiringEpisode { episode airingAt }
        isAdult
        title { romaji english native }
        synonyms
        relations {
          edges {
            relationType
            node {
              id
              type
              format
              title { romaji english native }
              synonyms
            }
          }
        }
      }
    }
    """
    payload = json.dumps({"query": gql, "variables": {"id": media_id}}).encode("utf-8")
    request = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CodexAnimeFinder/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def bangumi_request(query: str, timeout: int) -> dict[str, Any]:
    payload = json.dumps({"keyword": query, "filter": {"type": [2]}}).encode("utf-8")
    request = urllib.request.Request(
        BANGUMI_SEARCH_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CodexAnimeFinder/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def bangumi_infobox_values(item: dict[str, Any], keys: set[str]) -> list[str]:
    values: list[str | None] = []
    for field in item.get("infobox") or []:
        if not isinstance(field, dict) or field.get("key") not in keys:
            continue
        value = field.get("value")
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    values.append(entry)
                elif isinstance(entry, dict):
                    values.append(entry.get("v"))
    return unique(values)


def bangumi_item_names(item: dict[str, Any]) -> list[str]:
    return unique(
        [
            item.get("name_cn"),
            item.get("name"),
            *bangumi_infobox_values(item, {"中文名", "别名"}),
        ]
    )


def bangumi_item_is_current(item: dict[str, Any], today: date) -> bool:
    try:
        start = date.fromisoformat(str(item.get("date")))
    except ValueError:
        return False
    current_season, current_year = current_anime_season(today)
    season_months = {
        "WINTER": {1, 2, 3},
        "SPRING": {4, 5, 6},
        "SUMMER": {7, 8, 9},
        "FALL": {10, 11, 12},
    }
    return start.year == current_year and start.month in season_months[current_season]


def bangumi_item_to_resolved(query: str, item: dict[str, Any], today: date) -> tuple[ResolvedAnime, int]:
    names = bangumi_item_names(item)
    search_titles = latin_search_titles(names)
    title = search_titles[0] if search_titles else item.get("name_cn") or item.get("name") or query
    platform = str(item.get("platform") or "").upper()
    anime_format = "TV" if platform == "TV" else "ONA" if platform in {"WEB", "ONA"} else platform or None
    current = bangumi_item_is_current(item, today)
    episode_values = bangumi_infobox_values(item, {"话数"})
    episode_match = re.search(r"\d+", episode_values[0]) if episode_values else None
    episodes = int(episode_match.group()) if episode_match else None
    score = name_score(query, names)
    if current:
        score += 10
    if anime_format in MAINLINE_FORMATS:
        score += 5
    resolved = ResolvedAnime(
        title=title,
        aliases=[name for name in unique([*names, query]) if norm(name) != norm(title)],
        search_titles=search_titles,
        season=infer_season(names),
        current=current,
        trackable=bool(current and anime_format in MAINLINE_FORMATS),
        source="bangumi",
        format=anime_format,
        status="RELEASING" if current else None,
        episodes=episodes,
        bangumi_id=item.get("id"),
    )
    return resolved, score


def resolve_bangumi_title(query: str, timeout: int, today: date) -> tuple[str, ResolvedAnime | None]:
    try:
        data = bangumi_request(query, timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "resolver_failed", ResolvedAnime(title=query, source=f"bangumi error: {exc}")
    items = [item for item in data.get("data", []) if isinstance(item, dict)]
    if not items:
        return "resolver_failed", ResolvedAnime(title=query, source="bangumi no result")
    ranked = sorted(
        (bangumi_item_to_resolved(query, item, today) for item in items[:8]),
        key=lambda pair: pair[1],
        reverse=True,
    )
    top, top_score = ranked[0]
    if top_score < 35:
        return "resolver_failed", top
    if len(ranked) > 1:
        second, second_score = ranked[1]
        if second_score >= top_score - 6 and norm(second.title) != norm(top.title):
            top.choices = [
                {
                    "title": choice.title,
                    "aliases": choice.aliases[:3],
                    "format": choice.format,
                    "bangumi_id": choice.bangumi_id,
                }
                for choice, _ in ranked[:4]
            ]
            return "ambiguous", top
    return "resolved", top


def resolved_from_state(show: dict[str, Any], fallback_title: str, source: str = "state") -> ResolvedAnime:
    return ResolvedAnime(
        title=show.get("title") or fallback_title,
        aliases=show.get("aliases", []),
        search_titles=show.get("search_titles", []),
        verified_search_titles=show.get("verified_search_titles", []),
        season=show.get("season"),
        current=True,
        trackable=True,
        source=source,
        format=show.get("format"),
        episodes=show.get("total_episodes"),
        duration_min=show.get("duration_min"),
        bangumi_id=show.get("bangumi_id"),
        anilist_id=show.get("anilist_id"),
        mainline_scope=show.get("mainline_scope", "unknown"),
        related_titles=show.get("related_titles", []),
    )


def name_score(query: str, names: list[str]) -> int:
    q = norm(query)
    if not q:
        return 0
    best = 0
    for name in names:
        n = norm(name)
        if not n:
            continue
        if q == n:
            best = max(best, 100)
        elif q in n or n in q:
            best = max(best, 82)
        else:
            q_tokens = set(re.findall(r"[a-z0-9]+", query.casefold()))
            n_tokens = set(re.findall(r"[a-z0-9]+", name.casefold()))
            if q_tokens and n_tokens:
                best = max(best, int(60 * len(q_tokens & n_tokens) / len(q_tokens | n_tokens)))
    return best


def infer_season(names: list[str]) -> str | None:
    for name in names:
        season = parse_release_identity(name).season
        if season is not None:
            return f"S{season:02d}"
    return None


def canonical_season(value: str | None) -> str | None:
    number = normalize_season_number(value)
    return f"S{number:02d}" if number is not None else value


def related_anime_titles(media: dict[str, Any]) -> list[str]:
    titles: list[str | None] = []
    relations = media.get("relations")
    edges = relations.get("edges") if isinstance(relations, dict) else None
    if not isinstance(edges, list):
        return []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict) or node.get("type") != "ANIME":
            continue
        title_data = node.get("title") or {}
        titles.extend(
            [
                title_data.get("english"),
                title_data.get("romaji"),
                title_data.get("native"),
                *(node.get("synonyms") or []),
            ]
        )
    return unique(titles)


def mainline_scope_from_media(media: dict[str, Any]) -> str:
    if media.get("format") not in MAINLINE_FORMATS:
        return "unknown"
    relations = media.get("relations")
    edges = relations.get("edges") if isinstance(relations, dict) else None
    if not isinstance(edges, list):
        return "unknown"
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("relationType") not in MAINLINE_RELATION_TYPES:
            continue
        node = edge.get("node")
        if (
            isinstance(node, dict)
            and node.get("type") == "ANIME"
            and node.get("format") in MAINLINE_FORMATS
        ):
            return "multi"
    return "single"


def media_to_resolved(query: str, media: dict[str, Any], today: date) -> tuple[ResolvedAnime, int]:
    title_data = media.get("title") or {}
    release_titles = unique([title_data.get("english"), title_data.get("romaji")])
    release_titles = [name for name in release_titles if has_latin_search_text(name) and not contains_cjk(name)]
    official_names = unique(
        [
            title_data.get("english"),
            title_data.get("romaji"),
            title_data.get("native"),
            *(media.get("synonyms") or []),
        ]
    )
    names = unique([*official_names, query])
    title = title_data.get("english") or title_data.get("romaji") or title_data.get("native") or query
    current_season, current_year = current_anime_season(today)
    anime_format = media.get("format")
    status = media.get("status")
    next_airing = media.get("nextAiringEpisode") or {}
    mainline_scope = mainline_scope_from_media(media)
    resolved_season = infer_season(names)
    if resolved_season is None and mainline_scope == "single" and anime_format in MAINLINE_FORMATS:
        resolved_season = "S01"
    is_current = bool(
        status == "RELEASING"
        or (media.get("season") == current_season and media.get("seasonYear") == current_year)
    )
    trackable = bool(is_current and anime_format in {"TV", "TV_SHORT", "ONA"})
    score = name_score(query, official_names)
    if is_current:
        score += 10
    if anime_format in {"TV", "TV_SHORT", "ONA"}:
        score += 5
    if media.get("isAdult"):
        score -= 100
    return (
        ResolvedAnime(
            title=title,
            aliases=[name for name in names if norm(name) != norm(title)],
            search_titles=release_titles,
            season=resolved_season,
            current=is_current,
            trackable=trackable,
            source="anilist",
            format=anime_format,
            status=status,
            episodes=media.get("episodes"),
            duration_min=media.get("duration"),
            anilist_id=media.get("id"),
            next_airing_episode=next_airing.get("episode"),
            next_airing_at=next_airing.get("airingAt"),
            mainline_scope=mainline_scope,
            related_titles=related_anime_titles(media),
        ),
        score,
    )


def resolve_title(query: str, timeout: int, today: date) -> tuple[str, ResolvedAnime | None]:
    try:
        data = anilist_request(query, timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "resolver_failed", ResolvedAnime(title=query, source=f"anilist error: {exc}")

    media_items = [item for item in data.get("data", {}).get("Page", {}).get("media", []) if not item.get("isAdult")]
    if not media_items:
        return "resolver_failed", ResolvedAnime(title=query, source="anilist no result")

    ranked = sorted((media_to_resolved(query, item, today) for item in media_items), key=lambda item: item[1], reverse=True)
    top, top_score = ranked[0]
    if top_score < 35:
        return "resolver_failed", top

    if len(ranked) > 1:
        second, second_score = ranked[1]
        if second_score >= top_score - 6 and norm(second.title) != norm(top.title):
            top.choices = [
                {"title": choice.title, "aliases": choice.aliases[:3], "format": choice.format, "status": choice.status}
                for choice, _ in ranked[:4]
            ]
            return "ambiguous", top

    return "resolved", top


def schedule_cache_key(resolved: ResolvedAnime) -> str:
    if resolved.anilist_id:
        return f"id:{resolved.anilist_id}"
    return f"title:{norm(resolved.title)}"


def load_schedule_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    if data.get("version") != SCHEDULE_CACHE_VERSION or not isinstance(data.get("entries"), dict):
        return {"version": SCHEDULE_CACHE_VERSION, "entries": {}}
    return data


def save_schedule_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp.replace(path)
    except OSError:
        return


def resolved_snapshot(resolved: ResolvedAnime) -> dict[str, Any]:
    return {
        "title": resolved.title,
        "aliases": resolved.aliases,
        "search_titles": resolved.search_titles,
        "verified_search_titles": resolved.verified_search_titles,
        "season": resolved.season,
        "current": resolved.current,
        "trackable": resolved.trackable,
        "source": resolved.source,
        "format": resolved.format,
        "status": resolved.status,
        "episodes": resolved.episodes,
        "duration_min": resolved.duration_min,
        "bangumi_id": resolved.bangumi_id,
        "anilist_id": resolved.anilist_id,
        "next_airing_episode": resolved.next_airing_episode,
        "next_airing_at": resolved.next_airing_at,
        "mainline_scope": resolved.mainline_scope,
        "related_titles": resolved.related_titles,
    }


def resolved_from_snapshot(snapshot: dict[str, Any], fallback: ResolvedAnime) -> ResolvedAnime:
    merged = {**resolved_snapshot(fallback), **snapshot}
    return ResolvedAnime(**merged)


def read_schedule_snapshot(path: Path, key: str) -> dict[str, Any] | None:
    cache = load_schedule_cache(path)
    entry = cache["entries"].get(key)
    if not isinstance(entry, dict):
        return None
    try:
        is_expired = float(entry.get("expires_at", 0)) <= time.time()
    except (TypeError, ValueError):
        is_expired = True
    if is_expired:
        return None
    snapshot = entry.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def write_schedule_snapshot(path: Path, key: str, resolved: ResolvedAnime) -> None:
    cache = load_schedule_cache(path)
    now = time.time()
    cache["entries"][key] = {
        "expires_at": now + SCHEDULE_CACHE_SECONDS,
        "snapshot": resolved_snapshot(resolved),
    }
    save_schedule_cache(path, cache)


def write_schedule_snapshots(path: Path, keys: list[str], resolved: ResolvedAnime) -> None:
    for key in dict.fromkeys(keys):
        write_schedule_snapshot(path, key, resolved)


def merge_resolved(base: ResolvedAnime, fresh: ResolvedAnime) -> ResolvedAnime:
    fresh.aliases = unique([*base.aliases, *fresh.aliases])
    fresh.search_titles = unique([*base.search_titles, *fresh.search_titles])
    fresh.verified_search_titles = unique([*base.verified_search_titles, *fresh.verified_search_titles])
    fresh.related_titles = unique([*base.related_titles, *fresh.related_titles])
    fresh.season = base.season or fresh.season
    fresh.trackable = base.trackable or fresh.trackable
    fresh.current = base.current or fresh.current
    fresh.bangumi_id = fresh.bangumi_id or base.bangumi_id
    fresh.anilist_id = fresh.anilist_id or base.anilist_id
    if base.source and base.source not in {"none", fresh.source}:
        fresh.source = f"{base.source}+{fresh.source}"
    if fresh.mainline_scope == "unknown":
        fresh.mainline_scope = base.mainline_scope
    return fresh


def hydrate_airing_metadata(
    resolved: ResolvedAnime,
    timeout: int,
    cache_path: Path,
    refresh_cache: bool,
    today: date,
) -> tuple[ResolvedAnime, str]:
    key = schedule_cache_key(resolved)
    if not refresh_cache:
        snapshot = read_schedule_snapshot(cache_path, key)
        if snapshot:
            return resolved_from_snapshot(snapshot, resolved), "hit"

    if resolved.next_airing_episode is not None or resolved.status == "FINISHED":
        write_schedule_snapshot(cache_path, key, resolved)
        return resolved, "resolver"

    try:
        if resolved.anilist_id:
            data = anilist_media_request(resolved.anilist_id, timeout)
            media = data.get("data", {}).get("Media")
            if media:
                fresh, _ = media_to_resolved(resolved.title, media, today)
                merged = merge_resolved(resolved, fresh)
                write_schedule_snapshots(cache_path, [key, schedule_cache_key(merged)], merged)
                return merged, "miss"
        for query in unique([*resolved.search_titles, resolved.title, *resolved.aliases])[:2]:
            status, fresh = resolve_title(query, timeout, today)
            if status == "resolved" and fresh:
                merged = merge_resolved(resolved, fresh)
                write_schedule_snapshots(cache_path, [key, schedule_cache_key(merged)], merged)
                return merged, "miss"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass
    return resolved, "unavailable"


def latest_regular_target(
    resolved: ResolvedAnime, state_show: dict[str, Any] | None
) -> tuple[int | None, str]:
    now = int(time.time())
    if resolved.next_airing_episode and resolved.next_airing_at and resolved.next_airing_at > now:
        target = resolved.next_airing_episode - 1
        return (target, "anilist_schedule") if target > 0 else (None, "not_aired_yet")
    if resolved.status == "FINISHED" and resolved.episodes:
        return resolved.episodes, "anilist_finished_total"
    if state_show and isinstance(state_show.get("latest_known_episode"), int):
        return state_show["latest_known_episode"], "observed_state_only"
    return None, "latest_unresolved"


def build_search_args(
    title: str,
    aliases: list[str],
    args: argparse.Namespace,
    season: str | None,
    episode: int | None,
    duration_min: int | None,
) -> argparse.Namespace:
    return argparse.Namespace(
        query=title,
        alias=aliases,
        category="1_0",
        filter="0",
        limit=args.limit,
        timeout=args.timeout,
        want_zh=args.want_zh,
        require_zh=args.require_zh,
        airing_priority=args.airing_priority,
        resolution=None,
        tier=args.tier,
        season=season,
        episode=episode,
        duration_min=duration_min or 22.0,
        episodes=None,
        min_gib_per_episode=args.min_gib_per_episode,
        max_gib_per_episode=args.max_gib_per_episode,
        size_policy_source=args.size_policy_source,
        prefer_group=args.release_group_hint,
        avoid_group=[],
        inspect_details=args.require_zh,
        detail_limit=5 if args.require_zh else 0,
        detail_batch_size=5,
        detail_budget_seconds=30.0,
        include_magnets=args.include_magnet,
        magnet_only=False,
        legal_ok=args.legal_ok,
    )


def selected_view(
    candidate: dict[str, Any] | None,
    include_page_link: bool,
    require_zh: bool = False,
) -> dict[str, Any] | None:
    if not candidate:
        return None
    selected = {
        "title": candidate.get("title"),
        "size": candidate.get("size"),
        "seeders": candidate.get("seeders"),
        "resolution": candidate.get("resolution"),
        "magnet": candidate.get("magnet"),
        "subtitle_signal": candidate.get("subtitle_signal"),
        "detail_chinese_confirmed": candidate.get("detail_chinese_confirmed"),
        "detail_subtitle_signal": candidate.get("detail_subtitle_signal"),
        "score": candidate.get("score"),
        "effective_season": candidate.get("effective_season"),
        "season_source": candidate.get("season_source"),
        "work_match": candidate.get("work_match"),
        "coverage": candidate.get("coverage"),
    }
    if candidate.get("work_match_evidence") is not None:
        selected["work_match_evidence"] = candidate["work_match_evidence"]
    if include_page_link or require_zh:
        selected["url"] = candidate.get("url")
    return selected


def is_final_episode(resolved: ResolvedAnime | None, episode: int | None) -> bool:
    if not resolved or episode is None:
        return False
    return bool(resolved.status == "FINISHED" and resolved.episodes and episode >= resolved.episodes)


def result_output_contract(
    selected: dict[str, Any] | None,
    include_magnet: bool,
    require_zh: bool = False,
) -> dict[str, Any]:
    required = ["title", "size", "seeders"]
    if include_magnet:
        required.append("magnet")
    if require_zh:
        required.extend(["url", "detail_chinese_confirmed", "detail_subtitle_signal"])
    missing = []
    for field_name in required:
        value = (selected or {}).get(field_name)
        if value is None or value == "" or (field_name == "detail_chinese_confirmed" and value is not True):
            missing.append(field_name)
    return {
        "ready": not missing,
        "magnet_requested": include_magnet,
        "required_fields": required,
        "missing_fields": missing,
    }


def render_result_reply(
    display_title: str,
    season: str | None,
    episode: int | None,
    selected: dict[str, Any],
    include_magnet: bool,
) -> str:
    episode_label = ""
    if episode is not None:
        season_label = canonical_season(season) or "S01"
        episode_label = f" {season_label}E{episode:02d}"
    subtitle = selected.get("subtitle_signal") or "字幕未确认"
    if str(subtitle).casefold() in {"not confirmed", "unknown", "none"}:
        subtitle = "字幕未确认"
    lines = [
        f"《{display_title}》{episode_label}",
        str(selected.get("title") or ""),
        f"{selected.get('size')} | {selected.get('seeders')} 做种 | {subtitle}",
    ]
    if selected.get("url"):
        lines.append(f"Nyaa: {selected['url']}")
    if include_magnet:
        lines.extend(["", "```text", str(selected.get("magnet") or ""), "```"])
    return "\n".join(lines)


def render_season_batch_reply(
    display_title: str,
    season: str | None,
    selected: dict[str, Any],
    include_magnet: bool,
) -> str:
    coverage = selected.get("coverage") or {}
    season_label = canonical_season(season) or "S01"
    episode_count = coverage.get("expected_episodes")
    scope_label = "精确单季包" if coverage.get("scope") == "exact" else "含目标季的多季合集"
    minimum = coverage.get("min_gib_per_episode")
    maximum = coverage.get("max_gib_per_episode")
    if coverage.get("source_exempt"):
        size_range = "BDMV/Remux 高画质来源"
    elif minimum is not None and maximum is not None:
        size_range = f"{minimum:g}-{maximum:g} GiB/集"
    else:
        size_range = "逐集体积已核验"
    lines = [
        f"《{display_title}》{season_label} 整季",
        str(selected.get("title") or ""),
        f"{scope_label} | {episode_count or '?'} 集 | {size_range} | {selected.get('seeders')} 做种",
    ]
    if selected.get("url"):
        lines.append(f"Nyaa: {selected['url']}")
    if include_magnet:
        lines.extend(["", "```text", str(selected.get("magnet") or ""), "```"])
    return "\n".join(lines)


def render_failure_reply(
    status: str,
    display_title: str,
    season: str | None,
    intent: SearchIntent,
    tier: str,
    diagnostic: dict[str, Any] | None = None,
) -> str:
    season_label = canonical_season(season) or "S01"
    subject = f"《{display_title}》{season_label} 整季" if intent is SearchIntent.SEASON_BATCH else f"《{display_title}》"
    tier_label = {"browse": "轻量观看", "watch": "普通观看", "premium": "高画质"}.get(tier, tier)
    size_policy = (diagnostic or {}).get("size_policy") or {}
    has_above_range_release = (
        intent is not SearchIntent.SEASON_BATCH
        and size_policy.get("hard_max_gib") is not None
        and int((diagnostic or {}).get("above_max_count") or 0) > 0
    )
    if has_above_range_release:
        release_unqualified = f"{subject}当前区间内没有合格资源，但有高于该区间的资源可选。"
    elif intent is SearchIntent.SEASON_BATCH:
        release_unqualified = (
            f"{subject}存在对应发布，但没有资源的每个正篇文件都满足{tier_label}档位；"
            "未达当前硬门槛的候选不会展示。"
        )
    else:
        release_unqualified = f"{subject}存在对应发布，但没有资源满足{tier_label}档位。"
    messages = {
        "no_complete_season_release": f"{subject}没有找到覆盖完整目标季且通过核验的资源包。",
        "season_check_incomplete": f"{subject}存在整季候选，但文件列表或逐集覆盖尚未核验完成，因此没有返回磁力链接。",
        "release_unqualified": release_unqualified,
        "no_rss_candidates": f"{subject}没有检索到 Nyaa 原始候选。",
        "no_nyaa_release_for_target": f"{subject}没有检索到目标正篇发布。",
        "subtitle_unqualified": f"{subject}的画质合格候选均未确认带有中文字幕。",
        "subtitle_check_incomplete": f"{subject}的中文字幕检查尚未完成，因此没有返回磁力链接。",
        "latest_unresolved": f"{subject}目前无法可靠确认最新正篇。",
        "network_error": f"{subject}检索时网络请求失败，请稍后重试。",
        "output_incomplete": f"{subject}的结果缺少必要字段，因此没有输出不完整的资源信息。",
    }
    return messages.get(status, status)


def render_quality_fallback_question(
    display_title: str,
    season: str | None,
    episode: int | None,
    candidate: dict[str, Any],
) -> str:
    season_label = canonical_season(season) or "S01"
    episode_label = f" {season_label}E{episode:02d}" if episode is not None else ""
    subtitle = candidate.get("subtitle_signal") or "中文字幕已确认"
    return "\n".join(
        [
            f"《{display_title}》{episode_label} 的普通观看档没有同时满足画质和中文字幕要求的资源。",
            "轻量观看档找到了这个候选：",
            str(candidate.get("title") or ""),
            f"{candidate.get('size')} | {candidate.get('seeders')} 做种 | {subtitle}",
            "是否降级到轻量观看？",
        ]
    )


def bridge_to_tracked_show(
    state: dict[str, Any], resolved: ResolvedAnime
) -> dict[str, Any] | None:
    show = find_show_by_identity(state, resolved.bangumi_id, resolved.anilist_id)
    if show is not None:
        return show
    for name in unique([resolved.title, *resolved.aliases, *resolved.search_titles]):
        show = find_show(state, name)
        if show is not None:
            return show
    return None


def input_kind_for(query: str, nickname_alias: dict[str, Any] | None, state_show: dict[str, Any] | None) -> str:
    if nickname_alias:
        return "nickname"
    if state_show and norm(query) != norm(str(state_show.get("title") or "")):
        return "alias"
    return "full_title"


def resolver_failure(source: str, resolved: ResolvedAnime | None) -> str:
    detail = resolved.source if resolved and resolved.source else "no result"
    return f"{source}: {detail}"[:400]


def resolve_work_identity(
    args: argparse.Namespace,
    state: dict[str, Any],
    today: date,
) -> IdentityResolution:
    nickname_alias = lookup_nickname_alias(args.title)
    resolver_query = nickname_alias["canonical_title"] if nickname_alias else args.title
    state_show = find_show(state, args.title)
    if state_show is None and resolver_query != args.title:
        state_show = find_show(state, resolver_query)
    tracked = bool(state_show)
    sources: list[str] = []
    failures: list[str] = []
    ambiguous: ResolvedAnime | None = None

    if state_show:
        resolved = resolved_from_state(state_show, args.title)
        sources.append("state")
    else:
        resolved = ResolvedAnime(
            title=resolver_query,
            aliases=[args.title] if resolver_query != args.title else [],
            source="nickname_alias" if nickname_alias else "input",
        )
        if nickname_alias:
            resolved.aliases = unique([*resolved.aliases, *nickname_alias.get("aliases", [])])
            sources.append("nickname_registry")

    manual_search_titles = latin_search_titles(args.search_title or [])
    resolved.search_titles = unique(
        [
            *manual_search_titles,
            *resolved.search_titles,
            *latin_search_titles([resolved.title, *resolved.aliases]),
        ]
    )
    if manual_search_titles:
        sources.append("web")

    # A complete tracked record is the fast path. Airing metadata can still be
    # refreshed later for --latest without repeating title resolution here.
    if state_show and resolved.search_titles:
        return IdentityResolution(
            "resolved",
            resolved,
            state_show,
            True,
            input_kind_for(args.title, nickname_alias, state_show),
            unique(sources),
            failures,
            "state_hit",
        )
    if args.no_web_resolve:
        status = "resolved" if resolved.search_titles else "needs_web_resolution"
        return IdentityResolution(
            status,
            resolved,
            state_show,
            tracked,
            input_kind_for(args.title, nickname_alias, state_show),
            unique(sources),
            failures,
            "no_web_resolve",
        )

    bangumi_attempted = False
    bangumi_resolved = False
    should_try_bangumi_first = contains_cjk(args.title) or bool(state_show) or not resolved.search_titles
    if should_try_bangumi_first:
        bangumi_attempted = True
        for query in unique([args.title, resolver_query, resolved.title])[:2]:
            status, fresh = resolve_bangumi_title(query, args.timeout, today)
            if status == "resolved" and fresh:
                resolved = merge_resolved(resolved, fresh)
                sources.append("bangumi")
                bangumi_resolved = True
                break
            if status == "ambiguous" and fresh:
                ambiguous = fresh
            else:
                failures.append(resolver_failure("bangumi", fresh))

    anilist_queries = unique(
        [
            *resolved.search_titles,
            resolver_query,
            resolved.title,
            *resolved.aliases,
        ]
    )
    should_try_anilist = not state_show or not resolved.search_titles or bangumi_resolved
    if should_try_anilist:
        for query in anilist_queries[:2]:
            status, fresh = resolve_title(query, args.timeout, today)
            if status == "resolved" and fresh:
                resolved = merge_resolved(resolved, fresh)
                sources.append("anilist")
                break
            if status == "ambiguous" and fresh:
                ambiguous = ambiguous or fresh
            else:
                failures.append(resolver_failure("anilist", fresh))

    if not bangumi_attempted and not resolved.search_titles:
        for query in unique([args.title, resolver_query])[:2]:
            status, fresh = resolve_bangumi_title(query, args.timeout, today)
            if status == "resolved" and fresh:
                resolved = merge_resolved(resolved, fresh)
                sources.append("bangumi")
                break
            if status == "ambiguous" and fresh:
                ambiguous = ambiguous or fresh
            else:
                failures.append(resolver_failure("bangumi", fresh))

    resolved.search_titles = unique(
        [
            *manual_search_titles,
            *resolved.search_titles,
            *latin_search_titles([resolved.title, *resolved.aliases]),
        ]
    )
    if state_show is None:
        bridged = bridge_to_tracked_show(state, resolved)
        if bridged is not None:
            state_show = bridged
            tracked = True
            resolved = merge_resolved(resolved_from_state(bridged, args.title), resolved)
            sources.insert(0, "state")

    input_kind = input_kind_for(args.title, nickname_alias, state_show)
    if resolved.search_titles:
        resolver = "+".join(unique(sources)) or "resolved"
        return IdentityResolution(
            "resolved", resolved, state_show, tracked, input_kind, unique(sources), failures, resolver
        )
    if ambiguous is not None:
        return IdentityResolution(
            "ambiguous", ambiguous, state_show, tracked, input_kind, unique(sources), failures, "ambiguous"
        )
    return IdentityResolution(
        "needs_web_resolution",
        resolved,
        state_show,
        tracked,
        input_kind,
        unique(sources),
        failures,
        "needs_web_resolution",
    )


def identity_report_fields(
    identity: IdentityResolution,
    season: str | None,
    search_titles: list[str] | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    resolved = identity.resolved
    return {
        "identity_status": status_override or identity.status,
        "input_kind": identity.input_kind,
        "work_identity": {
            "bangumi_id": resolved.bangumi_id,
            "anilist_id": resolved.anilist_id,
            "format": resolved.format,
            "season": season or resolved.season,
        },
        "search_titles": search_titles if search_titles is not None else resolved.search_titles,
        "identity_sources": identity.sources,
        "resolver_failures": identity.failures,
    }


def child_argv_from_args(args: argparse.Namespace, title: str) -> list[str]:
    child = [
        title,
        "--state",
        str(args.state),
        "--tier",
        args.tier,
        "--timeout",
        str(args.timeout),
        "--limit",
        str(args.limit),
        "--query-limit",
        str(args.query_limit),
        "--cache",
        str(args.cache),
        "--schedule-cache",
        str(args.schedule_cache),
        "--json",
        "--no-auto-batch",
    ]
    valued = (
        ("--season", args.season),
        ("--episode", args.episode),
        ("--min-gib-per-episode", args.min_gib_per_episode),
        ("--max-gib-per-episode", args.max_gib_per_episode),
    )
    for option, value in valued:
        if value is not None:
            child.extend([option, str(value)])
    for search_title in args.search_title or []:
        child.extend(["--search-title", search_title])
    for group_hint in args.release_group_hint or []:
        child.extend(["--release-group-hint", group_hint])
    flags = (
        ("--refresh-cache", args.refresh_cache),
        ("--include-magnet", args.include_magnet),
        ("--include-page-link", args.include_page_link),
        ("--legal-ok", args.legal_ok),
        ("--no-web-resolve", args.no_web_resolve),
        ("--no-state-update", args.no_state_update),
        ("--mark-finished", args.mark_finished),
        ("--latest", args.latest),
        ("--whole-season", args.whole_season),
        ("--include-specials", args.include_specials),
        ("--explain", args.explain),
        ("--want-zh", args.want_zh),
        ("--require-zh", args.require_zh),
        ("--airing-priority", args.airing_priority),
    )
    child.extend(option for option, enabled in flags if enabled)
    return child


def render_batch_child_status(display_title: str, result: dict[str, Any]) -> str:
    target = result.get("target_episode")
    season = canonical_season(result.get("season")) or "S01"
    episode_label = f" {season}E{int(target):02d}" if isinstance(target, int) else ""
    status = result.get("status")
    messages = {
        "not_aired_yet": "尚未播出。",
        "no_rss_candidates": "没有检索到 Nyaa 发布。",
        "no_nyaa_release_for_target": "没有匹配目标集数的 Nyaa 发布。",
        "release_unqualified": "已有发布，但没有符合当前画质档位的资源。",
        "subtitle_unqualified": "已有发布，但没有经详细页确认的简体或繁体中文字幕资源。",
        "subtitle_check_incomplete": "中文字幕详情检查未完成，不能断言没有合格资源。",
        "needs_quality_fallback_confirmation": "轻量观看有中文字幕候选，需要确认是否降级。",
        "needs_web_resolution": "需要网页补全可靠的英文或罗马字检索名。",
        "needs_confirmation": "候选身份存在歧义，需要确认。",
        "latest_unresolved": "无法可靠确认官方最新正篇。",
        "output_incomplete": "结果缺少必需输出字段，未作为成功结果返回。",
    }
    return f"《{display_title}》{episode_label} {messages.get(status, str(status))}"


def run_tracked_title_batch(args: argparse.Namespace, mentions: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for mention in mentions:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return_code = main(child_argv_from_args(args, mention["title"]))
        try:
            result = json.loads(output.getvalue())
        except json.JSONDecodeError:
            result = {
                "status": "batch_child_error",
                "resolved_title": mention["title"],
                "search_return_code": return_code,
                "search_stderr": output.getvalue()[-600:],
            }
        if not result.get("reply_text"):
            result["reply_text"] = render_batch_child_status(mention["title"], result)
        results.append(result)
    reply_text = "\n\n".join(result["reply_text"] for result in results)
    rendered_count = sum(bool(result.get("reply_text")) for result in results)
    return {
        "status": "batch",
        "titles": [mention["title"] for mention in mentions],
        "results": results,
        "reply_text": reply_text,
        "output_contract": {
            "ready": rendered_count == len(results) and all(
                result.get("status") not in {"found", "finished_deleted", "latest_unresolved"}
                or result.get("output_contract", {}).get("ready", False)
                for result in results
            ),
            "result_count": len(results),
            "rendered_count": rendered_count,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--tier", default="browse", choices=["browse", "watch", "premium"])
    parser.add_argument("--season")
    parser.add_argument("--episode", type=int)
    parser.add_argument("--min-gib-per-episode", type=float)
    parser.add_argument("--max-gib-per-episode", type=float)
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--query-limit", type=int, default=2, help="Maximum high-value Nyaa title queries.")
    parser.add_argument(
        "--search-title",
        action="append",
        help="Verified English/romaji Nyaa title supplied by the bounded web-resolution fallback.",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--schedule-cache", type=Path, default=DEFAULT_SCHEDULE_CACHE)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--include-magnet", "--include-magnets", dest="include_magnet", action="store_true")
    parser.add_argument("--include-page-link", action="store_true")
    parser.add_argument("--legal-ok", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-web-resolve", action="store_true")
    parser.add_argument("--no-state-update", action="store_true")
    parser.add_argument("--mark-finished", action="store_true")
    parser.add_argument("--latest", action="store_true", help="Find the latest regular episode using airing metadata.")
    parser.add_argument(
        "--whole-season",
        action="store_true",
        help="Find one verified package covering the complete target season.",
    )
    parser.add_argument("--include-specials", action="store_true", help="Select a special/OVA after explicit user confirmation.")
    parser.add_argument("--explain", action="store_true", help="Include compact staged diagnostics in the JSON report.")
    parser.add_argument("--want-zh", action="store_true")
    parser.add_argument(
        "--require-zh",
        action="store_true",
        help="Require Simplified or Traditional Chinese subtitles verified from the Nyaa detail page.",
    )
    parser.add_argument(
        "--release-group-hint",
        action="append",
        default=[],
        help="Preferred release-group clue for a strict subtitle search; repeatable.",
    )
    parser.add_argument("--airing-priority", action="store_true")
    parser.add_argument("--no-auto-batch", action="store_true", help=argparse.SUPPRESS)
    return parser


def status_return_code(status: str) -> int | None:
    return {
        "found": 0,
        "finished_deleted": 0,
        "network_error": 1,
        "release_unqualified": 3,
        "subtitle_unqualified": 3,
        "subtitle_check_incomplete": 3,
        "season_check_incomplete": 3,
        "no_complete_season_release": 4,
        "no_nyaa_release_for_target": 4,
        "output_incomplete": 5,
    }.get(status)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.require_zh:
        args.want_zh = True
        args.include_page_link = True
    if args.include_magnet and not args.legal_ok:
        print("Refusing to print magnet links without --legal-ok.", file=sys.stderr)
        return 2
    state = load_state(args.state)
    state_repairs = sanitize_state_aliases(state)
    if state_repairs and not args.no_state_update:
        save_state(args.state, state)
    mentions = detect_tracked_titles(state, args.title)
    if len(mentions) >= 2 and not args.no_auto_batch and not args.search_title:
        report = run_tracked_title_batch(args, mentions)
        report["state_repairs"] = state_repairs
        if args.json:
            emit_json(report)
        else:
            print(report["reply_text"] or "batch")
        return 0
    requested_tier = args.tier
    explicit_min_gib = args.min_gib_per_episode
    explicit_max_gib = args.max_gib_per_episode
    if (
        explicit_min_gib is not None
        and explicit_max_gib is not None
        and explicit_max_gib < explicit_min_gib
    ):
        print("--max-gib-per-episode must be greater than or equal to --min-gib-per-episode.", file=sys.stderr)
        return 2
    args.size_policy_source = (
        "explicit" if explicit_min_gib is not None or explicit_max_gib is not None else "tier"
    )
    if args.size_policy_source == "tier":
        args.min_gib_per_episode = DEFAULT_TIER_MIN_GIB[args.tier]

    identity = resolve_work_identity(args, state, date.today())
    resolved = identity.resolved
    state_show = identity.state_show
    resolver_status = identity.resolver
    tracked = identity.tracked
    state_update = "none"
    schedule_cache_status = "not_used"
    season = canonical_season(args.season or resolved.season or (state_show or {}).get("season"))
    state_aliases = unique([*resolved.aliases, args.title])
    search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)

    if args.mark_finished:
        if not args.no_state_update:
            deleted = delete_show(state, [args.title, resolved.title, *resolved.aliases])
            if deleted:
                save_state(args.state, state)
                state_update = "deleted_finished"
        report = {
            "status": "finished_deleted" if state_update == "deleted_finished" else "finished_not_tracked",
            "resolved_title": resolved.title,
            "aliases": search_names,
            "season": season,
            "target_episode": args.episode,
            "tracked": bool(state_show),
            "selected": None,
            "state_update": state_update,
            "resolver": resolver_status,
            "search_return_code": None,
            "search_stderr": "",
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print("Finished state removed.")
        return 0

    if identity.status in {"ambiguous", "needs_web_resolution"}:
        report = {
            "status": identity.status,
            "resolved_title": resolved.title,
            "aliases": resolved.aliases,
            "season": season,
            "target_episode": args.episode or ((state_show or {}).get("next_episode")),
            "tracked": tracked,
            "selected": None,
            "state_update": "none",
            "choices": resolved.choices if identity.status == "ambiguous" else [],
            "diagnostic": {
                "search_skipped": "identity_incomplete",
                "suggested_queries": [f"{args.title} anime", f"{args.title} English title"],
            },
            "resolver": resolver_status,
            "search_return_code": None,
            "search_stderr": " | ".join(identity.failures)[:600],
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print(identity.status)
        return 0

    target_episode = args.episode
    intent: SearchIntent
    availability: dict[str, Any] = {"target_source": "input", "official_target": False}
    not_aired_yet = False
    if target_episode is not None:
        intent = SearchIntent.SPECIFIC_EPISODE
    elif args.latest:
        intent = SearchIntent.LATEST_REGULAR
        if not args.no_web_resolve:
            resolved, schedule_cache_status = hydrate_airing_metadata(
                resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today()
            )
            identity.resolved = resolved
            state_aliases = unique([*resolved.aliases, args.title])
            search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)
        target_episode, target_source = latest_regular_target(resolved, state_show)
        availability = {
            "target_source": target_source,
            "official_target": target_source.startswith("anilist"),
            "target_episode": target_episode,
        }
        not_aired_yet = target_source == "not_aired_yet"
    elif args.whole_season or (
        args.season is not None
        and state_show is None
        and resolved.format in MAINLINE_FORMATS
        and (resolved.status == "FINISHED" or not resolved.trackable)
    ):
        intent = SearchIntent.SEASON_BATCH
        availability = {
            "target_source": "whole_season",
            "official_target": bool(resolved.episodes),
            "expected_episodes": resolved.episodes,
        }
    elif state_show and isinstance(state_show.get("next_episode"), int):
        target_episode = state_show["next_episode"]
        intent = SearchIntent.NEXT_TRACKED
        if not args.no_web_resolve:
            resolved, schedule_cache_status = hydrate_airing_metadata(
                resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today()
            )
            identity.resolved = resolved
            state_aliases = unique([*resolved.aliases, args.title])
            search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)
            official_latest, official_source = latest_regular_target(resolved, state_show)
            availability = {
                "target_source": "tracked_next_episode",
                "official_latest_source": official_source,
                "official_latest_episode": official_latest,
                "official_target": official_source.startswith("anilist"),
            }
            not_aired_yet = bool(
                official_source == "not_aired_yet"
                or (
                    availability["official_target"]
                    and official_latest is not None
                    and target_episode > official_latest
                )
            )
        else:
            availability = {"target_source": "tracked_next_episode", "official_target": False}
    else:
        intent = SearchIntent.SEASON_BROWSE

    if not_aired_yet:
        report = {
            "status": "not_aired_yet",
            "intent": intent.value,
            "resolved_title": resolved.title,
            "aliases": search_names,
            "season": season,
            "target_episode": target_episode,
            "availability": availability,
            "quality": {"requested_tier": requested_tier, "fallback": None},
            "tracked": tracked,
            "selected": None,
            "choices": [],
            "diagnostic": {"raw_count": 0, "search_skipped": "official_schedule"},
            "state_update": "none",
            "resolver": resolver_status,
            "cache": {"rss": "not_used", "schedule": schedule_cache_status},
            "search_return_code": None,
            "search_stderr": "",
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print("not_aired_yet")
        return 0

    base_search_names = list(search_names)
    release_search_names = (
        strict_zh_search_names(
            base_search_names,
            args.title,
            target_episode,
            args.release_group_hint,
            state_aliases,
        )
        if args.require_zh
        else base_search_names
    )
    search_args = build_search_args(
        release_search_names[0],
        release_search_names[1:],
        args,
        season,
        target_episode,
        resolved.duration_min,
    )
    if intent is SearchIntent.SEASON_BATCH:
        search_args.episodes = resolved.episodes
    search_context = SearchContext(
        canonical_title=resolved.title,
        aliases=tuple(state_aliases),
        search_titles=tuple(base_search_names),
        related_titles=tuple(resolved.related_titles),
        mainline_scope=resolved.mainline_scope,
        resolved_season=normalize_season_number(season or resolved.season),
        expected_episodes=resolved.episodes,
        flexible_title_match=args.require_zh,
    )
    core_report = search_release_report(
        search_args,
        intent=intent,
        requested_episode=target_episode,
        include_specials=args.include_specials,
        cache_path=args.cache,
        refresh_cache=args.refresh_cache,
        context=search_context,
    )
    primary_report = core_report
    quality_fallback: dict[str, Any] | None = None
    fallback_report_for_diagnostic = None
    fallback_confirmation_item = None
    fallback_tier = {"watch": "browse", "premium": "watch"}.get(requested_tier)
    if (
        fallback_tier is not None
        and args.size_policy_source == "tier"
        and (
            core_report.status == "release_unqualified"
            or (args.require_zh and core_report.status == "subtitle_unqualified")
        )
    ):
        fallback_args = argparse.Namespace(**vars(args))
        fallback_args.tier = fallback_tier
        fallback_args.min_gib_per_episode = DEFAULT_TIER_MIN_GIB[fallback_tier]
        fallback_args.max_gib_per_episode = None
        fallback_args.size_policy_source = "tier"
        fallback_search_args = build_search_args(
            release_search_names[0],
            release_search_names[1:],
            fallback_args,
            season,
            target_episode,
            resolved.duration_min,
        )
        if intent is SearchIntent.SEASON_BATCH:
            fallback_search_args.episodes = resolved.episodes
        fallback_report = search_release_report(
            fallback_search_args,
            intent=intent,
            requested_episode=target_episode,
            include_specials=args.include_specials,
            cache_path=args.cache,
            refresh_cache=args.refresh_cache,
            context=search_context,
        )
        quality_fallback = {
            "from": requested_tier,
            "to": fallback_tier,
            "status": fallback_report.status,
        }
        fallback_report_for_diagnostic = fallback_report
        if fallback_report.status == "found":
            if args.require_zh and requested_tier == "watch" and fallback_tier == "browse":
                fallback_confirmation_item = fallback_report.selected[0]
                quality_fallback["requires_confirmation"] = True
            else:
                core_report = fallback_report
        elif args.require_zh and fallback_report.status in {
            "subtitle_unqualified",
            "subtitle_check_incomplete",
        }:
            core_report = fallback_report
    selected_item = core_report.selected[0] if core_report.selected else None
    selected = asdict(selected_item.candidate) if selected_item else None
    if selected_item and selected is not None:
        selected.update(
            {
                "effective_season": selected_item.effective_season,
                "season_source": selected_item.season_source,
                "work_match": selected_item.work_match,
                "coverage": selected_item.coverage.as_dict() if selected_item.coverage else None,
            }
        )
        if args.explain and selected_item.work_match_evidence is not None:
            selected["work_match_evidence"] = selected_item.work_match_evidence.as_dict()
        matched_base_queries = [
            query
            for query in selected_item.candidate.matched_queries
            if norm(query) in {norm(name) for name in base_search_names}
        ]
        resolved.search_titles = promote_search_titles(
            unique([*resolved.search_titles, *base_search_names]),
            matched_base_queries,
        )
        resolved.verified_search_titles = unique(
            [*resolved.verified_search_titles, *latin_search_titles(matched_base_queries)]
        )
        identity.resolved = resolved
    status = core_report.status
    fallback_selected = None
    if fallback_confirmation_item is not None:
        fallback_selected = asdict(fallback_confirmation_item.candidate)
        fallback_selected.update(
            {
                "effective_season": fallback_confirmation_item.effective_season,
                "season_source": fallback_confirmation_item.season_source,
                "work_match": fallback_confirmation_item.work_match,
                "coverage": (
                    fallback_confirmation_item.coverage.as_dict()
                    if fallback_confirmation_item.coverage
                    else None
                ),
            }
        )
        if args.explain and fallback_confirmation_item.work_match_evidence is not None:
            fallback_selected["work_match_evidence"] = (
                fallback_confirmation_item.work_match_evidence.as_dict()
            )
        status = "needs_quality_fallback_confirmation"
    needs_title_discovery = bool(
        status == "no_rss_candidates"
        and not args.search_title
        and not set(map(norm, search_names)) & set(map(norm, resolved.verified_search_titles))
    )
    if needs_title_discovery:
        status = "needs_web_resolution"
    if (
        intent is SearchIntent.LATEST_REGULAR
        and not availability["official_target"]
        and status == "found"
    ):
        status = "latest_unresolved"
    output_contract = result_output_contract(selected, args.include_magnet, args.require_zh)
    if intent is SearchIntent.SEASON_BATCH:
        coverage = (selected or {}).get("coverage") or {}
        for field_name in ("coverage.complete", "coverage.quality_fit"):
            output_contract["required_fields"].append(field_name)
        if coverage.get("complete") is not True:
            output_contract["missing_fields"].append("coverage.complete")
        if coverage.get("quality_fit") is not True:
            output_contract["missing_fields"].append("coverage.quality_fit")
        output_contract["ready"] = not output_contract["missing_fields"]
    if status == "needs_quality_fallback_confirmation":
        fallback_ready = bool(
            fallback_selected
            and fallback_selected.get("title")
            and fallback_selected.get("size")
            and fallback_selected.get("seeders") is not None
            and fallback_selected.get("detail_chinese_confirmed") is True
        )
        output_contract = {
            "ready": fallback_ready,
            "magnet_requested": args.include_magnet,
            "magnet_deferred_until_confirmation": True,
            "required_fields": [
                "fallback_candidate.title",
                "fallback_candidate.size",
                "fallback_candidate.seeders",
                "fallback_candidate.detail_chinese_confirmed",
            ],
            "missing_fields": [] if fallback_ready else ["fallback_candidate"],
        }
    if status in {"found", "latest_unresolved"} and not output_contract["ready"]:
        status = "output_incomplete"

    found_episode: int | None = None
    if (
        selected_item
        and selected_item.identity.kind is EpisodeKind.REGULAR
        and selected_item.identity.episode is not None
        and selected_item.identity.episode == selected_item.identity.episode.to_integral_value()
    ):
        found_episode = int(selected_item.identity.episode)

    if status == "found" and found_episode is not None:
        if not args.no_state_update and (resolved.trackable or tracked):
            if is_final_episode(resolved, found_episode):
                delete_show(state, [args.title, resolved.title, *resolved.aliases])
                state_update = "deleted_final_episode"
                status = "finished_deleted"
            else:
                upsert_show(
                    state,
                    resolved.title,
                    state_aliases,
                    season or "S01",
                    found_episode,
                    found_episode + 1,
                    f"Found regular episode {found_episode}; next default is episode {found_episode + 1}.",
                    resolved,
                    "airing",
                    show_hint=state_show,
                )
                state_update = "advanced"
                tracked = True
            save_state(args.state, state)
    elif (
        status
        in {
            "no_nyaa_release_for_target",
            "release_unqualified",
            "subtitle_unqualified",
            "subtitle_check_incomplete",
            "latest_unresolved",
            "needs_confirmation",
            "needs_quality_fallback_confirmation",
            "needs_web_resolution",
        }
        and not args.no_state_update
        and resolved.trackable
    ):
        upsert_show(
            state,
            resolved.title,
            state_aliases,
            season or resolved.season or "S01",
            None,
            target_episode,
            f"Current-season target has status: {status}.",
            resolved,
            "waiting",
            show_hint=state_show,
        )
        save_state(args.state, state)
        state_update = "tracked_waiting"
        tracked = True

    diagnostic = dict(core_report.diagnostics)
    if args.require_zh:
        diagnostic["strict_zh"] = {
            "enabled": True,
            "accepts": ["simplified_chinese", "traditional_chinese"],
            "queries": release_search_names,
            "release_group_hints": args.release_group_hint,
            "detail_page_required": True,
        }
    if status == "output_incomplete":
        diagnostic["output_error"] = {
            "missing_fields": output_contract["missing_fields"],
            "magnet_requested": args.include_magnet,
        }
    if needs_title_discovery:
        diagnostic["provisional_status"] = core_report.status
        diagnostic["web_resolution_reason"] = "unverified_search_titles_exhausted"
        diagnostic["suggested_queries"] = [
            f"{args.title} anime English title",
            f"{resolved.title} Nyaa",
        ]
    if quality_fallback is not None and fallback_report_for_diagnostic is not None:
        diagnostic["quality_stages"] = {
            requested_tier: primary_report.diagnostics,
            str((quality_fallback or {}).get("to") or "fallback"): fallback_report_for_diagnostic.diagnostics,
        }

    public_selected = selected_view(selected, args.include_page_link, args.require_zh)
    public_fallback_selected = selected_view(fallback_selected, True, True)
    if public_fallback_selected is not None:
        public_fallback_selected.pop("magnet", None)
    display_title = str((state_show or {}).get("title") or args.title)
    reply_text = ""
    if status in {"found", "finished_deleted", "latest_unresolved"} and public_selected and output_contract["ready"]:
        if intent is SearchIntent.SEASON_BATCH:
            reply_text = render_season_batch_reply(
                display_title,
                season,
                public_selected,
                args.include_magnet,
            )
        else:
            reply_text = render_result_reply(
                display_title,
                season,
                target_episode,
                public_selected,
                args.include_magnet,
            )
    elif (
        status == "needs_quality_fallback_confirmation"
        and public_fallback_selected
        and output_contract["ready"]
    ):
        reply_text = render_quality_fallback_question(
            display_title,
            season,
            target_episode,
            public_fallback_selected,
        )
    elif not reply_text:
        effective_tier = str((quality_fallback or {}).get("to") or requested_tier)
        reply_text = render_failure_reply(
            status,
            display_title,
            season,
            intent,
            effective_tier,
            diagnostic,
        )
    report = {
        "status": status,
        "intent": intent.value,
        "resolved_title": resolved.title,
        "aliases": search_names,
        "season": season,
        "target_episode": target_episode,
        "availability": availability,
        "quality": {
            "requested_tier": requested_tier,
            "effective_tier": str((quality_fallback or {}).get("to") or requested_tier),
            "policy": primary_report.diagnostics.get("size_policy"),
            "effective_policy": core_report.diagnostics.get("size_policy"),
            "fallback": quality_fallback,
            "fallback_candidate": public_fallback_selected,
        },
        "tracked": tracked,
        "selected": public_selected,
        "choices": [
            choice.as_dict(args.explain, args.explain)
            for choice in core_report.choices
        ],
        "diagnostic": diagnostic,
        "state_update": state_update,
        "resolver": resolver_status,
        "cache": {"rss": core_report.cache, "schedule": schedule_cache_status},
        "search_return_code": status_return_code(status),
        "search_stderr": " | ".join(core_report.failures)[:600],
        "output_contract": output_contract,
        "reply_text": reply_text,
        "state_repairs": state_repairs,
        **identity_report_fields(
            identity,
            season,
            search_names,
            "needs_web_resolution" if needs_title_discovery else "resolved",
        ),
    }

    if args.json:
        emit_json(report)
    elif reply_text:
        print(reply_text)
    elif selected:
        print(f"{selected.get('title')}\nSize: {selected.get('size')} | Seeds: {selected.get('seeders')}")
        if selected.get("magnet"):
            print(f"Magnet: {selected.get('magnet')}")
    elif status == "needs_confirmation":
        print("Regular episode and special candidates need user confirmation.")
    else:
        print(status)
    return status_return_code(status) or 0


if __name__ == "__main__":
    raise SystemExit(main())
