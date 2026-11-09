"""Read-only episode worklist for an explicitly scoped panel run."""
import re


def verified_finds(saved, show):
    entries = list(saved.get('finds', []))
    known = {r['infoHash'] for r in entries}
    for op in show.get('operations', {}).values():
        info_hash = op.get('info_hash', '')
        if (op.get('kind') == 'regular' and op.get('review_manifest', {}).get('reviewed') is True
                and re.fullmatch(r'[0-9a-f]{40}', info_hash) and info_hash not in known
                and type(op.get('episode')) is int and op['episode'] > 0):
            entries.append({'infoHash': info_hash, 'episode': op['episode'], 'scope': 'regular',
                            'sourceUrl': op.get('request', {}).get('source_url'),
                            'checkedAt': op.get('receipt', {}).get('checked_at')})
            known.add(info_hash)
    return entries


def worklist(state, plan, through):
    from dsh_panel_run import read, result_path
    from dsh_panel_download import compatible
    if type(through) is not int or not 1 <= through <= 10000:
        raise ValueError('invalid_latest_episode')
    if plan['mode'] != 'missing_episodes':
        raise ValueError('missing_mode_required')
    saved = read(result_path(state, plan['id']), {})
    show = next((s for s in read(state, {}).get('shows', []) if s.get('track_id') == plan['trackId']), {})
    entries = verified_finds(saved, show)
    recorded = sorted({r['episode'] for r in entries if r.get('scope') == 'regular'
                       and type(r.get('episode')) is int and 1 <= r['episode'] <= through})
    accepted = {r.get('infoHash') for r in saved.get('completed', [])}
    accepted.update(h for h, v in saved.get('downloads', {}).items() if v.get('status') in {'download_submitted', 'completed'})
    accepted.update(op.get('info_hash') for op in show.get('operations', {}).values()
                    if op.get('receipt', {}).get('accepted') or op.get('committed'))
    # One reusable result per episode, not every alternate encode in its history.
    choices = {}
    for entry in sorted(entries, key=lambda r: r.get('checkedAt') or ''):
        if entry.get('episode') in recorded:
            choices[entry['episode']] = entry
    pending = [dict(episode=n, info_hash=r['infoHash']) for n, r in sorted(choices.items())
               if r['infoHash'] not in accepted and compatible(r, plan)]
    return {'status': 'targets_ready', 'through_episode': through, 'recorded_episodes': recorded,
            'missing_episodes': [n for n in range(1, through + 1) if n not in set(recorded)],
            'pending_downloads': pending}


def allows_backfill(state, track_id):
    from dsh_panel_run import read
    return any(p.get('trackId') == track_id and p.get('mode') == 'missing_episodes'
               and not p.get('deleted') and not p.get('paused')
               for p in read(state.with_suffix('.plans.json'), {}).get('plans', []))
