"""Shared local-first lookup for probes and the high-level resolver."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from release_identity import parse_release_identity, normalize_season_number

NICKNAMES = Path(__file__).resolve().parent.parent / "references" / "anime_nickname_aliases.json"


def norm(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def without_season(value):
    return re.sub(r'第[零〇一二三四五六七八九十\d]+[季期]|\bseason\s*\d+\b|\b\d+(?:st|nd|rd|th)\s+season\b|\bS\d{1,2}\b',
                  '', value, flags=re.I).strip(' -:：')


def tracked_matches(data, query, season=None):
    """A bare franchise name prefers its sole active tracked installment.

    Explicit seasons remain explicit. Short names require registered evidence;
    two active matches remain ambiguous instead of falling through to web search.
    """
    queries = [query, without_season(query)]
    try:
        for entry in json.loads(NICKNAMES.read_text(encoding="utf-8"))["entries"]:
            names = [entry["canonical_title"], *entry.get("aliases", [])]
            if any(norm(q) in {norm(n) for n in names} for q in queries):
                queries.extend(names)
                break
    except (OSError, ValueError, KeyError, TypeError):
        pass
    explicit_season = normalize_season_number(season) if season else parse_release_identity(query).season
    matches = []
    for show in data.get("shows", []):
        if explicit_season is not None and normalize_season_number(show.get("season")) != explicit_season:
            continue
        names = [show.get("title", ""), *show.get("aliases", [])]
        normalized = {norm(n) for n in names if n}
        exact = any(norm(q) in normalized for q in queries if norm(q))
        partial = any(len(norm(q)) >= 4 and any(n and (norm(q) in n or n in norm(q)) for n in normalized)
                      for q in queries)
        if exact or partial:
            active = show.get("airing") is True and show.get("status") not in {"completed", "finished"}
            matches.append(((active if explicit_season is None else False), show))
    if not matches:
        return []
    best = max(rank for rank, _ in matches)
    return [show for rank, show in matches if rank == best]


def find_tracked_show(data, query, season=None):
    matches = tracked_matches(data, query, season)
    return matches[0] if len(matches) == 1 else None
