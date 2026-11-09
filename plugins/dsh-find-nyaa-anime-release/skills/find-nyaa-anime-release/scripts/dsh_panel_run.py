"""Panel-only execution context and verified search/download history."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import time
import io
from contextlib import redirect_stdout
from pathlib import Path

from anime_release.storage import atomic_json, file_lock
from dsh_paths import state_path, download_directory, qb_backup_directory

_context = None


def read(path, default):
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('panel_state_too_large')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return default


def result_path(state, plan_id):
    if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}', plan_id):
        raise ValueError('invalid_plan_id')
    return state.with_suffix('.panel-results') / (plan_id + '.json')


def load_plan(state, plan_id):
    plans = read(state.with_suffix('.plans.json'), {}).get('plans', [])
    plan = next((p for p in plans if p['id'] == plan_id and not p.get('deleted')), None)
    if not plan or plan.get('paused'):
        raise ValueError('plan_paused_or_deleted')
    return plan


def update_result(state, plan, values):
    file = result_path(state, plan['id'])
    with file_lock(file.with_suffix('.lock')):
        saved = read(file, {'version': 1, 'finds': [], 'completed': []})
        saved.update(values)
        atomic_json(file, saved)
    return saved


def start_watching(state, plan, subject_id=None):
    from watch_v3.bangumi_client import configured_client, load_config
    subject_id = subject_id or plan.get('bangumiSubjectId')
    if not subject_id:
        return {'startSync': 'binding_required'}
    try:
        config = load_config(state)
        if config is None:
            raise ValueError('not_configured')
        client = configured_client(config)
        subject = client.subject(subject_id)
        if subject.get('id') != subject_id or subject.get('type') != 2:
            raise ValueError('subject_mismatch')
        try:
            collection = client.collection(config['username'], subject_id)
        except Exception as exc:
            if str(exc) != 'bangumi_http_404':
                raise
            collection = {}
        if collection.get('type') != 2:
            if collection.get('type') != 3:
                load_plan(state, plan['id'])
                client.set_collection(subject_id, 3)
            if client.collection(config['username'], subject_id).get('type') != 3:
                raise ValueError('write_not_confirmed')
        return {'startSync': 'synced', 'startedCollectionType': 2 if collection.get('type') == 2 else 3,
                'bangumiSubjectId': subject_id}
    except Exception:
        return {'startSync': 'pending', 'bangumiSubjectId': subject_id}


def connection_revision(state):
    """Invalidate retries on config/credential changes without storing secrets."""
    from watch_v3.bangumi_client import config_path, load_config
    def stamp(path):
        try:
            stat = Path(path).stat()
            return [stat.st_mtime_ns, stat.st_size]
        except OSError:
            return None
    key = [stamp(config_path(state))]
    try:
        config = load_config(state) or {}
        key.append(stamp(config['token_file']) if config.get('token_file')
                   else os.environ.get(config.get('token_env', 'BANGUMI_ACCESS_TOKEN'), ''))
    except (ValueError, OSError, RuntimeError):
        key.append('unavailable')
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def ensure_watching(state, plan, subject_id=None):
    from datetime import datetime, timezone
    file = result_path(state, plan['id'])
    # Commands in one search share both success and failure results. A new plan
    # revision or changed credentials retries immediately; otherwise wait 5 minutes.
    with file_lock(file.with_suffix('.start.lock')):
        previous = read(file, {})
        subject_id = subject_id or plan.get('bangumiSubjectId') or previous.get('bangumiSubjectId')
        key = [plan['revision'], subject_id, connection_revision(state)]
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(previous['startedAt'])).total_seconds()
        except (KeyError, TypeError, ValueError):
            age = -1
        if previous.get('startKey') == key and 0 <= age < 300:
            return previous
        load_plan(state, plan['id'])
        return update_result(state, plan, {**start_watching(state, plan, subject_id),
            'startedAt': datetime.now(timezone.utc).isoformat(), 'startedRevision': plan['revision'], 'startKey': key})


def record_found(report, *, show=None, review=None, review_path=None):
    """Called only after the existing evidence validator passed, never from a saved report."""
    if _context is None or report.get('status') != 'found' or report.get('eligibility') != 'passed':
        return
    state, plan_id = _context
    plan = load_plan(state, plan_id)
    if show and show.get('track_id') != plan.get('trackId'):
        raise ValueError('panel_track_mismatch')
    if show and plan['mode'] in {'season_batch', 'movie'}:
        raise ValueError('panel_package_required')
    from datetime import datetime, timezone
    from qbittorrent_submit import extract_btih
    selected = report.get('selected') or {}
    info_hash = report.get('info_hash') or extract_btih(selected.get('magnet') or '')
    if not info_hash or not re.fullmatch(r'[0-9a-fA-F]{40}', info_hash):
        raise ValueError('panel_hash_required')
    broadcast = (show or {}).get('broadcast', {})
    completion = broadcast.get('completion', {})
    scope = report.get('scope') if not show else None
    if not show and (not isinstance(scope, dict) or scope.get('kind') not in {'season', 'movie'}):
        raise ValueError('panel_scope_required')
    if not show and (plan['mode'] not in {'season_batch', 'movie'} or plan['mode'] == 'movie' and scope.get('kind') != 'movie'):
        raise ValueError('panel_scope_mismatch')
    if not show and scope.get('title') != plan['title'] and not (plan.get('bangumiSubjectId') and scope.get('bangumi_id') == plan['bangumiSubjectId']):
        raise ValueError('panel_work_mismatch')
    if not show and plan.get('season') and scope.get('season') != plan['season']:
        raise ValueError('panel_season_mismatch')
    subject_id = ((show or {}).get('bangumi') or {}).get('subject_id') or ((show or {}).get('identity', {}).get('provider_bindings', {}).get('bangumi') or {}).get('entry_id') or (scope or {}).get('bangumi_id')
    if plan.get('bangumiSubjectId') and subject_id and subject_id != plan['bangumiSubjectId']:
        raise ValueError('panel_subject_mismatch')
    episode = report.get('target_episode') if show else None
    total = completion.get('final_episode') if completion.get('confirmed') else None
    entry = {'infoHash': info_hash.lower(), 'episode': episode,
             'scope': 'regular' if show else scope['kind'],
             'sourceUrl': selected.get('url') or report.get('source_url'),
             'checkedAt': datetime.now(timezone.utc).isoformat(),
             'finalEpisode': total if type(total) is int and total > 0 else None}
    file = result_path(state, plan_id)
    entry.update(title=selected.get('title'), size=selected.get('size'), qualityPolicy=report.get('quality_policy', {}))
    if review_path is not None and review is not None:
        from package_release import durable_review
        kept, _ = durable_review(review_path, review, file.parent / plan_id / entry['infoHash'])
        entry['reviewPath'] = str(kept)
    with file_lock(file.with_suffix('.lock')):
        saved = read(file, {'version': 1, 'finds': [], 'completed': []})
        saved['finds'] = [f for f in saved['finds'] if f['infoHash'] != entry['infoHash']] + [entry]
        atomic_json(file, saved)
    if subject_id and not plan.get('bangumiSubjectId'):
        ensure_watching(state, plan, subject_id)


def files_complete(info_hash, root, backup):
    """Require matching torrent, qB completion evidence AND actual files below the fixed root."""
    from qbittorrent_submit import _decode_bencode, inspect_fastresume
    if not inspect_fastresume(backup / (info_hash + '.fastresume'))['download_complete']:
        return False
    torrent = backup / (info_hash + '.torrent')
    if not torrent.is_file() or torrent.stat().st_size > 16 * 1024 * 1024:
        return False
    from qbittorrent_submit import _acceptance_evidence
    if not _acceptance_evidence(info_hash, backup).get('torrent_valid'):
        return False
    value, _ = _decode_bencode(torrent.read_bytes())
    info = value.get(b'info', {})
    name = info.get(b'name.utf-8', info.get(b'name', b'')).decode('utf-8')
    files = info.get(b'files')
    entries = [( [name] + [p.decode('utf-8') for p in f.get(b'path.utf-8', f.get(b'path', []))], f.get(b'length')) for f in files] if files else [([name], info.get(b'length'))]
    if not entries:
        return False
    root = root.resolve()
    for parts, size in entries:
        if not parts or any(not p or p in {'.', '..'} or '/' in p or '\\' in p or ':' in p for p in parts):
            return False
        path = root.joinpath(*parts).resolve()
        if not path.is_relative_to(root) or type(size) is not int or size < 0 or not path.is_file() or path.stat().st_size != size:
            return False
    return True


def web_files_complete(client, info_hash, root, observed=None):
    from urllib.parse import urlencode
    observed = observed or client.inspect(info_hash)
    torrent = observed.details.get('torrent')
    if not observed.verified or not torrent or torrent.get('amount_left') != 0 or torrent.get('progress') != 1:
        return False
    if Path(torrent.get('save_path', '')).resolve() != root.resolve():
        return False
    files = json.loads(client._request('/api/v2/torrents/files?' + urlencode({'hash': info_hash})))
    if not isinstance(files, list) or not files:
        return False
    for item in files:
        parts = str(item.get('name', '')).replace('\\', '/').split('/')
        if any(not p or p in {'.', '..'} or ':' in p for p in parts):
            return False
        path = root.joinpath(*parts).resolve()
        if item.get('progress') != 1 or not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size != item.get('size'):
            return False
    return True


def snapshot(state):
    plans = read(state.with_suffix('.plans.json'), {}).get('plans', [])
    setup = read(state.with_suffix('.setup.json'), {})
    root = Path(setup.get('download_directory') or download_directory())
    backup = qb_backup_directory()
    core = read(state, {}).get('shows', [])
    web = None
    deadline = time.monotonic() + 6
    web_failed = False
    output = {}
    for plan in plans:
        if plan.get('deleted'):
            continue
        file = result_path(state, plan['id'])
        with file_lock(file.with_suffix('.lock')):
            saved = read(file, {'version': 1, 'finds': [], 'completed': []})
            before = copy.deepcopy(saved)
            show = next((s for s in core if s.get('track_id') == plan.get('trackId')), {})
            # Migrate validated operations, but never broadcast latest/target into found progress.
            from dsh_panel_targets import verified_finds
            saved['finds'] = verified_finds(saved, show)
            completed = {r['infoHash']: r for r in saved['completed']}
            live_downloads = {}
            check_incomplete = False
            for entry in saved['finds']:
                try:
                    if entry['infoHash'] in completed:
                        continue
                    complete = files_complete(entry['infoHash'], root, backup)
                    if not complete and setup.get('client') == 'webapi' and (web_failed or time.monotonic() >= deadline):
                        check_incomplete = True
                    if not complete and setup.get('client') == 'webapi' and setup.get('web_url') and not web_failed and time.monotonic() < deadline:
                        try:
                            if web is None:
                                from watch_v3.clients import QbittorrentWebApiClient
                                web = QbittorrentWebApiClient(setup['web_url'], username=setup.get('web_username'), password=setup.get('web_password'), timeout=1)
                                web.preflight()
                            observed = web.inspect(entry['infoHash'])
                            torrent = observed.details.get('torrent') or {}
                            if observed.verified:
                                progress = torrent.get('progress')
                                live_downloads[entry['infoHash']] = {
                                    'status': 'downloading',
                                    'progress': progress if type(progress) in (int, float) and 0 <= progress <= 1 else None,
                                    'state': 'paused' if str(torrent.get('state', '')).startswith(('paused', 'stopped')) else 'active'}
                            complete = web_files_complete(web, entry['infoHash'], root, observed)
                        except Exception:
                            web_failed = True
                            check_incomplete = True
                    if complete:
                        completed[entry['infoHash']] = entry
                except (OSError, ValueError, UnicodeError, KeyError):
                    pass
            saved['completed'] = list(completed.values())
            if saved != before:
                atomic_json(file, saved)
        latest = max((r for r in saved['finds'] if r.get('scope') == 'regular' and type(r.get('episode')) is int), key=lambda r: r['episode'], default=None)
        package = max((r for r in saved['finds'] if r.get('scope') in {'season', 'movie'}), key=lambda r: r.get('checkedAt') or '', default=None)
        completion = show.get('broadcast', {}).get('completion', {})
        if latest and completion.get('confirmed') is True and type(completion.get('final_episode')) is int:
            latest = {**latest, 'finalEpisode': completion['final_episode']}
        from dsh_panel_download import compatible
        def public_entry(entry):
            if not entry:
                return None
            value = {k: v for k, v in entry.items() if k not in {'reviewPath', 'qualityPolicy'}}
            value['canDownload'] = compatible(entry, plan)
            return value
        def download_status(entry):
            if not entry:
                return None
            info_hash = entry['infoHash']
            delivery = saved.get('downloads', {}).get(info_hash) or {'status': 'not_submitted'}
            op = next((op for op in show.get('operations', {}).values() if op.get('info_hash') == info_hash), {})
            if op.get('receipt', {}).get('accepted') or op.get('committed'):
                delivery = {'status': 'download_submitted'}
            elif op.get('status') == 'failed':
                delivery = {'status': 'download_pending'}
            delivery = live_downloads.get(info_hash, delivery)
            if info_hash in completed:
                delivery = {'status': 'completed', 'progress': 1}
            elif check_incomplete:
                delivery = {**delivery, 'unconfirmed': True}
            return delivery
        by_episode = {}
        for entry in sorted(saved['finds'], key=lambda r: r.get('checkedAt') or ''):
            if entry.get('scope') == 'regular' and type(entry.get('episode')) is int:
                by_episode[entry['episode']] = entry
        resources = [{**public_entry(entry), 'download': download_status(entry)} for _, entry in sorted(by_episode.items())]
        output[plan['id']] = {k: saved[k] for k in ('startSync', 'startedCollectionType', 'startedAt', 'bangumiSubjectId') if k in saved}
        output[plan['id']].update(latestFound=public_entry(latest), latestPackage=public_entry(package), foundPackage=package is not None,
                                download=download_status(package or latest), lastSearch=saved.get('lastSearch'),
                                resources=resources if plan['mode'] == 'missing_episodes' else [],
                                recordedEpisodes=sorted(by_episode),
                                completedEpisodes=sorted({r['episode'] for r in saved['completed'] if r.get('episode')}),
                                completedDownloads=len(saved['completed']),
                                downloadCheckIncomplete=check_incomplete,
                                completedPackage=any(r['scope'] in {'season', 'movie'} for r in saved['completed']))
    return output


def main(argv=None):
    global _context
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=state_path())
    parser.add_argument('--plan-id')
    parser.add_argument('--scheduled', action='store_true')
    parser.add_argument('command', choices=['snapshot', 'targets', 'watch', 'package', 'download'])
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'snapshot':
        print(json.dumps(snapshot(args.state)))
        return 0
    if args.command == 'watch' and any(arg in {'watched', 'flush', 'finalize'} for arg in args.args[:2]):
        raise ValueError('panel_manual_sync_required')
    plan = load_plan(args.state, args.plan_id)
    if args.scheduled and plan.get('schedulePaused'):
        raise ValueError('automatic_run_disabled')
    previous_context = _context
    _context = (args.state, args.plan_id)
    try:
        return execute(args, plan)
    finally:
        _context = previous_context


def execute(args, plan):
    if args.command == 'targets':
        from dsh_panel_targets import worklist
        parser = argparse.ArgumentParser()
        parser.add_argument('--through', type=int, required=True)
        print(json.dumps(worklist(args.state, plan, parser.parse_args(args.args).through)))
        return 0
    delivery = args.command == 'download' or (args.command == 'package' and args.args[:1] in [['deliver'], ['recover']])
    if args.scheduled and not delivery and plan['mode'] in {'season_batch', 'movie'}:
        saved = read(result_path(args.state, plan['id']), {})
        if any(r.get('scope') in {'season', 'movie'} for r in saved.get('finds', [])):
            print(json.dumps({'status': 'package_already_found'}))
            return 0
    if args.command == 'download':
        from dsh_panel_download import submit
        if len(args.args) != 1 or not re.fullmatch(r'[a-f0-9]{40}', args.args[0]):
            raise ValueError('invalid_hash')
        print(json.dumps(submit(args.state, args.plan_id, args.args[0])))
        return 0
    ensure_watching(args.state, plan)
    def capture(call):
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                code = call()
        finally:
            text = output.getvalue()
            print(text, end='')
            try:
                result = json.loads(text)
                status = result.get('status')
                # Only a terminal search/validation result becomes an inbox event.
                if status in {'found', 'no_rss_candidates', 'no_nyaa_release_for_target', 'release_unqualified',
                              'needs_confirmation', 'latest_unresolved', 'not_yet_aired', 'resolver_failed', 'search_incomplete'}:
                    from datetime import datetime, timezone
                    update_result(args.state, plan, {'lastSearch': {'status': status, 'checkedAt': datetime.now(timezone.utc).isoformat()}})
                accepted = result.get('receipt') or {}
                info_hash = accepted.get('info_hash')
                if accepted.get('accepted') is True and status in {'delivery_recorded', 'already_accepted', 'recovered', 'accepted_receipt_commit_failed'}:
                    file = result_path(args.state, plan['id'])
                    with file_lock(file.with_suffix('.lock')):
                        saved = read(file, {})
                        if any(r.get('infoHash') == info_hash for r in saved.get('finds', [])):
                            saved.setdefault('downloads', {})[info_hash] = {'status': 'download_submitted'}
                            atomic_json(file, saved)
            except (ValueError, TypeError, AttributeError):
                pass
        return code
    if args.command == 'watch':
        from watch_v3.cli import run
        if args.args and args.args[0] == 'review' and plan['mode'] in {'latest_regular', 'next_tracked', 'missing_episodes'}:
            expected = 'specific_episode' if plan['mode'] == 'missing_episodes' else 'latest_regular'
            if '--intent' in args.args:
                intent = args.args[args.args.index('--intent') + 1]
            elif '--manifest' in args.args:
                intent = read(Path(args.args[args.args.index('--manifest') + 1]), {}).get('intent')
            else:
                intent = None
            if intent != expected:
                raise ValueError('panel_search_scope_mismatch')
        result = capture(lambda: run(['--state', str(args.state), *args.args]))
        if not plan.get('bangumiSubjectId'):
            current = load_plan(args.state, args.plan_id)
            show = next((s for s in read(args.state, {}).get('shows', []) if s.get('track_id') == current.get('trackId')), {})
            subject_id = (show.get('bangumi') or {}).get('subject_id') or (show.get('identity', {}).get('provider_bindings', {}).get('bangumi') or {}).get('entry_id')
            if subject_id:
                ensure_watching(args.state, current, subject_id)
        return result
    from package_release import main as package_main
    return capture(lambda: package_main(args.args))


if __name__ == '__main__':
    # Imported validator hooks must share this execution context, not a second module.
    sys.modules['dsh_panel_run'] = sys.modules[__name__]
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'panel_operation_failed', 'error': type(error).__name__}))
        raise SystemExit(3)
