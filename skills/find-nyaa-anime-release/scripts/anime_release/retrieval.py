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
    from search_nyaa_releases import DEFAULT_TIER_MIN_GIB
    from .queries import latin_search_titles
    from .queries import norm
    from .presentation import premium_source_type
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
    fallback_confirmation_item = None
    fallback_report = None
    quality_upgrade: dict[str, Any] | None = None
    quality_upgrade_report = None
    quality_upgrade_item = None
    fallback_tier = {"watch": "browse", "premium": "watch"}.get(requested_tier)
    if (
        fallback_tier is not None
        and not args.candidate_id
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
            refresh_cache=False,
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
        elif fallback_report.status != "found":
            core_report = fallback_report
    if (
        intent is SearchIntent.SEASON_BATCH
        and not args.candidate_id
        and requested_tier == "watch"
        and args.size_policy_source == "tier"
        and fallback_report is not None
        and fallback_report.status
        in {"release_unqualified", "no_complete_season_release", "subtitle_unqualified"}
    ):
        premium_args = argparse.Namespace(**vars(args))
        premium_args.tier = "premium"
        premium_args.min_gib_per_episode = DEFAULT_TIER_MIN_GIB["premium"]
        premium_args.max_gib_per_episode = None
        premium_args.size_policy_source = "tier"
        premium_search_args = build_search_args(
            release_search_names[0],
            release_search_names[1:],
            premium_args,
            season,
            target_episode,
            resolved.duration_min,
        )
        premium_search_args.episodes = resolved.episodes
        quality_upgrade_report = search_release_report(
            premium_search_args,
            intent=intent,
            requested_episode=target_episode,
            include_specials=args.include_specials,
            cache_path=args.cache,
            refresh_cache=False,
            context=search_context,
        )
        quality_upgrade = {
            "from": requested_tier,
            "to": "premium",
            "status": quality_upgrade_report.status,
        }
        if quality_upgrade_report.status == "found":
            quality_upgrade_item = quality_upgrade_report.selected[0]
            quality_upgrade["requires_confirmation"] = True
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
    if quality_upgrade_item is not None:
        quality_upgrade_selected = asdict(quality_upgrade_item.candidate)
        quality_upgrade_selected.update(
            {
                "effective_season": quality_upgrade_item.effective_season,
                "season_source": quality_upgrade_item.season_source,
                "work_match": quality_upgrade_item.work_match,
                "coverage": (
                    quality_upgrade_item.coverage.as_dict()
                    if quality_upgrade_item.coverage
                    else None
                ),
            }
        )
        quality_upgrade_selected["source_type"] = premium_source_type(quality_upgrade_selected)
        status = "needs_quality_upgrade_confirmation"
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
    if status == "needs_quality_upgrade_confirmation":
        upgrade_coverage = (quality_upgrade_selected or {}).get("coverage") or {}
        upgrade_ready = bool(
            quality_upgrade_selected
            and quality_upgrade_selected.get("size")
            and quality_upgrade_selected.get("seeders") is not None
            and quality_upgrade_selected.get("source_type")
            and upgrade_coverage.get("complete") is True
            and upgrade_coverage.get("quality_fit") is True
        )
        output_contract = {
            "ready": upgrade_ready,
            "magnet_requested": args.include_magnet,
            "magnet_deferred_until_confirmation": True,
            "required_fields": [
                "upgrade_candidate.size",
                "upgrade_candidate.seeders",
                "upgrade_candidate.source_type",
                "upgrade_candidate.coverage.complete",
                "upgrade_candidate.coverage.quality_fit",
            ],
            "missing_fields": [] if upgrade_ready else ["upgrade_candidate"],
        }
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
