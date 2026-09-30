"""Lossless page evidence for Agent review; no query rewriting or eligibility filter."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from nyaa_client import NyaaClient, build_listing_url, parse_listing, nyaa_id_from_url


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class Pagination(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pages = set()

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        parsed = urlsplit(href)
        if parsed.netloc and parsed.netloc != 'nyaa.si':
            return
        if parsed.path not in ('', '/'):
            return
        for value in parse_qs(parsed.query).get('p', []):
            if value.isdigit():
                self.pages.add(int(value))


def listing(query, page=1, *, client=None, timeout=20):
    if not isinstance(query, str) or not query.strip() or page < 1:
        raise ValueError('A nonempty exact query and positive page are required')
    client = client or NyaaClient()
    html = client.fetch_listing(query, '1_0', '0', page, timeout, sort='id', order='desc')
    rows = []
    for entry in parse_listing(html):
        row = asdict(entry)
        # Link delivery remains a separate, reviewed action.
        row.pop('magnet', None)
        rows.append(row)
    pager = Pagination()
    pager.feed(html)
    return {'schema_version': 1, 'kind': 'nyaa_listing', 'checked_at': now(),
            'query': query, 'page': page, 'sort': 'id', 'order': 'desc',
            'source_url': build_listing_url('1_0', '0', page, query=query, sort='id', order='desc'),
            'scope': 'this_query_and_page_only', 'row_count': len(rows),
            'later_pages': sorted(p for p in pager.pages if p > page),
            'rows': rows}


def detail_payload(detail):
    release = asdict(detail.release)
    release.pop('magnet', None)
    return {'release': release, 'description': detail.description,
            'files': [asdict(f) for f in detail.files]}


def stable_detail(payload):
    release = payload['release']
    return {'release': {k: release.get(k) for k in
                        ('nyaa_id', 'title', 'size_bytes', 'info_hash', 'url')},
            'description': payload['description'], 'files': payload['files']}


def details(candidate_id, *, client=None, timeout=20):
    candidate_id = nyaa_id_from_url(str(candidate_id))
    if not candidate_id:
        raise ValueError('Expected a Nyaa ID or view URL')
    parsed = (client or NyaaClient()).get(candidate_id, timeout=timeout)
    payload = detail_payload(parsed)
    return {'schema_version': 1, 'kind': 'nyaa_detail', 'checked_at': now(),
            **payload, 'content_sha256': digest(stable_detail(payload))}


def read(path, kind=None):
    from evidence_artifacts import input_path
    value = json.loads(input_path(path).read_text(encoding='utf-8-sig'))
    if value.get('schema_version') != 1 or kind and value.get('kind') != kind:
        raise ValueError('Unsupported evidence report')
    return value


def save(path, value):
    from evidence_artifacts import output_path, register
    path = output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    register(path)
    return path


def draft(track, listings, detail_path, intent, episode):
    from evidence_artifacts import input_path
    listings = [input_path(p) for p in listings]
    detail_path = input_path(detail_path)
    reports = [read(p, 'nyaa_listing') for p in listings]
    selected = read(detail_path, 'nyaa_detail')
    if not any(r['nyaa_id'] == selected['release']['nyaa_id'] for report in reports for r in report['rows']):
        raise ValueError('Selected ID is not in the supplied listing evidence')
    return {'schema_version': 1, 'reviewed': False, 'track_id': track['track_id'],
            'identity_revision': track['identity_revision'], 'intent': intent,
            'target_episode': episode, 'candidate_id': selected['release']['nyaa_id'],
            'listing_reports': [str(Path(p).resolve()) for p in listings],
            'detail_report': str(Path(detail_path).resolve()),
            'coverage': {'complete_for_target': False, 'reason': ''},
            'key_decisions': [],
            'selection': {'kind': 'regular', 'work_reason': '', 'work_quotes': [],
                          'numbering': {'target_season': track.get('season'),
                                        'target_episode': episode, 'release_label': '',
                                        'reason': '', 'evidence_quotes': []},
                          'video_file': '', 'subtitle_quotes': []}}
