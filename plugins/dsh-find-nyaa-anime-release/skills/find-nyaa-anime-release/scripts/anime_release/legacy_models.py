"""Extracted policy module: legacy_models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResolvedAnime:
    title: str
    aliases: list[str] = field(default_factory=list)
    search_titles: list[str] = field(default_factory=list)
    verified_search_titles: list[str] = field(default_factory=list)
    season: str | None = None
    current: bool = False
    trackable: bool = False
    source: str = "none"
    format: str | None = None
    status: str | None = None
    episodes: int | None = None
    duration_min: int | None = None
    bangumi_id: int | None = None
    anilist_id: int | None = None
    next_airing_episode: int | None = None
    next_airing_at: int | None = None
    mainline_scope: str = "unknown"
    related_titles: list[str] = field(default_factory=list)
    continuation_parts: list[dict[str, Any]] = field(default_factory=list)
    choices: list[dict[str, Any]] = field(default_factory=list)
    completion: dict[str, Any] = field(default_factory=dict)
    metadata_titles: list[str] = field(default_factory=list)
    identity_conflicts: list[dict[str, Any]] = field(default_factory=list)
    work_identity: Any = None
    evidence: tuple = ()
    repair_proposal: dict[str, Any] = field(default_factory=dict)
    stage_errors: list[dict[str, Any]] = field(default_factory=list)
    official_identity_evidence: Any = None


@dataclass
class IdentityResolution:
    status: str
    resolved: ResolvedAnime
    state_show: dict[str, Any] | None
    tracked: bool
    input_kind: str
    sources: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    resolver: str = "not_used"

