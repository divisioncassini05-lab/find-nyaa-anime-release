"""Extracted policy module: retrieval."""

from __future__ import annotations

import argparse


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
        allow_upward_compatibility=getattr(args, "allow_upward_compatibility", False),
        prefer_group=args.release_group_hint,
        avoid_group=[],
        inspect_details=args.require_zh,
        detail_limit=5 if args.require_zh else 0,
        detail_batch_size=5,
        detail_budget_seconds=30.0,
        include_magnets=args.include_magnet,
        magnet_only=False,
        legal_ok=args.legal_ok,
        candidate_id=[args.candidate_id] if getattr(args, "candidate_id", None) else [],
    )



from dataclasses import dataclass
from typing import Any

@dataclass
class RetrievalOutcome:
    core_report: Any
    fallback_report_for_diagnostic: Any
    fallback_selected: Any
    found_episode: Any
    needs_title_discovery: Any
    offline_evidence: Any
    output_contract: Any
    primary_report: Any
    quality_fallback: Any
    quality_upgrade: Any
    quality_upgrade_report: Any
    quality_upgrade_selected: Any
    release_search_names: Any
    selected: Any
    selected_item: Any
    status: Any
    target_episode: Any


def evaluate_resources(args, resolved, locked_identity, season, state_aliases, search_names, intent, target_episode, availability, requested_tier, search_release_report):
    import argparse
    from dataclasses import asdict
    from typing import Any
    from release_identity import EpisodeKind, normalize_season_number
    from release_search_core import SearchContext, SearchIntent
    from .queries import latin_search_titles
    from .queries import norm
    from .queries import promote_search_titles
    from .presentation import result_output_contract
    from .queries import strict_zh_search_names
    from .queries import unique
    from .trace import trace_stage
    from offline_identity import read_catalog, lookup
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
    from offline_identity import read_catalog, lookup
    verified_bindings = {(e.provider, e.entry_id) for e in resolved.evidence}
    identity_ids = tuple((key,int(value)) for key,value in [('anilist',resolved.anilist_id),('bangumi',resolved.bangumi_id)]
                         if value and (key, str(value)) in verified_bindings)
    try:
        offline_evidence = lookup(read_catalog(args.offline_catalog),identity_ids)
    except (ValueError,OSError) as exc:
        offline_evidence = {'aliases':[], 'mappings':[], 'sources':[], 'conflicts':[str(exc)]}
    search_context = SearchContext(
        canonical_title=locked_identity.title,
        aliases=tuple(unique([*locked_identity.aliases, *resolved.metadata_titles, *offline_evidence['aliases']])),
        search_titles=tuple(base_search_names),
        related_titles=tuple(resolved.related_titles),
        mainline_scope=resolved.mainline_scope,
        resolved_season=normalize_season_number(locked_identity.season),
        expected_episodes=resolved.episodes,
        flexible_title_match=args.require_zh,
        identifiers=identity_ids,
        episode_mappings=tuple(offline_evidence['mappings']),
        source_numbering=args.source_numbering,
        target_numbering=args.target_numbering,
    )
    trace_stage('retrieval')
    core_report = search_release_report(
        search_args,
        intent=intent,
        requested_episode=target_episode,
        include_specials=args.include_specials,
        cache_path=args.cache,
        refresh_cache=args.refresh_cache,
        context=search_context,
    )
    if intent is SearchIntent.LATEST_REGULAR:
        target_episode = core_report.requested_episode
        availability["target_episode"] = target_episode
    primary_report = core_report
    quality_fallback: dict[str, Any] | None = None
    fallback_report_for_diagnostic = None
    # Historical result fields remain readable; new searches keep the requested tier.
    quality_upgrade = None
    quality_upgrade_report = None
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
    status = core_report.status
    fallback_selected = None
    quality_upgrade_selected = None
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
        and availability.get("target_source") != "nyaa_discovery_required"
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
    if (
        status == "found" or (status == "latest_unresolved" and selected is not None)
    ) and not output_contract["ready"]:
        status = "output_incomplete"

    found_episode: int | None = None
    if (
        selected_item
        and selected_item.identity.kind is EpisodeKind.REGULAR
        and selected_item.identity.episode is not None
        and selected_item.identity.episode == selected_item.identity.episode.to_integral_value()
    ):
        found_episode = int(selected_item.identity.episode)

    return RetrievalOutcome(core_report, fallback_report_for_diagnostic, fallback_selected, found_episode, needs_title_discovery, offline_evidence, output_contract, primary_report, quality_fallback, quality_upgrade, quality_upgrade_report, quality_upgrade_selected, release_search_names, selected, selected_item, status, target_episode)
