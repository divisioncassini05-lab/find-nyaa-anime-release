"""Old flag syntax routed to the v3 workflow; never to a legacy writer."""
from dataclasses import asdict
from pathlib import Path
import json
from .store import StateRepository, require
from .evidence import ReviewManifest, QualityPolicy, ReviewValidator
from .clients import DesktopLauncherClient
from .workflow import Workflow, Request, render_report
from .outbox import drain


def run(args):
    repo = StateRepository(args.state)
    require(not args.mark_finished, 'mark_finished_removed_use_reconcile')
    show = repo.find(title=args.title)
    require(show is not None, 'not_tracked_use_watch_create')
    policy = QualityPolicy(args.tier, args.require_zh, args.want_zh, args.min_gib_per_episode,
                           args.max_gib_per_episode, args.allow_upward_compatibility)
    if args.completion_evidence:
        require(not args.no_state_update, 'read_only_completion_use_reconcile')
        repo.attach_completion(show['track_id'], json.loads(Path(args.completion_evidence).read_text(encoding='utf-8-sig')))
        show = repo.find(track_id=show['track_id'])
    if show['lifecycle']['phase'] in {'completed','blocked'} or show['progress']['target_episode'] is None:
        from .cli import report
        if not args.no_state_update:
            repo.command(show['track_id'], 'reconcile_completion')
            drain(repo)
        result = report(repo.find(track_id=show['track_id']))
    elif not args.review:
        result = {'status':'agent_review_required', 'track_id':show['track_id'],
                  'next_action':'watch discover, review, then deliver', 'state_update':'none'}
    else:
        require(not (args.whole_season or args.include_specials or args.official_air_date), 'review_requires_regular_episode')
        require(not (args.source_numbering or args.target_numbering or args.identity_evidence), 'review_does_not_mutate_provider_bindings')
        require(not args.season or args.season.upper() == show['identity'].get('season'), 'explicit_season_conflict')
        manifest = ReviewManifest.load(args.review)
        if args.candidate_id:
            from nyaa_client import nyaa_id_from_url
            require(nyaa_id_from_url(args.candidate_id) == str(manifest.content.get('candidate_id')), 'review_candidate_conflict')
        expected_intent = 'latest_regular' if args.latest else 'specific_episode' if args.episode is not None else 'next_tracked'
        require(manifest.content.get('intent') == expected_intent, 'review_intent_conflict')
        if args.episode is not None:
            require(manifest.content['target_episode'] == args.episode, 'review_episode_conflict')
        if args.no_state_update or not args.enqueue_qbittorrent:
            require(not (args.no_state_update and args.enqueue_qbittorrent), 'read_only_prohibits_enqueue')
            require(not args.include_magnet or args.legal_ok, 'legal_confirmation_required')
            result = ReviewValidator().validate(manifest, show, policy).report
            if not args.include_magnet and result.get('selected'):
                result['selected']['magnet'] = None
        else:
            require(args.include_magnet and args.legal_ok, 'delivery_flags_required')
            client = DesktopLauncherClient(executable=args.qbittorrent_exe, save_path=args.qbittorrent_save_path,
                                           backup_dir=args.qbittorrent_backup_dir, profile_path=args.qbittorrent_profile)
            result = render_report(repo, Workflow(repo,client).deliver(Request(args.title,Path(args.review),policy,
                str(args.qbittorrent_save_path) if args.qbittorrent_save_path else None)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 6 if result['status'] in {'available_enqueue_failed','accepted_receipt_commit_failed','blocked','recovery_required'} else 4 if result['status']=='agent_review_required' else 0
