"""Extracted policy module: providers."""

from __future__ import annotations
from .settings import ANILIST_API, BANGUMI_SEARCH_API, MAINLINE_FORMATS, MAINLINE_RELATION_TYPES

import copy
import json
import re
import urllib.error
import urllib.request
from .transport import request_json
from dataclasses import field
from datetime import date
from typing import Any

from release_identity import normalize_season_number, parse_release_identity


import completion as completion_policy


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
          endDate { year month day }
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
                status
                episodes
                startDate { year month day }
                nextAiringEpisode { episode airingAt }
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
    return request_json(request, timeout)


def anilist_media_request(media_id: int, timeout: int) -> dict[str, Any]:
    gql = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        id
        format
        status
        season
        seasonYear
        endDate { year month day }
        startDate { year month day }
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
              status
              episodes
              startDate { year month day }
              nextAiringEpisode { episode airingAt }
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
    return request_json(request, timeout)


def anilist_air_date_request(media_id: int, episode: int, timeout: int) -> dict[str, Any]:
    gql = """
    query ($mediaId: Int, $episode: Int) {
      Media(id: $mediaId, type: ANIME) {
        id
        format
        status
        startDate { year month day }
        title { romaji english native }
        synonyms
      }
      AiringSchedule(mediaId: $mediaId, episode: $episode) {
        mediaId
        episode
        airingAt
      }
    }
    """
    payload = json.dumps(
        {
            "query": gql,
            "variables": {"mediaId": media_id, "episode": episode},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ANILIST_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CodexAnimeFinder/1.0"},
        method="POST",
    )
    return request_json(request, timeout)


def bangumi_request(query: str, timeout: int) -> dict[str, Any]:
    payload = json.dumps({"keyword": query, "filter": {"type": [2]}}).encode("utf-8")
    request = urllib.request.Request(
        BANGUMI_SEARCH_API,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "CodexAnimeFinder/1.0"},
        method="POST",
    )
    return request_json(request, timeout)


def bangumi_infobox_values(item: dict[str, Any], keys: set[str]) -> list[str]:
    from .queries import unique
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
    from .queries import unique
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
    from .evidence import from_raw
    from .legacy_models import ResolvedAnime
    from .queries import latin_search_titles
    from .queries import norm
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
        aliases=[name for name in names if norm(name) != norm(title)],
        metadata_titles=names,
        search_titles=search_titles,
        season=infer_season(names),
        current=current,
        trackable=bool(current and anime_format in MAINLINE_FORMATS),
        source="bangumi",
        format=anime_format,
        status="RELEASING" if current else None,
        episodes=episodes,
        bangumi_id=item.get("id"),
        evidence=(from_raw('bangumi', item),),
    )
    return resolved, score


def _requested_installment(provider, items, season):
    if not season:
        return items
    from .evidence import from_raw
    from .models import WorkflowError
    expected = canonical_season(season)
    kept = []
    for item in items:
        try:
            evidence = from_raw(provider, item)
        except WorkflowError:
            continue
        if (evidence.season == expected or expected == 'S01' and evidence.season is None) and evidence.format in {'TV', 'TV_SHORT', 'ONA'}:
            kept.append(item)
    return kept


def resolve_bangumi_title(query: str, timeout: int, today: date, *, season=None) -> tuple[str, ResolvedAnime | None]:
    from .legacy_models import ResolvedAnime
    from .queries import norm
    try:
        data = bangumi_request(query, timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "resolver_failed", ResolvedAnime(title=query, source=f"bangumi error: {exc}",
            stage_errors=[exc.detail.as_dict()] if hasattr(exc, 'detail') else [])
    items = [item for item in data.get("data", []) if isinstance(item, dict)]
    items = _requested_installment('bangumi', items, season)
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
    from .legacy_models import ResolvedAnime
    completion = copy.deepcopy(show.get('completion', {}))
    # Historical active metadata is not proof of completion after v1 adaptation.
    # Retained completed records are delivery history and remain network-free.
    pending = show.get('binding_evidence', {})
    if show.get('status') != 'completed' and completion.get('source_kind') == 'metadata' and not any(
        b.get('status') == 'verified' for b in pending.values()
    ):
        completion['confirmed'] = False
    return ResolvedAnime(
        title=show.get("title") or fallback_title,
        aliases=show.get("aliases", []),
        search_titles=show.get("search_titles", []),
        verified_search_titles=show.get("verified_search_titles", []),
        season=show.get("season"),
        current=show.get("status") != "completed" and not completion.get("confirmed"),
        trackable=show.get("status") != "completed" and not completion.get("confirmed"),
        status="FINISHED" if show.get("status") == "completed" or completion.get("confirmed") else None,
        completion=completion,
        metadata_titles=list(show.get("metadata_titles", [])),
        source=source,
        format=show.get("format"),
        episodes=show.get("total_episodes"),
        duration_min=show.get("duration_min"),
        bangumi_id=show.get("bangumi_id"),
        anilist_id=show.get("anilist_id"),
        mainline_scope=show.get("mainline_scope", "unknown"),
        related_titles=show.get("related_titles", []),
        continuation_parts=show.get("continuation_parts", []),
    )


def name_score(query: str, names: list[str]) -> int:
    from .queries import norm
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
    from .queries import unique
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


def continuation_parts_from_media(media: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured, official mainline sequel evidence without guessing from titles alone."""
    relations = media.get("relations")
    edges = relations.get("edges") if isinstance(relations, dict) else None
    if not isinstance(edges, list):
        return []
    parts: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("relationType") != "SEQUEL":
            continue
        node = edge.get("node")
        if (
            not isinstance(node, dict)
            or node.get("type") != "ANIME"
            or node.get("format") not in MAINLINE_FORMATS
        ):
            continue
        title_data = node.get("title") or {}
        title = title_data.get("english") or title_data.get("romaji") or title_data.get("native")
        start = node.get("startDate") or {}
        try:
            start_date = date(
                int(start["year"]),
                int(start["month"]),
                int(start["day"]),
            ).isoformat()
        except (KeyError, TypeError, ValueError):
            start_date = None
        next_airing = node.get("nextAiringEpisode") or {}
        parts.append(
            {
                "anilist_id": node.get("id"),
                "title": title,
                "status": node.get("status"),
                "episodes": node.get("episodes"),
                "start_date": start_date,
                "next_airing_episode": next_airing.get("episode"),
                "next_airing_at": next_airing.get("airingAt"),
                "explicit_split_cour": bool(
                    title
                    and re.search(
                        r"(?:\bpart\s*(?:2|ii)\b|\b(?:2nd|second)\s+cour\b|\bcour\s*2\b|第[二2]クール)",
                        title,
                        re.I,
                    )
                ),
            }
        )
    return parts


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
    from .evidence import from_raw
    from .legacy_models import ResolvedAnime
    from .queries import contains_cjk
    from .queries import has_latin_search_text
    from .queries import norm
    from .queries import unique
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
    # Caller wording is a search request, never evidence about a returned work.
    names = official_names
    title = title_data.get("english") or title_data.get("romaji") or title_data.get("native") or query
    current_season, current_year = current_anime_season(today)
    anime_format = media.get("format")
    status = media.get("status")
    next_airing = media.get("nextAiringEpisode") or {}
    mainline_scope = mainline_scope_from_media(media)
    resolved_season = infer_season(names)
    if resolved_season is None and mainline_scope == "single" and anime_format in MAINLINE_FORMATS:
        resolved_season = "S01"
    is_current = bool(status != "FINISHED" and (
        status == "RELEASING"
        or (media.get("season") == current_season and media.get("seasonYear") == current_year)
    ))
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
            metadata_titles=official_names,
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
            continuation_parts=continuation_parts_from_media(media),
            completion=completion_policy.metadata(media),
            evidence=(from_raw('anilist', media),),
        ),
        score,
    )


def resolve_title(query: str, timeout: int, today: date, *, season=None) -> tuple[str, ResolvedAnime | None]:
    from .legacy_models import ResolvedAnime
    from .queries import norm
    try:
        data = anilist_request(query, timeout)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "resolver_failed", ResolvedAnime(title=query, source=f"anilist error: {exc}",
            stage_errors=[exc.detail.as_dict()] if hasattr(exc, 'detail') else [])

    media_items = [item for item in data.get("data", {}).get("Page", {}).get("media", []) if not item.get("isAdult")]
    media_items = _requested_installment('anilist', media_items, season)
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

