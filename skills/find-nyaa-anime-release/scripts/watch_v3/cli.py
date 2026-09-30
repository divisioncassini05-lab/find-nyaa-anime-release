"""Explicit single-entry CLI. Read commands never migrate or mutate tracking."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
from runtime_paths import DEFAULT_STATE
from .store import StateRepository, migrate_state, require, digest
from .clients import DesktopLauncherClient, QbittorrentWebApiClient
from .evidence import DiscoveryService, ReviewManifest, ReviewValidator, QualityPolicy
from .workflow import Workflow, Request, render_report
from .outbox import drain


def parser():
    p = argparse.ArgumentParser(prog='watch')
    p.add_argument('--state', type=Path, default=DEFAULT_STATE)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('inspect','discover'):
        q = sub.add_parser(name)
        q.add_argument('title')
        q.add_argument('--latest', action='store_true')
        if name == 'discover':
            q.add_argument('--page', type=int, default=1)
            q.add_argument('--output', type=Path)
    q = sub.add_parser('workspace', help='Create an owned temporary evidence run')
    q = sub.add_parser('cleanup', help='Clean an ended run or expired unreferenced evidence')
    q.add_argument('--run', type=Path)
    q = sub.add_parser('detail')
    q.add_argument('candidate_id'); q.add_argument('--output', type=Path, required=True)
    q = sub.add_parser('create')
    q.add_argument('--identity', type=Path, required=True)
    q.add_argument('--track-id', required=True)
    q = sub.add_parser('review')
    q.add_argument('--track-id')
    q.add_argument('--listing', type=Path, action='append')
    q.add_argument('--detail', type=Path)
    q.add_argument('--intent', choices=['latest_regular','specific_episode','next_tracked'])
    q.add_argument('--episode', type=int)
    q.add_argument('--output', type=Path)
    q.add_argument('--manifest', type=Path)
    quality_args(q)
    q = sub.add_parser('deliver')
    q.add_argument('title', nargs='?')
    q.add_argument('--review', type=Path, required=True)
    q.add_argument('--latest', action='store_true')
    q.add_argument('--episode', type=int)
    q.add_argument('--enqueue-qbittorrent', action='store_true', required=True)
    q.add_argument('--include-magnet', action='store_true', required=True)
    q.add_argument('--legal-ok', action='store_true', required=True)
    q.add_argument('--operation-id')
    quality_args(q); client_args(q)
    q = sub.add_parser('recover')
    q.add_argument('--operation', required=True)
    client_args(q)
    q = sub.add_parser('reconcile')
    q.add_argument('title'); q.add_argument('--completion-evidence', type=Path)
    q = sub.add_parser('migrate')
    q.add_argument('--apply', action='store_true')
    q.add_argument('--expected-sha256')
    q = sub.add_parser('bind-automation')
    q.add_argument('--owner', type=Path, required=True)
    q.add_argument('--automation-config', type=Path, required=True,
                   help='Current exact scheduler TOML, read only; never inferred from a title')
    q = sub.add_parser('outbox')
    q.add_argument('--track-id')
    q = sub.add_parser('ack-outbox')
    q.add_argument('--track-id', required=True)
    q.add_argument('--outbox-id', required=True)
    q.add_argument('--receipt', type=Path, required=True)
    return p


def quality_args(q):
    q.add_argument('--tier', choices=['browse','watch','premium'], default='browse')
    q.add_argument('--require-zh', action='store_true')
    q.add_argument('--want-zh', action='store_true')
    q.add_argument('--min-gib-per-episode', type=float)
    q.add_argument('--max-gib-per-episode', type=float)
    q.add_argument('--allow-upward-compatibility', action='store_true')


def client_args(q):
    q.add_argument('--client', choices=['desktop','webapi'], default='desktop')
    q.add_argument('--qb-url', default='http://127.0.0.1:8080')
    q.add_argument('--qb-username-env', default='QBITTORRENT_USERNAME')
    q.add_argument('--qb-password-env', default='QBITTORRENT_PASSWORD')
    q.add_argument('--qbittorrent-exe', type=Path)
    q.add_argument('--qbittorrent-save-path', type=Path)
    q.add_argument('--qbittorrent-backup-dir', type=Path)
    q.add_argument('--qbittorrent-profile', type=Path)


def client(args):
    if args.client == 'webapi':
        return QbittorrentWebApiClient(args.qb_url, username=os.environ.get(args.qb_username_env), password=os.environ.get(args.qb_password_env))
    return DesktopLauncherClient(executable=args.qbittorrent_exe, save_path=args.qbittorrent_save_path,
        backup_dir=args.qbittorrent_backup_dir, profile_path=args.qbittorrent_profile)


def policy(args):
    return QualityPolicy(args.tier, args.require_zh, args.want_zh, args.min_gib_per_episode,
                         args.max_gib_per_episode, args.allow_upward_compatibility)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def report(show):
    return {'status':show['lifecycle']['phase'], 'track_id':show['track_id'], 'identity':show['identity'],
            'progress':show['progress'], 'broadcast':show['broadcast'], 'outbox':show['outbox'],
            'next_episode':show['progress']['target_episode'],
            'message':'等待完结确认' if show['lifecycle']['phase'] == 'finale_pending_evidence' and show['progress']['target_episode'] is None else None}


def run(argv=None):
    args = parser().parse_args(argv)
    repo = StateRepository(args.state)
    try:
        from evidence_artifacts import output_path, input_path, register
        if getattr(args, 'output', None):
            args.output = output_path(args.output,args.state)
        for field in ('manifest','review','detail'):
            if getattr(args,field,None):
                setattr(args,field,input_path(getattr(args,field),args.state))
        if getattr(args,'listing',None):
            args.listing = [input_path(p,args.state) for p in args.listing]
        if args.command == 'migrate':
            raw = args.state.read_bytes() if args.state.exists() else b'{}'
            data = json.loads(raw.decode('utf-8-sig'))
            converted = migrate_state(data)
            sha = hashlib.sha256(raw).hexdigest()
            result = {'status':'preview', 'source_sha256':sha, 'state':converted}
            if args.apply:
                require(bool(args.expected_sha256), 'migration_preview_hash_required')
                repo.migrate(expected_sha256=args.expected_sha256)
                result.update(status='applied')
        else:
            # New entry accepts only v3. Mutating commands perform the one-time
            # hash-guarded migration; read commands report migration_required.
            if args.command in {'create','deliver','recover','reconcile','bind-automation'}:
                raw = args.state.read_bytes() if args.state.exists() else b'{}'
                if json.loads(raw.decode('utf-8-sig')).get('version') != 3:
                    repo.migrate(expected_sha256=hashlib.sha256(raw).hexdigest())
            if args.command == 'workspace':
                from evidence_artifacts import new_workspace, collect_expired
                collect_expired(args.state)
                result = {'status':'workspace_created', 'run_dir':str(new_workspace(args.state))}
            elif args.command == 'cleanup':
                from evidence_artifacts import cleanup
                result = {'status':'artifacts_cleaned', **cleanup(repo,run=args.run,expired=not bool(args.run))}
            elif args.command == 'inspect':
                show = repo.find(title=args.title); require(show is not None, 'not_tracked')
                result = report(show)
            elif args.command == 'discover':
                show = repo.find(title=args.title)
                if show and (show['lifecycle']['phase'] in {'completed','blocked'} or show['progress']['target_episode'] is None):
                    result = report(show)
                else:
                    result = DiscoveryService().discover(args.title, args.page)
                    if args.output:
                        from anime_release.raw_evidence import save
                        save(args.output, result)
            elif args.command == 'detail':
                result = DiscoveryService().detail(args.candidate_id)
                from anime_release.raw_evidence import save
                save(args.output, result)
            elif args.command == 'create':
                result = repo.command(args.track_id, 'create_track', **read_json(args.identity))
            elif args.command == 'review':
                if args.manifest:
                    manifest = ReviewManifest.load(args.manifest)
                    show = repo.find(track_id=manifest.content['track_id']); require(show is not None, 'not_tracked')
                    result = ReviewValidator().validate(manifest, show, policy(args)).report
                else:
                    require(all([args.track_id,args.listing,args.detail,args.intent,args.episode,args.output]), 'review_draft_arguments_required')
                    show = repo.find(track_id=args.track_id); require(show is not None, 'not_tracked')
                    result = DiscoveryService().draft(show, args.listing, args.detail, args.intent, args.episode)
                    from anime_release.raw_evidence import save
                    save(args.output, result)
            elif args.command == 'deliver':
                manifest = ReviewManifest.load(args.review)
                if args.latest:
                    require(manifest.content['intent'] == 'latest_regular', 'review_intent_conflict')
                if args.episode is not None:
                    require(not args.latest and manifest.content['intent'] == 'specific_episode' and manifest.content['target_episode'] == args.episode, 'review_episode_conflict')
                outcome = Workflow(repo, client(args)).deliver(Request(args.title, args.review, policy(args),
                    str(args.qbittorrent_save_path) if args.qbittorrent_save_path else None, args.operation_id))
                result = render_report(repo, outcome)
            elif args.command == 'recover':
                result = render_report(repo, Workflow(repo, client(args)).recover(args.operation))
            elif args.command == 'reconcile':
                show = repo.find(title=args.title); require(show is not None, 'not_tracked')
                if args.completion_evidence:
                    repo.attach_completion(show['track_id'], read_json(args.completion_evidence))
                else:
                    repo.command(show['track_id'], 'reconcile_completion')
                drain(repo)
                result = report(repo.find(track_id=show['track_id']))
            elif args.command == 'bind-automation':
                owner = read_json(args.owner)
                import tomllib
                from .automation import scope_hash
                config = tomllib.loads(args.automation_config.read_text(encoding='utf-8-sig'))
                require(config.get('id') == owner['automation_id'], 'automation_id_mismatch')
                require(scope_hash(config['prompt']) == owner['scope_hash'], 'automation_scope_changed')
                require(owner.get('scope_reviewed') is True and owner.get('all_targets_resolved') is True,
                        'complete_prompt_scope_review_required')
                require(owner.get('retry_children_checked_at'), 'retry_child_check_required')
                for tid in owner['target_track_ids']:
                    require(repo.find(track_id=tid) is not None, 'automation_target_not_found')
                for tid in owner['target_track_ids']:
                    repo.command(tid, 'append_outbox_action', owner=owner)
                result = {'status':'automation_bound', 'owner':owner}
            elif args.command == 'outbox':
                result = {'status':'outbox_drained', 'actions':drain(repo, track_id=args.track_id)}
            elif args.command == 'ack-outbox':
                result = repo.ack_outbox(args.track_id, args.outbox_id, success=True, receipt=read_json(args.receipt))
        if getattr(args, 'output', None) and args.output.is_file():
            register(args.output,args.state)
            result['output_path'] = str(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 6 if result.get('status') in {'available_enqueue_failed','accepted_receipt_commit_failed','recovery_failed','recovery_required','blocked'} else 0
    except Exception as exc:
        failure = {'status':'workflow_error', 'error_type':type(exc).__name__, 'error':str(exc)}
        if hasattr(exc, 'recovery'):
            failure['recovery'] = asdict(exc.recovery)
        print(json.dumps(failure, ensure_ascii=False))
        return 6

if __name__ == '__main__':
    raise SystemExit(run())
