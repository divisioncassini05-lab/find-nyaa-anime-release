"""Extracted policy module: queries."""

from __future__ import annotations
from .settings import DEFAULT_NICKNAME_ALIASES

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from failure_recovery import recovery_plan
from chinese_search import chinese_search_variants


import completion as completion_policy

STRICT_ZH_ANCHOR_STOPWORDS = {'anime', 'season', 'movie', 'the', 'this', 'with'}


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
    from .trace import attach_trace
    attach_trace(report)
    report.setdefault("recovery", recovery_plan(report))
    report.setdefault("automation_cleanup", completion_policy.automation_cleanup(report))
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


def is_obviously_damaged_search_name(candidate: str, alternatives: list[str]) -> bool:
    """Reject metadata names whose leading title token is visibly truncated."""
    if "\ufffd" in candidate or not candidate.strip():
        return True
    candidate_tokens = re.findall(r"[a-z0-9]+", candidate.casefold())
    if len(candidate_tokens) < 2:
        return False
    for alternative in alternatives:
        if norm(alternative) == norm(candidate):
            continue
        alternative_tokens = re.findall(r"[a-z0-9]+", alternative.casefold())
        if len(alternative_tokens) < 2:
            continue
        same_tail_anchor = candidate_tokens[1] == alternative_tokens[1]
        leading_token_truncated = (
            len(alternative_tokens[0]) == len(candidate_tokens[0]) + 1
            and alternative_tokens[0].endswith(candidate_tokens[0])
        )
        if same_tail_anchor and leading_token_truncated:
            return True
    return False


def broad_search_name(name: str) -> str:
    """Derive a complete franchise/work anchor without a season or subtitle suffix."""
    original = name.strip()
    value = re.sub(
        r"\s+(?:season\s*\d+|\d+(?:st|nd|rd|th)\s+season)\s*$",
        "",
        original,
        flags=re.I,
    )
    delimiter = re.search(r"\s(?:-|~|～)\s|:\s+", value)
    if not delimiter:
        return original
    proposals = [value[: delimiter.start()].strip(), value]
    for proposal in proposals:
        proposal = re.sub(r"\s+[IVXLCDM]+\s*$", "", proposal, flags=re.I).strip(" -:~～")
        tokens = re.findall(r"[a-z0-9]+", proposal, re.I)
        compact_length = sum(len(token) for token in tokens)
        if len(tokens) >= 2 and compact_length >= 8:
            return proposal
        if len(tokens) == 1 and len(tokens[0]) >= 7:
            return proposal
    return original


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
    reliable_pool = [
        name for name in pool if not is_obviously_damaged_search_name(name, pool)
    ]
    if reliable_pool:
        pool = reliable_pool
        preferred_latin = [name for name in preferred_latin if name in pool]
    ranked = sorted(
        enumerate(pool),
        key=lambda item: (
            1000 - preferred_latin.index(item[1]) if item[1] in preferred_latin else search_name_score(item[1], title),
            -item[0],
        ),
        reverse=True,
    )
    primary_source = ranked[0][1]
    primary_query = broad_search_name(primary_source)
    limit = max(1, query_limit)
    selected: list[str] = []
    for _, name in ranked:
        if len(selected) >= limit:
            break
        if is_redundant_search_name(name, selected):
            continue
        selected.append(name)
    # This protected broad query is additive: metadata aliases keep their legacy
    # ordering/budget, while a subtitle/season suffix cannot consume every slot.
    if norm(primary_query) not in {norm(name) for name in selected}:
        selected.append(primary_query)
    return selected


def strict_zh_search_names(
    base_names: list[str],
    original_title: str,
    episode: int | None,
    release_group_hints: list[str] | None = None,
    cjk_aliases: list[str] | None = None,
) -> list[str]:
    """Add bounded release-search bridges only for explicit Chinese-subtitle requests."""
    expanded = list(base_names)
    expanded.extend(chinese_search_variants([original_title, *(cjk_aliases or [])]))

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

