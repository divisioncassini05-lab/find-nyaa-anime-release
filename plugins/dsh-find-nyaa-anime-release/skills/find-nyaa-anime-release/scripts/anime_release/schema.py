"""Lossless v1 read adapter and v2 serialization. Never deduplicate records."""
from __future__ import annotations

import copy
import uuid

IDENTITY = {'title', 'aliases', 'season', 'part', 'format'}
BROADCAST = {'airing', 'total_episodes', 'duration_min', 'completion', 'metadata_titles',
             'mainline_scope', 'related_titles', 'continuation_parts', 'next_airing_episode', 'next_airing_at'}
PROGRESS = {'watched_episode', 'latest_known_episode', 'next_episode', 'status', 'tracking_status'}
RETRIEVAL = {'search_titles', 'verified_search_titles'}
META = {'track_id', 'revision', 'identity_revision', 'binding_evidence', 'deliveries', 'operations'}
PROVIDERS = {'anilist_id': 'anilist', 'bangumi_id': 'bangumi'}


def adapt(data):
    """Only memory changes. An ordinal distinguishes even byte-identical v1 rows."""
    result = copy.deepcopy(data)
    seen = set()
    for index, show in enumerate(result.setdefault('shows', [])):
        if 'identity' in show:
            flat = {**show.get('extra', {}), **show['identity'], **show.get('broadcast', {}),
                    **show.get('progress', {}), **show.get('retrieval', {})}
            flat.update({key: copy.deepcopy(show[key]) for key in META if key in show})
            for key, provider in PROVIDERS.items():
                if provider in show.get('bindings', {}):
                    flat[key] = show['bindings'][provider]['entry_id']
            flat['binding_evidence'] = copy.deepcopy(show.get('bindings', {}))
            result['shows'][index] = show = flat
        if not show.get('track_id'):
            # No alias, provider ID, progress or mutable metadata participates.
            seed = f"legacy-row:{index}:{show.get('created_at', '')}:{show.get('title', '')}:{show.get('season', '')}"
            show['track_id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
        if show['track_id'] in seen:
            raise ValueError('duplicate_track_id')
        seen.add(show['track_id'])
        show.setdefault('revision', 0)
        show.setdefault('identity_revision', 0)
        show.setdefault('binding_evidence', {provider: {'entry_id': show[key], 'status': 'pending_verification'}
                                           for key, provider in PROVIDERS.items() if show.get(key)})
    result['version'] = 2
    return result


def encode(data):
    result = adapt(data)
    for index, show in enumerate(result['shows']):
        bindings = copy.deepcopy(show.get('binding_evidence', {}))
        for key, provider in PROVIDERS.items():
            if key in show:
                previous = bindings.get(provider, {})
                bindings[provider] = previous if 'entry_id' in previous and previous.get('entry_id') == show[key] else {
                    'entry_id': show[key], 'status': 'pending_verification'}
        reserved = IDENTITY | BROADCAST | PROGRESS | RETRIEVAL | META | PROVIDERS.keys()
        result['shows'][index] = {
            'track_id': show['track_id'], 'revision': show['revision'],
            'identity_revision': show['identity_revision'],
            'identity': {key: show[key] for key in IDENTITY if key in show},
            'bindings': bindings,
            'broadcast': {key: show[key] for key in BROADCAST if key in show},
            'progress': {key: show[key] for key in PROGRESS if key in show},
            'retrieval': {key: show[key] for key in RETRIEVAL if key in show},
            'deliveries': show.get('deliveries', []), 'operations': show.get('operations', {}),
            'extra': {key: value for key, value in show.items() if key not in reserved},
        }
    return result


def new_track_id():
    return str(uuid.uuid4())
