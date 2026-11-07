"""Bangumi subcommands shared by Codex and DSH."""
from .bangumi_client import connect, config_path, load_config, setup_hint
from .bangumi import BangumiSync, COLLECTION_TYPES


def add_parser(sub):
    root = sub.add_parser('bangumi', help='Read personal library/reviews or mirror watched episodes')
    commands = root.add_subparsers(dest='bangumi_command', required=True)
    q = commands.add_parser('connect')
    auth = q.add_mutually_exclusive_group()
    auth.add_argument('--token-env', default='BANGUMI_ACCESS_TOKEN')
    auth.add_argument('--token-file')
    commands.add_parser('status')
    q = commands.add_parser('list')
    q.add_argument('--collection', choices=COLLECTION_TYPES, default='watching')
    q.add_argument('--query')
    q.add_argument('--min-rating', type=int, default=0)
    q.add_argument('--comments-only', action='store_true')
    q.add_argument('--limit', type=int, default=30)
    q.add_argument('--offset', type=int, default=0)
    q.add_argument('--refresh', action='store_true')
    q = commands.add_parser('progress')
    q.add_argument('--subject-id', type=int, required=True)
    q.add_argument('--episode-offset', type=int, default=0)
    q = commands.add_parser('bind')
    q.add_argument('--track-id', required=True)
    q.add_argument('--subject-id', type=int, required=True)
    q.add_argument('--episode-offset', type=int, default=0)
    q.add_argument('--add-watching', action='store_true')
    q = commands.add_parser('pull')
    q.add_argument('--track-id')
    q.add_argument('--refresh', action='store_true')
    q = commands.add_parser('flush')
    q.add_argument('--track-id')
    q = commands.add_parser('watched')
    target = q.add_mutually_exclusive_group(required=True)
    target.add_argument('--track-id')
    target.add_argument('--subject-id', type=int)
    q.add_argument('--episode-offset', type=int, default=0)
    scope = q.add_mutually_exclusive_group(required=True)
    scope.add_argument('--episode', type=int)
    scope.add_argument('--through', type=int)
    scope.add_argument('--complete', action='store_true')


def run(args, repo):
    name = args.bangumi_command
    if name == 'connect':
        return connect(repo.path, token_env=args.token_env or 'BANGUMI_ACCESS_TOKEN', token_file=args.token_file)
    if name == 'status':
        config = load_config(repo.path)
        return {'status': 'bangumi_connected' if config else 'bangumi_not_connected',
                'account_id': config.get('account_id') if config else None,
                'username': config.get('username') if config else None,
                'delivery_as_watched': True, 'config_path': str(config_path(repo.path)),
                **({} if config else setup_hint())}
    service = BangumiSync(repo)
    if name == 'list':
        return service.collections(collection=args.collection, query=args.query, min_rating=args.min_rating,
                                   comments_only=args.comments_only, limit=args.limit, offset=args.offset, refresh=args.refresh)
    if name == 'progress':
        return service.progress(args.subject_id, episode_offset=args.episode_offset)
    if name == 'bind':
        return service.bind(args.track_id, args.subject_id, episode_offset=args.episode_offset, add_watching=args.add_watching)
    if name == 'watched':
        if args.subject_id is not None:
            return service.watched_subject(args.subject_id, episode_offset=args.episode_offset,
                                           episode=args.episode, through=args.through, complete=args.complete)
        return service.watched(args.track_id, episode=args.episode, through=args.through, complete=args.complete)
    if name == 'flush':
        from .outbox import drain
        actions = drain(repo, track_id=args.track_id, bangumi=service, kinds={'bangumi_watched'})
        return {'status': 'bangumi_sync_pending' if any(a['status'] != 'done' for a in actions) else 'bangumi_synced', 'actions': actions}
    if name == 'pull':
        ids = [args.track_id] if args.track_id else [s['track_id'] for s in repo.read()['shows'] if s.get('bangumi')]
        results = []
        for tid in ids:
            try:
                results.append(service.refresh_track(tid, refresh=args.refresh))
            except Exception as exc:
                results.append({'track_id': tid, 'status': 'bangumi_sync_failed', 'error': str(exc)})
        return {'status': 'bangumi_sync_partial' if any(r['status'] == 'bangumi_sync_failed' for r in results) else 'bangumi_synced',
                'tracks': results}
    raise ValueError('unknown_bangumi_command')
