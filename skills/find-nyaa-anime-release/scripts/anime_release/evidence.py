"""Provider evidence validation and bounded binding repair, independent of state IO."""
import json
import re
from datetime import datetime, timezone
from dataclasses import asdict
from urllib.parse import urlsplit
from .models import MetadataEvidence, WorkIdentity, WorkflowError
from release_identity import parse_release_identity, normalize_season_number
from tracked_identity import norm

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def part_of(titles):
    parts = {int(m.group(1) or m.group(2)) for title in titles
             for m in re.finditer(r'\b(?:part|cour)\s*(\d+)\b|第\s*(\d+)\s*(?:部|クール)', title, re.I)}
    if len(parts) == 1:
        return str(next(iter(parts)))
    for title in titles:
        named = re.search(r'\s+([^\s]+[篇編])\s*$', title)
        if named:
            return 'named:' + named.group(1)
    return None

def from_raw(provider, payload, revision=0, checked_at=None):
    from .providers import bangumi_item_names
    if provider == 'anilist':
        titles = tuple(str(v) for v in (payload.get('title') or {}).values() if v)
        # Only source-authored titles establish the installment; synonyms aid search.
        fmt = payload.get('format')
        url = f'https://anilist.co/anime/{payload.get("id")}'
    elif provider == 'bangumi':
        titles = tuple(bangumi_item_names(payload))
        platform = str(payload.get('platform') or '').upper()
        fmt = {'WEB': 'ONA'}.get(platform, platform) or None
        url = f'https://bgm.tv/subject/{payload.get("id")}'
        if payload.get('type') not in (None, 2):
            fmt = 'NOT_ANIME'
    else:
        raise WorkflowError('metadata', 'unsupported_provider')
    seasons = {parse_release_identity(title).season for title in titles} - {None}
    season = f'S{next(iter(seasons)):02d}' if len(seasons) == 1 else None
    if len(seasons) > 1:
        raise WorkflowError('metadata', 'source_season_conflict', False, titles)
    return MetadataEvidence(provider, str(payload.get('id') or ''), url, checked_at or timestamp(),
        titles, season, part_of(titles), fmt, json.dumps(payload, ensure_ascii=False), revision)

def validate(identity, evidence):
    reasons = []
    if evidence.provider in {'anilist', 'bangumi'}:
        try:
            raw = from_raw(evidence.provider, json.loads(evidence.payload_json),
                evidence.identity_revision, evidence.checked_at)
            if any(getattr(raw, key) != getattr(evidence, key) for key in
                ('entry_id', 'source_url', 'titles', 'season', 'part', 'format')):
                reasons.append('source_payload_mismatch')
        except (ValueError, TypeError, AttributeError, WorkflowError):
            reasons.append('source_payload_invalid')
    elif evidence.provider != 'official':
        reasons.append('unsupported_provider')
    try:
        checked = datetime.fromisoformat(evidence.checked_at)
        if checked.tzinfo is None or checked.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
            reasons.append('invalid_evidence_time')
    except (ValueError, TypeError):
        reasons.append('invalid_evidence_time')
    if not evidence.entry_id or not evidence.titles or not evidence.format:
        reasons.append('source_identity_incomplete')
    if identity.format and evidence.format and identity.format != evidence.format:
        reasons.append('format_mismatch')
    expected = normalize_season_number(identity.season)
    actual = normalize_season_number(evidence.season)
    if expected and (actual != expected and not (expected == 1 and actual is None)):
        reasons.append('season_mismatch' if actual else 'season_unverified')
    if identity.part != evidence.part:
        reasons.append('part_mismatch')
    # No similarity scores, query text, search aliases, IDs or RELEASING status.
    names = {norm(n) for n in (identity.title, *identity.aliases) if n}
    if not names.intersection(norm(n) for n in evidence.titles):
        reasons.append('work_title_mismatch')
    if reasons:
        raise WorkflowError('metadata', 'identity_conflict', False,
            ({'reasons': reasons, 'expected': asdict(identity), 'received': asdict(evidence)},),
            'verify_locked_work_binding')
    return evidence


def reviewed_official(path, identity):
    """Agent attestation after inspecting an official work page, never a web fetch."""
    from pathlib import Path
    try:
        payload = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        url = urlsplit(payload.get('source_url', ''))
        checked = datetime.fromisoformat(payload.get('checked_at', ''))
    except (ValueError, TypeError, AttributeError) as exc:
        raise WorkflowError('metadata', 'invalid_official_identity_attestation') from exc
    if (payload.get('reviewed') is not True or payload.get('source_kind') not in {'official', 'broadcaster'}
        or url.scheme != 'https' or not url.hostname or url.username or url.password
        or url.hostname in {'anilist.co', 'bgm.tv', 'bangumi.tv', 'nyaa.si'}
        or checked.tzinfo is None or not payload.get('evidence_text')
        or payload.get('track_id') != identity.track_id or payload.get('identity_revision') != identity.revision):
        raise WorkflowError('metadata', 'invalid_official_identity_attestation')
    titles = tuple(payload.get('titles', []))
    if not titles or any(not isinstance(t,str) for t in titles):
        raise WorkflowError('metadata', 'official_titles_missing')
    seasons = {parse_release_identity(t).season for t in titles} - {None}
    expected = normalize_season_number(payload.get('season'))
    if seasons and seasons != {expected}:
        raise WorkflowError('metadata', 'official_season_conflict')
    evidence = MetadataEvidence('official', payload['source_url'], payload['source_url'], payload['checked_at'],
        titles, payload.get('season'), payload.get('part'), payload.get('format'),
        json.dumps(payload,ensure_ascii=False), identity.revision)
    return validate(identity,evidence)

def unique_repair(identity, candidates):
    verified = []
    for evidence in candidates:
        try:
            verified.append(validate(identity, evidence))
        except WorkflowError:
            pass
    grouped = {}
    for e in verified:
        grouped.setdefault(e.provider, {})[e.entry_id] = e
    if len(grouped) < 2 or any(len(entries) != 1 for entries in grouped.values()):
        raise WorkflowError('metadata', 'binding_repair_ambiguous', False,
                            tuple(asdict(e) for e in candidates), 'review_independent_identity_evidence')
    evidence_list = [asdict(next(iter(entries.values()))) for entries in grouped.values()]
    # Both providers independently validated the same local work/season/part/type.
    return {provider: {'entry_id': int(next(iter(entries))), 'status': 'verified',
                      'evidence': evidence_list, 'checked_at': timestamp()}
            for provider, entries in grouped.items() if provider in {'anilist','bangumi'}}
