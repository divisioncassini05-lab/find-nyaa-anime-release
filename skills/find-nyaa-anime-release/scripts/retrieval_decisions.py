"""Versioned evidence contracts shared by discovery and final verification."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import re

REPORT_VERSION = 2
ACTIVE_RUN: ContextVar[SearchRun | None] = ContextVar('retrieval_run', default=None)
TITLE_CONTEXT: ContextVar[tuple[str, ...]] = ContextVar('title_context', default=())


@dataclass
class IdentityDecision:
    status: str
    episode: str | None
    season: int | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    parser: str = 'aniparse-2.0.0'
    work: str = 'unresolved'
    kind: str = 'unknown'

    def as_dict(self):
        return asdict(self)


@dataclass
class TargetDecision:
    observed_episode: int | None
    confirmed_episode: int | None
    status: str
    basis: str
    ambiguous_ids: list[str] = field(default_factory=list)


@dataclass
class EligibilityDecision:
    release_id: str
    status: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class SearchRun:
    intent: str
    query_plan: list[dict[str, Any]]
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requests: list[dict[str, Any]] = field(default_factory=list)
    raw_candidates: list[dict[str, Any]] = field(default_factory=list)
    identities: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    completeness: str = 'complete'
    scope: str = 'queried_names_and_pages_only'
    target: TargetDecision | None = None
    eligibility: list[EligibilityDecision] = field(default_factory=list)
    coverage_notes: list[str] = field(default_factory=list)

    def add_raw(self, candidates):
        for candidate in candidates:
            payload = {
                'release_id': candidate.url,
                'title': candidate.title,
                'size': candidate.size,
                'size_bytes': candidate.size_bytes,
                'published': candidate.published,
                'seeders': candidate.seeders,
                'info_hash': getattr(candidate, 'info_hash', None),
                'matched_queries': list(candidate.matched_queries),
            }
            old = next((r for r in self.raw_candidates if r['release_id'] == candidate.url), None)
            if old:
                old['matched_queries'] = list(dict.fromkeys(old['matched_queries'] + payload['matched_queries']))
            else:
                self.raw_candidates.append(payload)

    def ingest_requests(self):
        """Keep rows from successful pages even when a later page failed."""
        from types import SimpleNamespace
        for request in self.requests:
            items = request.get('items', []) if request.get('source') == 'cache' else [
                {'query':request.get('query',''), 'release':r} for r in request.get('releases',[])]
            for item in items:
                row = dict(item['release'])
                if row.get('url'):
                    row['matched_queries'] = [item['query']] if item.get('query') else []
                    self.add_raw([SimpleNamespace(**row)])

    def record_eligibility(self, release_id, status, reasons=()):
        self.eligibility[:] = [d for d in self.eligibility if d.release_id != release_id]
        self.eligibility.append(EligibilityDecision(release_id, status, list(reasons)))

    def as_dict(self):
        payload=asdict(self)
        seen={}
        for raw in payload['raw_candidates']:
            key=(raw.get('info_hash') or raw['release_id']).lower()
            raw['dedup_key']=key
            raw['duplicate_of']=seen.get(key)
            seen.setdefault(key,raw['release_id'])
        payload.update(raw_candidate_count=len(self.raw_candidates),deduplicated_candidate_count=len(seen),
                       raw_candidates_truncated=False)
        return payload


class RecordingClient:
    """Record actual requests; never converts an exception into an empty page."""
    def __init__(self, client, run):
        self.client, self.run = client, run

    def search(self, request):
        record = {**asdict(request), 'at': datetime.now(timezone.utc).isoformat()}
        self.run.requests.append(record)
        try:
            result = self.client.search(request)
            record.update(status='ok', count=len(result))
            if request.source == 'rss' and len(result) >= 75:
                self.run.coverage_notes.append(f'rss_recent_window_only:{request.query}')
            if request.source == 'listing' and request.page >= 3 and len(result) >= 75:
                self.run.coverage_notes.append(f'listing_page_cap_reached:{request.query}')
            # Persist raw records before any size or identity processing.
            record['releases'] = [
                {k: v for k, v in asdict(r).items() if k != 'magnet'} for r in result
            ]
            return result
        except Exception as exc:
            record.update(status='failed', error=str(exc), error_type=type(exc).__name__)
            self.run.completeness = 'partial'
            raise

    def get(self, *args, **kwargs):
        record = {'source':'detail','candidate':str(args[0]) if args else '',
                  'at':datetime.now(timezone.utc).isoformat()}
        self.run.requests.append(record)
        try:
            result = self.client.get(*args, **kwargs)
            record.update(status='ok', releases=[{k:v for k,v in asdict(result.release).items() if k!='magnet'}])
            record['description'] = result.description
            record['files'] = [asdict(f) for f in result.files]
            return result
        except Exception as exc:
            record.update(status='failed', error=str(exc), error_type=type(exc).__name__)
            raise

    def get_description(self, *args, **kwargs):
        record={'source':'subtitle_detail','candidate':str(args[0]) if args else '',
                'at':datetime.now(timezone.utc).isoformat()}
        self.run.requests.append(record)
        try:
            result=self.client.get_description(*args, **kwargs)
            record.update(status='ok',description=result)
            return result
        except Exception as exc:
            record.update(status='failed',error=str(exc),error_type=type(exc).__name__)
            raise


def plan_queries(titles, intent, episode=None, season=None):
    """Verified names first; known numbering formats are explicit plan entries."""
    unique = list(dict.fromkeys(t for t in titles if t))
    plan = [{'query': t, 'lane': 'broad', 'basis': 'caller_verified_title'} for t in unique]
    if episode is not None and intent != 'latest_regular':
        for title in unique:
            if re.search(r'[a-zA-Z]', title):
                token = f'S{season:02d}E{episode:02d}' if season else f'{episode:02d}'
                plan.append({'query': f'{title} {token}', 'lane': 'exact_fallback', 'basis': 'requested_numbering'})
                plan.append({'query': f'{title} {episode:02d}', 'lane': 'exact_fallback', 'basis': 'regular_episode'})
                break
    return plan
