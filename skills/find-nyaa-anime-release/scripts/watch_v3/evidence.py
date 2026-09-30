"""Evidence discovery, Agent manifest, validation and unique selection boundary."""
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import copy
import json
from anime_release import raw_evidence
from anime_release.reviewed import audit

@dataclass(frozen=True)
class QualityPolicy:
    tier: str = 'browse'
    require_zh: bool = False
    want_zh: bool = False
    min_gib: float | None = None
    max_gib: float | None = None
    allow_upward: bool = False

@dataclass(frozen=True)
class ReviewManifest:
    path: Path
    content: dict

    @classmethod
    def load(cls, path):
        from evidence_artifacts import input_path
        path = input_path(path)
        content = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(content, dict) or content.get('reviewed') is not True:
            raise ValueError('agent_review_required')
        return cls(path, content)

@dataclass(frozen=True)
class SelectionResult:
    release: object | None
    report: dict


def validation_snapshot(show):
    """Disposable evidence-validator input, never saved or merged into state."""
    identity = copy.deepcopy(show['identity'])
    for provider, binding in identity.pop('provider_bindings', {}).items():
        identity[provider + '_id'] = binding['entry_id']
    return {**identity, 'track_id':show['track_id'], 'identity_revision':show['identity_revision'],
            'watched_episode':show['progress']['handled_episode'],
            'next_episode':show['progress']['target_episode'],
            'status':show['lifecycle']['phase'], 'completion':show['broadcast'].get('completion', {})}

class DiscoveryService:
    def __init__(self, client=None):
        self.client = client

    def discover(self, query, page=1):
        return raw_evidence.listing(query, page, client=self.client)

    def detail(self, candidate_id):
        return raw_evidence.details(candidate_id, client=self.client)

    def draft(self, show, listings, detail, intent, episode):
        return raw_evidence.draft(validation_snapshot(show), listings, detail, intent, episode)

class ReviewValidator:
    def __init__(self, client=None):
        self.client = client

    def validate(self, manifest, show, policy):
        intent = manifest.content['intent']
        args = SimpleNamespace(review=manifest.path, title=show['identity']['title'], season=None,
            whole_season=False, include_specials=False, mark_finished=False, official_air_date=None,
            source_numbering=None, target_numbering=None, identity_evidence=None, completion_evidence=None,
            no_state_update=True, include_magnet=True, legal_ok=True, enqueue_qbittorrent=False,
            latest=intent == 'latest_regular', episode=manifest.content['target_episode'] if intent == 'specific_episode' else None,
            candidate_id=None, tier=policy.tier, min_gib_per_episode=policy.min_gib,
            max_gib_per_episode=policy.max_gib, allow_upward_compatibility=policy.allow_upward,
            require_zh=policy.require_zh, want_zh=policy.want_zh, timeout=20)
        validated, report = audit(args, client=self.client, track=validation_snapshot(show))
        release = validated[0] if validated and validated[0] != 'reconcile_completion' else None
        return SelectionResult(release, report)
