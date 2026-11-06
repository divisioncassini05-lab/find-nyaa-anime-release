"""Extracted policy module: legacy_state."""

from __future__ import annotations

import copy
from typing import Any

from airing_watch_state import pending_download
from tracked_identity import find_tracked_show


def names_for(show: dict[str, Any]) -> list[str]:
    from .queries import unique
    return unique([show.get("title"), *show.get("aliases", []), *show.get("search_titles", [])])


def find_show_by_identity(
    data: dict[str, Any], bangumi_id: int | None = None, anilist_id: int | None = None
) -> dict[str, Any] | None:
    return None  # Provider IDs are bindings, never local record identity.


def find_show(data: dict[str, Any], query: str) -> dict[str, Any] | None:
    return find_tracked_show(data, query)


def _name_position(text: str, name: str) -> int:
    from .queries import norm
    if not name or len(norm(name)) < 4:
        return -1
    return text.casefold().find(name.casefold())


def detect_tracked_titles(data: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """Find distinct tracked works explicitly mentioned inside one request."""
    from .queries import lookup_nickname_alias
    from .queries import norm
    if lookup_nickname_alias(text) or any(
        norm(text) == norm(name) for show in data.get("shows", []) for name in names_for(show)
    ):
        return []  # One shared name is not a request to fetch every season.
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
    watched_episode: int | None = None,
) -> dict[str, Any]:
    from .legacy_models import ResolvedAnime
    from .providers import canonical_season
    from .queries import norm
    from .queries import now_iso
    from .queries import unique
    show = show_hint if show_hint in data.get("shows", []) else None
    if resolved and resolved.identity_conflicts:
        raise ValueError("Cannot persist conflicting work/season metadata")
    if show is None:
        from .schema import new_track_id
        show = {"track_id": new_track_id(), "title": title, "aliases": [], "airing": True, "created_at": now_iso()}
        data["shows"].append(show)

    show["title"] = show.get("title") or title
    candidate_aliases = unique([*show.get("aliases", []), *aliases, title])
    show["aliases"] = [
        alias for alias in candidate_aliases if not alias_mentions_multiple_canonical_titles(data, alias)
    ]
    show["aliases"] = [alias for alias in show["aliases"] if norm(alias) != norm(show["title"])]
    if season:
        show["season"] = season
    if watched_episode is not None:
        current_watched = show.get("watched_episode")
        show["watched_episode"] = max(
            watched_episode,
            current_watched if isinstance(current_watched, int) else 0,
        )
        queued = pending_download(show)
        if queued is not None and queued["episode"] <= show["watched_episode"]:
            # Legacy deferred-download state must not survive the standard
            # success boundary, where a verified link/qBittorrent acceptance
            # already counts as handled progress.
            show.pop("pending_download", None)
    if latest_episode is not None:
        show["latest_known_episode"] = latest_episode
    if next_episode is not None:
        show["next_episode"] = next_episode
    if resolved and resolved.episodes:
        show["total_episodes"] = resolved.episodes
    if resolved and resolved.completion:
        show["completion"] = copy.deepcopy(resolved.completion)
    if resolved and resolved.metadata_titles:
        show["metadata_titles"] = list(resolved.metadata_titles)
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
    if resolved and resolved.continuation_parts:
        show["continuation_parts"] = resolved.continuation_parts
    if resolved and resolved.search_titles:
        show["search_titles"] = resolved.search_titles
    if resolved and resolved.verified_search_titles:
        show["verified_search_titles"] = resolved.verified_search_titles
    show["status"] = status
    show["airing"] = True
    show["notes"] = notes
    show["updated_at"] = now_iso()
    return show

