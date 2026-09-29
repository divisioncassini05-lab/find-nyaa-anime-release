"""Immutable cross-stage contracts; no provider or filesystem dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class ReleaseRequest:
    title: str
    season: str | None = None
    episode: int | None = None
    intent: str = 'browse'
    read_only: bool = True
    enqueue: bool = False
    require_zh: bool = False
    want_zh: bool = True
    min_gib: float | None = None
    max_gib: float | None = None
    candidate_id: str | None = None


@dataclass(frozen=True)
class WorkIdentity:
    track_id: str
    title: str
    season: str | None
    part: str | None = None
    revision: int = 0
    aliases: tuple[str, ...] = ()
    format: str | None = None


@dataclass(frozen=True)
class MetadataEvidence:
    provider: str
    entry_id: str
    source_url: str
    checked_at: str
    titles: tuple[str, ...]
    season: str | None
    part: str | None
    format: str | None
    # JSON payloads prevent mutable dictionaries leaking across stage boundaries.
    payload_json: str
    identity_revision: int = 0


@dataclass(frozen=True)
class TargetDecision:
    identity: WorkIdentity
    intent: str
    episode: int | None
    source: str
    latest_confirmed: bool = False


@dataclass(frozen=True)
class VerifiedRelease:
    identity: WorkIdentity
    target: TargetDecision
    candidate_id: str
    title: str
    magnet: str
    info_hash: str
    source_url: str
    kind: str
    evidence_json: str


@dataclass(frozen=True)
class DeliveryReceipt:
    operation_id: str
    track_id: str
    info_hash: str
    status: str
    accepted: bool
    checked_at: str
    evidence_json: str


@dataclass(frozen=True)
class StateCommand:
    track_id: str
    kind: str
    expected_revision: int | None = None
    expected_identity_revision: int | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    receipt: DeliveryReceipt | None = None


@dataclass
class WorkflowError(Exception):
    stage: str
    code: str
    retryable: bool = False
    evidence: tuple[Any, ...] = ()
    next_action: str = 'inspect_evidence'

    def as_dict(self):
        return asdict(self)

    def __str__(self):
        return f'{self.stage}: {self.code}'
