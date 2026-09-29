"""Extracted policy module: workflow."""

from __future__ import annotations
from .settings import MAINLINE_FORMATS

import argparse
import copy
import sys
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from airing_watch_state import completed_episode
from qbittorrent_submit import DEFAULT_BACKUP_DIR as DEFAULT_QBITTORRENT_BACKUP_DIR, SubmissionError, submit_magnet
from release_identity import EpisodeKind, normalize_season_number
from nyaa_client import nyaa_id_from_url
from release_search_core import SearchContext, SearchIntent, search_release_report
from search_nyaa_releases import DEFAULT_TIER_MIN_GIB
from state_io import StateFileError, load_state
from failure_recovery import transport_diagnostic


import completion as completion_policy


def new_tracking_record(identity, resolved):
    return {'title': identity.title, 'season': identity.season,
        'aliases': list(identity.aliases), 'part': identity.part, 'format': resolved.format,
        'anilist_id': resolved.anilist_id, 'bangumi_id': resolved.bangumi_id,
        'search_titles': resolved.search_titles, 'verified_search_titles': resolved.verified_search_titles,
        'mainline_scope': resolved.mainline_scope, 'total_episodes': resolved.episodes,
        'duration_min': resolved.duration_min, 'status': 'waiting', 'airing': True}


def run(args: argparse.Namespace) -> int:
    from .cli import build_parser
    from .retrieval import build_search_args
    from .providers import canonical_season
    from .metadata import completed_part_context
    from .legacy_state import delete_show
    from .legacy_state import detect_tracked_titles
    from .queries import emit_json
    from .metadata import ensure_official_air_identity
    from .legacy_state import find_show
    from .metadata import hydrate_airing_metadata
    from .presentation import identity_conflict_report
    from .presentation import identity_report_fields
    from .presentation import is_final_episode
    from .metadata import latest_regular_target
    from .queries import latin_search_titles
    from .metadata import next_airing_context
    from .queries import norm
    from .metadata import official_air_date_report
    from .presentation import premium_source_type
    from .queries import promote_search_titles
    from .presentation import quality_compatibility
    from .presentation import render_failure_reply
    from .presentation import render_latest_already_handled_reply
    from .metadata import render_not_aired_reply
    from .metadata import render_part_finished_reply
    from .presentation import render_quality_fallback_question
    from .presentation import render_quality_upgrade_question
    from .presentation import render_result_reply
    from .presentation import render_season_batch_reply
    from .identity import resolve_work_identity
    from .presentation import result_output_contract
    from .batch import run_tracked_title_batch
    from .legacy_state import sanitize_state_aliases
    from .queries import select_search_names
    from .presentation import selected_view
    from .cli import status_return_code
    from .queries import strict_zh_search_names
    from .queries import unique
    from .legacy_state import upsert_show
    from .requests import from_args
    from .identity import lock_identity
    from .models import TargetDecision, StateCommand, WorkflowError
    from .repository import StateRepository, require_record
    from .delivery import verify, finalize
    from .trace import trace_stage
    trace_stage('request')
    if bool(args.source_numbering) != bool(args.target_numbering):
        print("--source-numbering and --target-numbering must be provided together.", file=sys.stderr)
        return 2
    if args.defer_state_until_download_complete:
        print(
            "--defer-state-until-download-complete has been retired. Remove it to use "
            "the standard progress boundary: a qualified magnet returned or qBittorrent submission accepted.",
            file=sys.stderr,
        )
        return 2
    if args.candidate_id:
        args.candidate_id = nyaa_id_from_url(args.candidate_id)
        if args.candidate_id is None:
            print("--candidate-id must be a numeric Nyaa ID or view URL.", file=sys.stderr)
            return 2
        if (
            sum((args.episode is not None, args.latest, args.whole_season)) != 1
            or args.official_air_date or args.mark_finished or args.include_specials
        ):
            print("--candidate-id requires exactly one of --episode, --latest, or --whole-season and cannot be used for schedule, finish, or special operations.", file=sys.stderr)
            return 2
    if args.official_air_date:
        if args.episode is None:
            print("--official-air-date requires --episode.", file=sys.stderr)
            return 2
        args.no_state_update = True
        args.no_auto_batch = True
    if args.require_zh:
        args.want_zh = True
        args.include_page_link = True
    if args.include_magnet and not args.legal_ok:
        print("Refusing to print magnet links without --legal-ok.", file=sys.stderr)
        return 2
    if args.enqueue_qbittorrent and (not args.include_magnet or not args.legal_ok):
        print(
            "--enqueue-qbittorrent requires --include-magnet and --legal-ok.",
            file=sys.stderr,
        )
        return 2
    try:
        state = load_state(args.state)
    except StateFileError as exc:
        report = {"status": "state_corrupt", "error": str(exc), "state_update": "unchanged"}
        if args.json:
            emit_json(report)
        else:
            print(str(exc), file=sys.stderr)
        return 2
    state_base = copy.deepcopy(state)
    state_repairs = []  # Identity aliases are not silently rewritten by discovery.
    mentions = detect_tracked_titles(state, args.title)
    if (args.candidate_id or args.completion_evidence) and len(mentions) >= 2:
        print("--candidate-id finalizes one work; supply a single title.", file=sys.stderr)
        return 2
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

    request = from_args(args)
    args.season = request.season
    trace_stage('identity')
    identity = resolve_work_identity(args, state, date.today())
    resolved = identity.resolved
    state_show = identity.state_show
    resolver_status = identity.resolver
    tracked = identity.tracked
    locked_identity = lock_identity(identity, request)
    if args.identity_evidence:
        from .evidence import reviewed_official
        resolved.official_identity_evidence = reviewed_official(args.identity_evidence, locked_identity)
    trace_stage('metadata', track_id=locked_identity.track_id, season=locked_identity.season)
    repo = StateRepository(args.state)
    if resolved.identity_conflicts:
        report = identity_conflict_report(identity)
        emit_json(report) if args.json else print(report["reply_text"])
        return 0
    if args.official_air_date:
        identity = ensure_official_air_identity(
            identity,
            args.schedule_cache,
            args.timeout,
            args.refresh_cache,
            date.today(),
        )
        tracked = identity.tracked
        resolver_status = identity.resolver
        report = official_air_date_report(
            identity,
            args.episode,
            args.schedule_cache,
            args.timeout,
            args.refresh_cache,
            date.today(),
        )
        report["tracked"] = tracked
        report["state_update"] = "none"
        report["resolver"] = resolver_status
        if args.json:
            emit_json(report)
        else:
            print(report["status"])
        return {
            "found": 0,
            "not_current_airing": 0,
            "not_current_new_anime": 0,
            "not_aired_yet": 0,
            "schedule_unavailable": 1,
            "ambiguous": 4,
        }.get(report["status"], 1)
    state_update = "none"
    schedule_cache_status = "not_used"
    season = canonical_season(args.season or resolved.season or (state_show or {}).get("season"))
    if args.whole_season and state_show and not args.no_web_resolve:
        resolved, schedule_cache_status = hydrate_airing_metadata(
            resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today())
        identity.resolved = resolved
        if resolved.identity_conflicts:
            report = identity_conflict_report(identity)
            emit_json(report) if args.json else print(report['reply_text'])
            return 0
    if args.completion_evidence:
        try:
            completion_policy.apply_evidence(resolved, completion_policy.read_evidence(
                args.completion_evidence, resolved, season))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            emit_json({"status": "invalid_completion_evidence", "error": str(exc), "state_update": "none"})
            return 2
    if (
        season is None
        and state_show is None
        and resolved.status == "FINISHED"
        and resolved.format in MAINLINE_FORMATS
        and resolved.mainline_scope == "single"
    ):
        season = "S01"
        resolved.season = season
        schedule_cache_status = "single_mainline_inferred"
    state_aliases = unique([*resolved.aliases, args.title])
    search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)

    if args.mark_finished:
        if not args.no_state_update and state_show:
            state = repo.commit(StateCommand(locked_identity.track_id, 'delete',
                expected_revision=state_show['revision'], expected_identity_revision=locked_identity.revision))
            state_update = 'deleted_finished' 
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

    old_untracked_mainline = bool(
        state_show is None
        and resolved.format in MAINLINE_FORMATS
        and (resolved.status == "FINISHED" or not resolved.trackable)
    )
    if (
        args.episode is None
        and not args.latest
        and old_untracked_mainline
        and season is None
    ):
        reply_text = (
            f"《{args.title}》的目标季数还不能可靠确定。请告诉我要找第几季"
            "（例如“第一季”或“S02”），确认后我再搜索整季资源。"
        )
        report = {
            "status": "needs_season_confirmation",
            "intent": SearchIntent.SEASON_BATCH.value,
            "resolved_title": resolved.title,
            "aliases": search_names,
            "season": None,
            "target_episode": None,
            "availability": {
                "target_source": "season_unresolved",
                "official_target": False,
            },
            "quality": {"requested_tier": requested_tier, "fallback": None},
            "tracked": tracked,
            "selected": None,
            "choices": [],
            "diagnostic": {
                "search_skipped": "season_unresolved",
                "mainline_scope": resolved.mainline_scope,
                "related_titles": resolved.related_titles[:4],
            },
            "state_update": "none",
            "resolver": resolver_status,
            "cache": {"rss": "not_used", "schedule": "not_used"},
            "search_return_code": None,
            "search_stderr": "",
            "reply_text": reply_text,
            "output_contract": {
                "ready": True,
                "magnet_requested": bool(args.include_magnet),
                "required_fields": [],
                "missing_fields": [],
            },
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print(reply_text)
        return 0

    # Check the season boundary before BOTH scheduled latest and tracked-next.
    # A retained completed record makes repeated automation runs network-free.
    if state_show and args.episode is None and not args.whole_season:
        if not completion_policy.confirmed(resolved) and not args.no_web_resolve and not args.completion_evidence:
            resolved, schedule_cache_status = hydrate_airing_metadata(
                resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today())
            identity.resolved = resolved
        if resolved.identity_conflicts:
            report = identity_conflict_report(identity)
            emit_json(report) if args.json else print(report["reply_text"])
            return 0
        handled = completed_episode(state_show)
        boundary = completed_part_context(resolved, handled)
        reasons = completion_policy.review_reasons(resolved, handled, date.today())
        if schedule_cache_status == "unavailable" and resolved.status is None and not completion_policy.confirmed(resolved):
            reasons.append("airing_metadata_unavailable")
        if boundary is not None or reasons:
            done = boundary is not None
            report_status = ("split_cour_break" if boundary and boundary["status"] == "split_cour_break"
                             else "completed") if done else "needs_completion_review"
            if done and report_status != 'split_cour_break' and not args.no_state_update:
                before = copy.deepcopy(state_show)
                completion_policy.mark_completed(state_show, resolved)
                # Avoid updating timestamps on every already-complete run.
                if before.get("status") != "completed" or before.get("completion") != resolved.completion:
                    state = repo.commit(StateCommand(locked_identity.track_id, 'completed',
                        expected_identity_revision=locked_identity.revision, fields={'completion': resolved.completion}))
                    state_update = 'completed' 
                else:
                    state_update = "unchanged"
            reply = (render_part_finished_reply(args.title, season, boundary) if boundary else
                     f"《{args.title}》需核实最终集和播出结束日期，再继续自动追番。")
            report = {"status": report_status, "tracked": True, "state_update": state_update,
                      "resolved_title": resolved.title, "season": season,
                      "intent": SearchIntent.LATEST_REGULAR.value if args.latest else SearchIntent.NEXT_TRACKED.value,
                      "cache": {"rss": "not_used", "schedule": schedule_cache_status},
                      "selected": None, "target_episode": None, "reply_text": reply,
                      "availability": {"state": report_status, "part": boundary},
                      "progress": {"before_episode": handled, "after_episode": handled,
                                   "latest_episode": resolved.episodes if done else None,
                                   "next_episode": None if done else state_show.get("next_episode"), "advanced": False},
                      "diagnostic": {"search_skipped": "completion_boundary", "completion_review_reasons": reasons},
                      "qbittorrent": {"status": "not_attempted", "reason": report_status},
                      **identity_report_fields(identity, season)}
            if args.json:
                emit_json(report)
            else:
                print(reply)
            return 0

    trace_stage('target')
    target_episode = args.episode
    intent: SearchIntent
    availability: dict[str, Any] = {"target_source": "input", "official_target": False}
    not_aired_yet = False
    part_finished: dict[str, Any] | None = None
    if target_episode is not None:
        intent = SearchIntent.SPECIFIC_EPISODE
    elif args.latest:
        intent = SearchIntent.LATEST_REGULAR
        if not args.no_web_resolve and schedule_cache_status == "not_used" and not args.completion_evidence:
            resolved, schedule_cache_status = hydrate_airing_metadata(
                resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today()
            )
            identity.resolved = resolved
            state_aliases = unique([*resolved.aliases, args.title])
            search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)
        target_episode, target_source = latest_regular_target(
            resolved, state_show, use_state_fallback=False
        )
        availability = {
            "target_source": target_source,
            "official_target": target_source.startswith("anilist"),
            "target_episode": target_episode,
        }
        not_aired_yet = target_source == "not_aired_yet"
    elif args.whole_season or old_untracked_mainline:
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
            if schedule_cache_status == "not_used" and not args.completion_evidence:
                resolved, schedule_cache_status = hydrate_airing_metadata(
                    resolved, args.timeout, args.schedule_cache, args.refresh_cache, date.today()
                )
            identity.resolved = resolved
            state_aliases = unique([*resolved.aliases, args.title])
            search_names = select_search_names(resolved.title, state_aliases, args.query_limit, resolved.search_titles)
            part_finished = completed_part_context(resolved, completed_episode(state_show))
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

    if resolved.identity_conflicts:
        identity.resolved = resolved
        report = identity_conflict_report(identity)
        emit_json(report) if args.json else print(report["reply_text"])
        return 0

    if resolved.repair_proposal and state_show and not args.no_state_update:
        from dataclasses import replace
        current = require_record(repo.read(), locked_identity.track_id)
        updated = repo.commit(StateCommand(locked_identity.track_id, 'metadata_repair',
            expected_revision=current['revision'], expected_identity_revision=locked_identity.revision,
            fields={'binding_evidence': resolved.repair_proposal}))
        state_show = require_record(updated, locked_identity.track_id)
        locked_identity = replace(locked_identity, revision=state_show['identity_revision'])
        resolved.work_identity = locked_identity
        state = updated

    if state_show and args.episode is None and not args.whole_season and completion_policy.confirmed(resolved):
        # Broadcasting ended, but the final release has not been delivered.
        # This targets the known finale without claiming Nyaa availability.
        target_episode = resolved.episodes
        intent = SearchIntent.SPECIFIC_EPISODE
        availability = {"target_source": "confirmed_final_episode", "official_target": True,
                        "target_episode": target_episode}
        not_aired_yet = False

    if part_finished is not None:
        report_status = str(part_finished["status"])
        availability.update(
            {
                "state": "split_cour_break" if report_status == "split_cour_break" else "part_finished",
                "part": part_finished,
            }
        )
        current_progress = completed_episode(state_show)
        progress = {
            "before_episode": current_progress,
            "after_episode": current_progress,
            "latest_episode": resolved.episodes,
            "next_episode": (state_show or {}).get("next_episode"),
            "advanced": False,
        }
        display_title = str((state_show or {}).get("title") or args.title)
        reply_text = render_part_finished_reply(display_title, season, part_finished)
        report = {
            "status": report_status,
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
            "diagnostic": {"raw_count": 0, "search_skipped": "part_boundary"},
            "state_update": "none",
            "progress": progress,
            "resolver": resolver_status,
            "cache": {"rss": "not_used", "schedule": schedule_cache_status},
            "search_return_code": 0,
            "search_stderr": "",
            "reply_text": reply_text,
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print(reply_text)
        return 0

    if not_aired_yet:
        airing = {
            "status": "schedule_unavailable",
            "episode": target_episode,
            "airing_at": resolved.next_airing_at,
            "airing_date": (
                datetime.fromtimestamp(resolved.next_airing_at).date().isoformat()
                if isinstance(resolved.next_airing_at, int)
                else None
            ),
            "weekly_break": False,
            "skipped_weeks": 0,
        }
        if (
            isinstance(target_episode, int)
            and availability.get("official_target")
            and resolved.anilist_id
            and not args.no_web_resolve
        ):
            airing = next_airing_context(
                identity,
                target_episode,
                args.schedule_cache,
                args.timeout,
                args.refresh_cache,
                date.today(),
            )
        if airing.get("long_break"):
            report_status = "long_break_unconfirmed"
            availability["state"] = "long_break_unconfirmed"
        elif airing.get("weekly_break"):
            report_status = "airing_schedule_break"
            availability["state"] = "schedule_break"
        else:
            report_status = "not_aired_yet"
            availability["state"] = "not_due"
        availability["next_airing"] = airing
        current_progress = completed_episode(state_show)
        next_progress = (state_show or {}).get("next_episode")
        progress = {
            "before_episode": current_progress,
            "after_episode": current_progress,
            "latest_episode": availability.get("official_latest_episode"),
            "next_episode": next_progress,
            "advanced": False,
        }
        display_title = str((state_show or {}).get("title") or args.title)
        reply_text = (
            render_not_aired_reply(display_title, season, target_episode, airing)
            if isinstance(target_episode, int)
            else f"《{display_title}》下一集尚未播出。"
        )
        report = {
            "status": report_status,
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
            "progress": progress,
            "resolver": resolver_status,
            "cache": {"rss": "not_used", "schedule": schedule_cache_status},
            "search_return_code": 0,
            "search_stderr": "",
            "reply_text": reply_text,
            **identity_report_fields(identity, season, search_names),
        }
        if args.json:
            emit_json(report)
        else:
            print(reply_text)
        return 0

    from .retrieval import evaluate_resources
    retrieval = evaluate_resources(args, resolved, locked_identity, season, state_aliases, search_names, intent, target_episode, availability, requested_tier, search_release_report)
    core_report = retrieval.core_report
    fallback_report_for_diagnostic = retrieval.fallback_report_for_diagnostic
    fallback_selected = retrieval.fallback_selected
    found_episode = retrieval.found_episode
    needs_title_discovery = retrieval.needs_title_discovery
    offline_evidence = retrieval.offline_evidence
    output_contract = retrieval.output_contract
    primary_report = retrieval.primary_report
    quality_fallback = retrieval.quality_fallback
    quality_upgrade = retrieval.quality_upgrade
    quality_upgrade_report = retrieval.quality_upgrade_report
    quality_upgrade_selected = retrieval.quality_upgrade_selected
    release_search_names = retrieval.release_search_names
    selected = retrieval.selected
    selected_item = retrieval.selected_item
    status = retrieval.status
    target_episode = retrieval.target_episode

    current_completed_before = completed_episode(state_show)
    already_handled_latest = bool(
        intent is SearchIntent.LATEST_REGULAR
        and found_episode is not None
        and current_completed_before is not None
        and found_episode <= current_completed_before
    )

    trace_stage('verification')
    qbittorrent_report = None
    receipt = None
    if status == 'found' and output_contract['ready'] and (args.include_magnet or args.enqueue_qbittorrent):
        if already_handled_latest:
            qbittorrent_report = {'status': 'not_attempted', 'ok': True, 'reason': 'latest_already_handled'}
        elif args.enqueue_qbittorrent and not args.candidate_id:
            status = 'review_required'
            qbittorrent_report = {'status': 'not_attempted', 'ok': False, 'reason': 'reviewed_candidate_id_required'}
        else:
            target = TargetDecision(locked_identity, intent.value, target_episode or found_episode,
                availability.get('target_source', 'verified_release'),
                latest_confirmed=(intent is not SearchIntent.LATEST_REGULAR or core_report.status == 'found'))
            verified = verify(locked_identity, target, selected, selected_item, status,
                output_contract['ready'], reviewed_id=args.candidate_id, enqueue=args.enqueue_qbittorrent)
            trace_stage('delivery')
            try:
                create = None
                if state_show is None and resolved.trackable and verified.kind == 'regular':
                    create = new_tracking_record(locked_identity, resolved)
                result, receipt = finalize(verified, request, args.state, submit_magnet,
                    client_options={'executable': args.qbittorrent_exe,
                        'save_path': args.qbittorrent_save_path,
                        'backup_dir': args.qbittorrent_backup_dir or DEFAULT_QBITTORRENT_BACKUP_DIR,
                        'profile_path': args.qbittorrent_profile}, create_record=create, completion=resolved.completion, evidence=resolved.evidence,
                    broadcast={'search_titles': resolved.search_titles, 'verified_search_titles': resolved.verified_search_titles,
                        'related_titles': resolved.related_titles, 'continuation_parts': resolved.continuation_parts,
                        'mainline_scope': resolved.mainline_scope, 'total_episodes': resolved.episodes,
                        'duration_min': resolved.duration_min})
                if args.enqueue_qbittorrent:
                    qbittorrent_report = result
                    if not result.get('ok'):
                        status = 'download_enqueue_failed'
                if result.get('reason') in {'latest_already_handled', 'season_completed'}:
                    state_show = require_record(repo.read(), locked_identity.track_id)
                    already_handled_latest = result['reason'] == 'latest_already_handled'
                    if result['reason'] == 'season_completed':
                        status, state_update = 'completed', 'unchanged_already_watched'
            except SubmissionError as exc:
                qbittorrent_report = exc.as_report()
                status = 'download_enqueue_failed'
    trace_stage('state_commit')

    if (
        intent is SearchIntent.LATEST_REGULAR
        and target_episode is None
        and found_episode is not None
    ):
        # In discovery mode the selected, verified regular release is the
        # actual latest episode for this run and should be reported as such.
        target_episode = found_episode
        availability["target_episode"] = found_episode

    if receipt is not None and receipt.accepted:
        state = repo.read()
        state_show = next((show for show in state['shows'] if show['track_id'] == locked_identity.track_id), state_show)
        if state_show:
            tracked = True
            if state_show.get('status') == 'completed' and (current_completed_before is None or (found_episode or 0) > current_completed_before):
                status, state_update = 'completed', 'completed'
            elif completed_episode(state_show) and (current_completed_before is None or completed_episode(state_show) > current_completed_before):
                state_update = 'advanced'
            else:
                state_update = 'unchanged_already_watched'
    elif already_handled_latest and status == 'found':
        status = 'latest_already_handled'
        state_update = 'unchanged_already_watched' if not args.no_state_update else 'none'
    elif (not args.no_state_update and state_show
          and not (intent is SearchIntent.LATEST_REGULAR and availability.get('target_source') == 'nyaa_discovery_required')
          and status in {'subtitle_check_incomplete', 'release_unqualified', 'subtitle_unqualified', 'no_nyaa_release_for_target'}):
        state = repo.commit(StateCommand(locked_identity.track_id, 'waiting',
            expected_identity_revision=locked_identity.revision,
            fields={'notes': f'Current-season target has status: {status}.'}))
        state_show = require_record(state, locked_identity.track_id)
        state_update = 'tracked_waiting'
    elif (not args.no_state_update and state_show is None and resolved.trackable
          and resolved.current and resolved.evidence and resolved.format in MAINLINE_FORMATS
          and locked_identity.season and intent is not SearchIntent.SEASON_BATCH
          and target_episode is not None
          and status in {'release_unqualified', 'subtitle_unqualified', 'no_nyaa_release_for_target'}):
        state = repo.commit(
            StateCommand(locked_identity.track_id, 'create', fields=new_tracking_record(locked_identity, resolved)),
            StateCommand(locked_identity.track_id, 'metadata_bind', expected_identity_revision=locked_identity.revision,
                fields={'evidence': [asdict(e) for e in resolved.evidence]}))
        state_show = require_record(state, locked_identity.track_id)
        state_update, tracked = 'tracked_waiting', True


    progress_show = state_show
    if status == 'found' and found_episode is not None and current_completed_before is not None and found_episode <= current_completed_before and not args.no_state_update:
        state_update = 'unchanged_already_watched'
    progress_after = completed_episode(progress_show)
    progress_next = (progress_show or {}).get("next_episode")
    if not isinstance(progress_next, int) and progress_after is not None and (progress_show or {}).get("status") != "completed":
        progress_next = progress_after + 1
    progress = {
        "before_episode": current_completed_before,
        "after_episode": progress_after,
        "latest_episode": found_episode if found_episode is not None else target_episode,
        "next_episode": progress_next,
        "advanced": bool(
            current_completed_before is not None
            and progress_after is not None
            and progress_after > current_completed_before
        )
        or bool(current_completed_before is None and progress_after is not None),
    }

    if status == "completed":
        availability["state"] = "completed"
    elif status in {"found", "finished_deleted", "latest_already_handled"}:
        availability["state"] = "available"
    elif status == "download_enqueue_failed":
        availability["state"] = "available_enqueue_failed"
    elif status in {
        "no_rss_candidates",
        "no_nyaa_release_for_target",
        "release_unqualified",
        "subtitle_unqualified",
        "no_complete_season_release",
    }:
        availability["state"] = "release_unqualified" if status in {"release_unqualified","subtitle_unqualified"} else (
            "aired_no_release" if availability.get("official_target") else "release_not_confirmed")
    elif status in {
        "network_error",
        "subtitle_check_incomplete",
        "season_check_incomplete",
        "latest_unresolved",
        "output_incomplete",
    }:
        availability["state"] = "search_incomplete"

    diagnostic = dict(core_report.diagnostics)
    transport = transport_diagnostic({"failures": core_report.failures,
        "search_run": core_report.search_run.as_dict() if core_report.search_run else {}})
    if transport:
        diagnostic["network"] = transport
    diagnostic['offline_identity'] = offline_evidence
    supplement_queries = (diagnostic.get('strict_zh_supplement') or {}).get('queries', [])
    actual_search_names = unique([*release_search_names, *supplement_queries])
    diagnostic["queries"] = actual_search_names
    if args.require_zh:
        diagnostic["strict_zh"] = {
            "enabled": True,
            "accepts": ["simplified_chinese", "traditional_chinese"],
            "queries": actual_search_names,
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
    if quality_upgrade is not None and quality_upgrade_report is not None:
        diagnostic.setdefault("quality_stages", {})["premium"] = quality_upgrade_report.diagnostics

    public_selected = selected_view(selected, args.include_page_link, args.require_zh)
    selected_compatibility = quality_compatibility(selected, args)
    if public_selected is not None and selected_compatibility is not None:
        public_selected["quality_compatibility"] = selected_compatibility
    public_fallback_selected = selected_view(fallback_selected, True, True)
    if public_fallback_selected is not None:
        public_fallback_selected.pop("magnet", None)
    public_quality_upgrade_selected = selected_view(quality_upgrade_selected, False, args.require_zh)
    if public_quality_upgrade_selected is not None:
        public_quality_upgrade_selected.pop("magnet", None)
        public_quality_upgrade_selected["source_type"] = quality_upgrade_selected.get("source_type")
    display_title = str((state_show or {}).get("title") or args.title)
    reply_text = ""
    if status == "latest_already_handled" and found_episode is not None:
        next_episode = progress.get("next_episode")
        if not isinstance(next_episode, int):
            next_episode = found_episode + 1
        reply_text = render_latest_already_handled_reply(
            display_title,
            season,
            found_episode,
            next_episode,
            args.enqueue_qbittorrent,
        )
    elif status in {"found", "finished_deleted", "completed", "latest_unresolved"} and public_selected and output_contract["ready"]:
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
    elif (
        status == "needs_quality_upgrade_confirmation"
        and public_quality_upgrade_selected
        and output_contract["ready"]
    ):
        reply_text = render_quality_upgrade_question(
            display_title,
            season,
            public_quality_upgrade_selected,
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
            target_episode,
        )
    if status == 'review_required':
        reply_text = f'《{display_title}》已发现第 {target_episode} 集候选；请审核完整标题与身份依据后，用 --candidate-id 核验并提交。'
    if status == "completed":
        reply_text += "\n最终集已成功交付，本季追踪完成。"
    report = {
        "status": status,
        "intent": intent.value,
        "resolved_title": resolved.title,
        "report_version": 2,
        "search_run": core_report.as_dict(explain=True).get("search_run"),
        "target_decision": core_report.as_dict(explain=True).get("target_decision"),
        "choice_count": len(core_report.choices),
        "choices_returned": len(core_report.as_dict(explain=args.explain)["choices"]),
        "choices_truncated": len(core_report.choices) > len(core_report.as_dict(explain=args.explain)["choices"]),
        "aliases": search_names,
        "queries": release_search_names,
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
            "upgrade": quality_upgrade,
            "upgrade_candidate": public_quality_upgrade_selected,
            "compatibility": selected_compatibility,
        },
        "tracked": tracked,
        "selected": public_selected,
        "choices": core_report.as_dict(explain=args.explain)["choices"],
        "diagnostic": diagnostic,
        "state_update": state_update,
        "progress": progress,
        "resolver": resolver_status,
        "cache": {"rss": core_report.cache, "schedule": schedule_cache_status},
        "search_return_code": status_return_code(status),
        "search_stderr": " | ".join(core_report.failures)[:600],
        "output_contract": output_contract,
        "qbittorrent": qbittorrent_report,
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

