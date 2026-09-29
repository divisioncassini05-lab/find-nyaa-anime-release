"""Extracted policy module: identity."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from tracked_identity import tracked_matches


def bridge_to_tracked_show(
    state: dict[str, Any], resolved: ResolvedAnime
) -> dict[str, Any] | None:
    return None  # Discovery aliases are never local-record joins.


def input_kind_for(query: str, nickname_alias: dict[str, Any] | None, state_show: dict[str, Any] | None) -> str:
    from .queries import norm
    if nickname_alias:
        return "nickname"
    if state_show and norm(query) != norm(str(state_show.get("title") or "")):
        return "alias"
    return "full_title"


def resolver_failure(source: str, resolved: ResolvedAnime | None) -> str:
    from .legacy_models import ResolvedAnime
    detail = resolved.source if resolved and resolved.source else "no result"
    return f"{source}: {detail}"[:400]


def resolve_work_identity(
    args: argparse.Namespace,
    state: dict[str, Any],
    today: date,
) -> IdentityResolution:
    from .legacy_models import IdentityResolution
    from .legacy_models import ResolvedAnime
    from .queries import contains_cjk
    from .legacy_state import find_show
    from .queries import latin_search_titles
    from .queries import lookup_nickname_alias
    from .metadata import merge_resolved
    from .queries import norm
    from .metadata import read_schedule_snapshot
    from .providers import resolve_bangumi_title
    from .providers import resolve_title
    from .metadata import resolved_from_snapshot
    from .providers import resolved_from_state
    from .metadata import schedule_cache_key
    from .queries import unique
    from .metadata import write_schedule_snapshots
    from tracked_identity import without_season
    nickname_alias = lookup_nickname_alias(without_season(args.title))
    local_matches = tracked_matches(state, args.title, args.season)
    if len(local_matches) > 1:
        unresolved = ResolvedAnime(title=args.title, source="state",
            choices=[{"title": show["title"], "season": show.get("season"),
                      "anilist_id": show.get("anilist_id")} for show in local_matches])
        return IdentityResolution("ambiguous", unresolved, None, True, "alias", ["state"], [], "state_ambiguous")
    resolver_query = nickname_alias["canonical_title"] if nickname_alias else args.title
    state_show = local_matches[0] if local_matches else None
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
            season=args.season,
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
    explicit_scope = {'season': args.season} if args.season else {}
    bangumi_resolved = False
    should_try_bangumi_first = (contains_cjk(args.title) and not nickname_alias) or bool(state_show) or not resolved.search_titles
    if should_try_bangumi_first:
        bangumi_attempted = True
        for query in unique([args.title, resolver_query, resolved.title])[:2]:
            status, fresh = resolve_bangumi_title(query, args.timeout, today, **explicit_scope)
            if status == "resolved" and fresh:
                resolved = merge_resolved(resolved, fresh)
                sources.append("bangumi")
                bangumi_resolved = True
                break
            if status == "ambiguous" and fresh:
                ambiguous = fresh
            else:
                failures.append(resolver_failure("bangumi", fresh))
                resolved.stage_errors.extend(fresh.stage_errors if fresh else [])

    anilist_queries = unique(
        [
            resolved.title,
            *resolved.search_titles,
            resolver_query,
            *resolved.aliases,
        ]
    )
    should_try_anilist = not state_show or not resolved.search_titles or bangumi_resolved
    if should_try_anilist:
        for query in anilist_queries[:2]:
            status, fresh = resolve_title(query, args.timeout, today, **explicit_scope)
            if status == "resolved" and fresh:
                resolved = merge_resolved(resolved, fresh)
                sources.append("anilist")
                break
            if status == "ambiguous" and fresh:
                ambiguous = ambiguous or fresh
            else:
                failures.append(resolver_failure("anilist", fresh))
                resolved.stage_errors.extend(fresh.stage_errors if fresh else [])

    if not bangumi_attempted and not resolved.search_titles:
        for query in unique([args.title, resolver_query])[:2]:
            status, fresh = resolve_bangumi_title(query, args.timeout, today, **explicit_scope)
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
    # External bindings and discovered search aliases cannot join local records.

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


def lock_identity(resolution, request):
    from .models import WorkIdentity, WorkflowError
    from .schema import new_track_id
    from .evidence import part_of
    from .providers import canonical_season
    resolved, show = resolution.resolved, resolution.state_show or {}
    expected = request.season or show.get('season') or resolved.season
    if expected is None and not show and resolved.format in {'TV', 'TV_SHORT', 'ONA'} and resolved.mainline_scope == 'single':
        expected = 'S01'
        resolved.season = expected
    if request.season and resolved.season and canonical_season(resolved.season) != request.season:
        raise WorkflowError('identity', 'explicit_season_conflict', False, (), 'verify_requested_season')
    locked = WorkIdentity(show.get('track_id') or new_track_id(), show.get('title') or resolved.title,
        canonical_season(expected), show.get('part') or part_of([resolved.title]),
        show.get('identity_revision', 0), tuple(show.get('aliases', resolved.aliases)),
        show.get('format') or resolved.format)
    resolved.work_identity = locked
    return locked

