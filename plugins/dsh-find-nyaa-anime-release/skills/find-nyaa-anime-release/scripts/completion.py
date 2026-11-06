"""Reviewed broadcast-boundary evidence, independent of release availability."""
from __future__ import annotations

import calendar
import copy
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def end_date(value):
    """Preserve fuzzy AniList dates; never manufacture a missing month/day."""
    if not value:
        return None, None
    if isinstance(value, dict):
        y, m, d = (value.get(k) for k in ('year', 'month', 'day'))
        if not y:
            return None, None
        value = f'{y:04d}' + (f'-{m:02d}' if m else '') + (f'-{d:02d}' if m and d else '')
    if not isinstance(value, str):
        raise ValueError('end_date must be an ISO date or partial date')
    parts = value.split('-')
    if len(parts) not in (1, 2, 3):
        raise ValueError('invalid end_date')
    y, m, d = [int(p) for p in parts] + [1] * (3 - len(parts))
    date(y, m, d)
    expected = f'{y:04d}' + (f'-{m:02d}' if len(parts) >= 2 else '') + (f'-{d:02d}' if len(parts) == 3 else '')
    if value != expected:
        raise ValueError('end_date must use ISO precision')
    return value, ('year', 'month', 'day')[len(parts) - 1]


def metadata(media):
    value, precision = end_date(media.get('endDate'))
    return dict(end_date=value, date_precision=precision,
                confirmed=media.get('status') == 'FINISHED', final_episode=media.get('episodes'),
                source_url=f"https://anilist.co/anime/{media['id']}" if media.get('id') else None,
                source_kind='metadata', checked_at=datetime.now(timezone.utc).isoformat())


def read_evidence(path: Path, resolved, season):
    evidence = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(evidence, dict):
        raise ValueError('completion evidence must be an object')
    matched = False
    for key in ('anilist_id', 'bangumi_id'):
        supplied, actual = evidence.get(key), getattr(resolved, key)
        if supplied is not None:
            if type(supplied) is not int or supplied <= 0 or (actual is not None and supplied != actual):
                raise ValueError('completion evidence work ID mismatch')
            matched |= supplied == actual
    if not matched or evidence.get('season') != season:
        raise ValueError('completion evidence must match a known work ID and exact season')
    if evidence.get('reviewed') is not True or type(evidence.get('confirmed')) is not bool:
        raise ValueError('completion evidence requires reviewed=true and confirmed boolean')
    if evidence.get('source_kind') not in ('official', 'broadcaster'):
        raise ValueError('reviewed evidence requires official or broadcaster source')
    url = urlparse(evidence.get('source_url', ''))
    if url.scheme != 'https' or not url.hostname or not evidence.get('evidence_text'):
        raise ValueError('completion evidence requires HTTPS source and supporting text')
    checked = datetime.fromisoformat(evidence.get('checked_at', ''))
    if checked.tzinfo is None or checked > datetime.now(timezone.utc):
        raise ValueError('checked_at must be a non-future timezone-aware timestamp')
    n = evidence.get('final_episode')
    if type(n) is not int or n <= 0:
        raise ValueError('completion evidence requires positive integer final_episode')
    value, precision = end_date(evidence.get('end_date'))
    if evidence['confirmed'] and value and value > date.today().isoformat()[:len(value)]:
        raise ValueError('future end date cannot confirm completed broadcasting')
    return {**evidence, 'end_date': value, 'date_precision': precision}


def confirmed(resolved):
    evidence = resolved.completion
    return bool(not getattr(resolved, 'identity_conflicts', []) and not evidence.get('conflict') and
                (evidence.get('confirmed') is True or resolved.status == 'FINISHED') and
                type(resolved.episodes) is int and resolved.episodes > 0)


def apply_evidence(resolved, evidence):
    resolved.completion = copy.deepcopy(evidence)
    resolved.episodes = evidence['final_episode']
    resolved.status = 'FINISHED' if evidence['confirmed'] else 'RELEASING'
    resolved.current = not evidence['confirmed']
    resolved.trackable = not evidence['confirmed'] and resolved.format in ('TV', 'TV_SHORT', 'ONA')


def review_reasons(resolved, completed, today):
    ev = resolved.completion
    if ev.get('conflict'):
        return ['conflicting_completion_evidence']
    if confirmed(resolved):
        return []
    reasons = []
    if type(resolved.episodes) is int and completed is not None and completed >= resolved.episodes:
        reasons.append('known_episode_count_reached')
    value = ev.get('end_date')
    if value:
        parts = [int(x) for x in value.split('-')]
        y = parts[0]
        m = parts[1] if len(parts) > 1 else 12
        d = parts[2] if len(parts) > 2 else calendar.monthrange(y, m)[1]
        if today >= date(y, m, d):
            reasons.append('planned_end_date_due')
    return reasons


def mark_completed(show, resolved):
    show.update(status='completed', tracking_status='completed', airing=False,
                next_episode=None, total_episodes=resolved.episodes,
                completion=copy.deepcopy(resolved.completion),
                updated_at=datetime.now(timezone.utc).isoformat())
    show['notes'] = f'Final regular episode {resolved.episodes} delivered; season tracking completed.'
    show.pop('pending_download', None)


def automation_cleanup(report):
    """Advisory only: the Agent must check the owning task's full prompt and use its API."""
    children = report.get('results') if report.get('status') == 'batch' else [report]
    children = children if isinstance(children, list) else []
    def delivered(child):
        if not isinstance(child, dict):
            return False
        progress = child.get('progress') or {}
        finale = (child.get('completion') or {}).get('final_episode')
        episode = progress.get('after_episode')
        return (child.get('status') == 'completed'
                and child.get('state_update') in ('completed', 'unchanged')
                and type(finale) is int and finale > 0
                and type(episode) is int and episode >= finale
                and 'next_episode' in progress and progress['next_episode'] is None)
    ready = bool(children) and all(delivered(child) for child in children)
    return {'action': 'delete_owning_automation' if ready else 'keep',
            'eligible': ready, 'executed': False,
            'requires': ['exact_automation_id', 'full_prompt_scope_completed',
                         'app_delete_success'],
            'reason': 'all_reported_shows_delivered_and_persisted' if ready else 'incomplete_or_read_only'}
