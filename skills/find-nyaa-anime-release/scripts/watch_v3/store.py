"""v3 domain commands. Every mutation shares one lock and revision transaction."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
from anime_release.storage import StateFileError, atomic_json, file_lock

SUCCESS_STATUSES = {'already_present', 'submitted', 'submitted_verified'}
PHASES = {'airing', 'finale_pending_evidence', 'completed', 'blocked'}
COMMANDS = {'create_track', 'record_delivery', 'record_pending_operation',
            'record_failed_operation', 'attach_completion_evidence', 'reconcile_completion',
            'record_waiting', 'repair_identity', 'append_outbox_action', 'ack_outbox_action'}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise StateFileError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def validate(data):
    require(isinstance(data, dict), 'invalid_state_object')
    require(data.get('version') == 3, 'v3_migration_required')
    require(isinstance(data.get('shows'), list), 'invalid_shows')
    ids = set()
    operations = set()
    for show in data['shows']:
        tid = show['track_id']
        require(isinstance(tid, str) and tid and tid not in ids, 'duplicate_or_invalid_track_id')
        ids.add(tid)
        require(show['lifecycle']['phase'] in PHASES, 'invalid_phase')
        require(isinstance(show['identity'].get('title'), str) and bool(show['identity']['title']), 'invalid_identity')
        require(isinstance(show['identity'].get('provider_bindings'), dict), 'invalid_provider_bindings')
        require(not (set(show['progress']) & {'watched_episode', 'next_episode', 'airing', 'status', 'tracking_status'}), 'legacy_progress_fields')
        require('airing' not in show['broadcast'], 'legacy_broadcast_fields')
        total = show['broadcast'].get('total_episodes')
        require(total is None or type(total) is int and total > 0, 'invalid_total_episodes')
        p = show['progress']
        require(type(p['handled_episode']) is int and p['handled_episode'] >= 0, 'invalid_progress')
        require(type(p['latest_release_episode']) is int and p['latest_release_episode'] >= 0, 'invalid_latest')
        require(p['target_episode'] is None or type(p['target_episode']) is int and p['target_episode'] > 0, 'invalid_target')
        if show['lifecycle']['phase'] == 'completed':
            require(p['target_episode'] is None, 'completed_has_target')
        for opid, op in show.get('operations', {}).items():
            require(opid not in operations, 'duplicate_operation_id')
            operations.add(opid)
            require(op.get('operation_id', opid) == opid, 'operation_id_conflict')
        for receipt in show.get('deliveries', []):
            op = show.get('operations', {}).get(receipt.get('operation_id'))
            require(op is not None and op.get('info_hash') == receipt.get('info_hash'), 'orphan_receipt')
        require(len({r['operation_id'] for r in show['deliveries']}) == len(show['deliveries']), 'duplicate_receipt')
    return data


def migrate_state(data):
    if data.get('version') == 3:
        return copy.deepcopy(validate(data))
    require(data.get('version', 1) in {1, 2}, 'unsupported_state_version')
    for raw in data.get('shows', []):
        if 'identity' in raw:
            require(not (raw.get('season') and raw['identity'].get('season') and raw['season'] != raw['identity']['season']), 'migration_season_conflict')
    from anime_release.schema import adapt, encode
    # Existing stable v1 IDs and unknown fields are preserved by the old decoder.
    normalized = encode(adapt(data))
    shows = []
    for old in normalized['shows']:
        p = old['progress']
        values = [p.get('watched_episode'), (p['next_episode'] - 1 if type(p.get('next_episode')) is int else None)]
        require(all(v is None or type(v) is int and v >= 0 for v in values), 'illegal_legacy_progress')
        handled = max([v for v in values if v is not None] or [0])
        latest = p.get('latest_known_episode') or 0
        require(type(latest) is int and latest >= 0, 'illegal_legacy_progress')
        show = copy.deepcopy(old)
        show['identity']['provider_bindings'] = show.pop('bindings')
        show['progress'] = {'handled_episode': handled, 'latest_release_episode': max(handled, latest), 'target_episode': handled + 1}
        show['lifecycle'] = {'phase': 'airing', 'updated_at': now_iso()}
        show['outbox'] = []
        show['automation_owners'] = []
        show['broadcast'].pop('airing', None)
        if p.get('status') == 'blocked':
            show['lifecycle']['phase'] = 'blocked'
        elif p.get('status') in {'completed', 'finished'}:
            # Only confirmed evidence may preserve a completed lifecycle.
            c = show['broadcast'].get('completion') or {}
            if c.get('confirmed') and type(c.get('final_episode')) is int and handled >= c['final_episode']:
                show['lifecycle']['phase'] = 'completed'
        for opid, op in show['operations'].items():
            op.setdefault('operation_id', opid)
            op.setdefault('track_id', show['track_id'])
            op.setdefault('identity_revision', show['identity_revision'])
            if op.get('info_hash') and not op.get('request'):
                from nyaa_client import magnet_from_hash
                op['request'] = {'track_id': show['track_id'], 'operation_id': opid,
                    'info_hash': op['info_hash'], 'magnet': magnet_from_hash(op['info_hash'], show['identity']['title']),
                    'source_url': 'https://nyaa.si/view/' + str(op['candidate_id']) if op.get('candidate_id') else None}
            op.setdefault('committed', False)
        # Orphans require human review: never invent an episode for a receipt.
        for receipt in show['deliveries']:
            opid = receipt.get('operation_id')
            require(opid in show['operations'] and receipt.get('info_hash'), 'orphan_receipt')
            op = show['operations'][opid]
            require(op.get('info_hash') == receipt['info_hash'], 'receipt_hash_conflict')
            # The delivery history is proof this operation was already committed.
            op['committed'] = True
            op.setdefault('receipt', copy.deepcopy(receipt))
        _reconcile(show)
        shows.append(show)
    converted = {k: copy.deepcopy(v) for k, v in data.items() if k not in {'shows', 'version'}}
    converted.update(version=3, schema='watch-v3', revision=0, shows=shows, updated_at=now_iso())
    return validate(converted)


def _append(show, action):
    require(action.get('outbox_id') and action.get('kind') in {'reconcile_completion', 'delete_owning_automation'}, 'invalid_outbox_action')
    found = next((a for a in show['outbox'] if a['outbox_id'] == action['outbox_id']), None)
    if found:
        require(found['kind'] == action['kind'] and found.get('payload', {}) == action.get('payload', {}), 'outbox_id_conflict')
        return
    show['outbox'].append({**copy.deepcopy(action), 'status': 'pending', 'attempts': 0, 'created_at': now_iso()})


def _reconcile(show):
    p, b, life = show['progress'], show['broadcast'], show['lifecycle']
    if life['phase'] == 'blocked':
        p['target_episode'] = None
        return
    completion = b.get('completion') or {}
    final = completion.get('final_episode')
    if life['phase'] == 'completed' or completion.get('confirmed') is True and type(final) is int and p['handled_episode'] >= final:
        life['phase'] = 'completed'
        p['target_episode'] = None
        return
    total = b.get('total_episodes')
    if type(total) is int and p['handled_episode'] >= total:
        life['phase'] = 'finale_pending_evidence'
        p['target_episode'] = None
    else:
        # A due date requests evidence but the still-undelivered finale stays targetable.
        due = completion.get('end_date')
        life['phase'] = 'finale_pending_evidence' if isinstance(due, str) and len(due) == 10 and due <= date.today().isoformat() else 'airing'
        p['target_episode'] = p['handled_episode'] + 1


def _cleanup_actions(data):
    owners = {}
    for show in data['shows']:
        for owner in show.get('automation_owners', []):
            owners[(owner['automation_id'], owner['scope_hash'])] = owner
    by_id = {s['track_id']: s for s in data['shows']}
    for owner in owners.values():
        targets = owner.get('target_track_ids', [])
        if not targets or owner.get('pending_retry_children') or owner.get('cleanup_policy') != 'delete_when_all_targets_completed':
            continue
        records = [by_id.get(t) for t in targets]
        if any(s is None or s['lifecycle']['phase'] != 'completed' for s in records):
            continue
        if any(any(not op.get('committed') and op.get('status') in {'prepared','recovering','accepted'} for op in s['operations'].values()) for s in records):
            continue
        def final_receipt(s):
            final = (s['broadcast'].get('completion') or {}).get('final_episode')
            return any(r.get('accepted') is True and r.get('status') in SUCCESS_STATUSES
                and s['operations'].get(r.get('operation_id'), {}).get('episode') == final for r in s['deliveries'])
        if not all(final_receipt(s) for s in records):
            continue
        # Every target must explicitly carry the exact same owner binding.
        if not all(owner in s.get('automation_owners', []) for s in records):
            continue
        _append(records[0], {'outbox_id': 'cleanup:' + digest(owner), 'kind': 'delete_owning_automation', 'payload': owner})


class StateRepository:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return {'version': 3, 'schema': 'watch-v3', 'revision': 0, 'shows': []}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8-sig'))
            return validate(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise StateFileError(f'invalid_watch_state: {exc}') from exc

    read_v3 = read

    def find(self, track_id=None, title=None):
        matches = []
        for show in self.read()['shows']:
            names = [show['identity']['title'], *show['identity'].get('aliases', [])]
            if (track_id and show['track_id'] == track_id) or (title and title.strip().casefold() in {n.strip().casefold() for n in names}):
                matches.append(show)
        require(len(matches) <= 1, 'ambiguous_track')
        return matches[0] if matches else None

    def work_lock(self, track_id):
        return file_lock(self.path.parent / '.watch-locks' / (hashlib.sha256(track_id.encode()).hexdigest() + '.lock'))

    def migrate(self, *, backup=True, expected_sha256=None):
        with file_lock(self.path.with_suffix(self.path.suffix + '.lock')):
            raw = self.path.read_bytes() if self.path.exists() else b'{}'
            sha = hashlib.sha256(raw).hexdigest()
            require(expected_sha256 is None or sha == expected_sha256, 'migration_source_changed')
            old = json.loads(raw.decode('utf-8-sig'))
            if old.get('version') == 3:
                return validate(old)
            converted = migrate_state(old)
            if backup:
                backup_path = self.path.with_name(self.path.name + '.' + sha[:16] + '.v2.bak')
                if not backup_path.exists():
                    with backup_path.open('xb') as f:
                        f.write(raw); f.flush()
                        import os
                        os.fsync(f.fileno())
            atomic_json(self.path, converted)
            return converted

    def command(self, track_id, kind, *, expected_revision=None, **fields):
        require(kind in COMMANDS, 'unknown_domain_command')
        with self.work_lock(track_id), file_lock(self.path.with_suffix(self.path.suffix + '.lock')):
            data = self.read()
            show = next((s for s in data['shows'] if s['track_id'] == track_id), None)
            if kind == 'create_track':
                require(show is None, 'track_exists')
                identity = copy.deepcopy(fields['identity'])
                require(bool(identity.get('title')), 'title_required')
                identity.setdefault('provider_bindings', {})
                show = {'track_id': track_id, 'revision': 0, 'identity_revision': 0, 'identity': identity,
                    'broadcast': copy.deepcopy(fields.get('broadcast', {})),
                    'progress': {'handled_episode': 0, 'latest_release_episode': 0, 'target_episode': 1},
                    'lifecycle': {'phase': 'airing'}, 'retrieval': copy.deepcopy(fields.get('retrieval', {})),
                    'deliveries': [], 'operations': {}, 'outbox': [], 'automation_owners': [], 'extra': {}}
                data['shows'].append(show)
            require(show is not None, 'track_not_found')
            require(expected_revision is None or show['revision'] == expected_revision, 'revision_conflict')
            before_all = {s['track_id']: copy.deepcopy(s) for s in data['shows']}
            self._apply(show, kind, fields)
            _reconcile(show)
            _cleanup_actions(data)
            for changed in data['shows']:
                if changed != before_all[changed['track_id']] or kind == 'create_track' and changed['track_id'] == track_id:
                    changed['revision'] += 1
                    changed['lifecycle']['updated_at'] = now_iso()
            data['revision'] = data.get('revision', 0) + 1
            data['updated_at'] = now_iso()
            validate(data)
            atomic_json(self.path, data)
            return data

    def _apply(self, s, kind, f):
        if kind == 'create_track':
            return
        if kind == 'record_pending_operation':
            require(s['lifecycle']['phase'] not in {'blocked', 'completed'}, 'track_not_deliverable')
            op = copy.deepcopy(f['operation'])
            require(op.get('track_id') == s['track_id'] and op.get('identity_revision') == s['identity_revision'], 'operation_identity_conflict')
            require(re.fullmatch('[0-9a-f]{40}', op.get('info_hash', '')) is not None, 'invalid_info_hash')
            require(type(op.get('episode')) is int and op['episode'] > 0, 'invalid_episode')
            require(op.get('kind') == 'regular', 'regular_delivery_required')
            from .clients import DeliveryRequest
            request = DeliveryRequest(**op['request'])
            request.validate()
            require((request.track_id, request.operation_id, request.info_hash) == (s['track_id'], op['operation_id'], op['info_hash']), 'operation_request_conflict')
            existing = s['operations'].get(op['operation_id'])
            if existing:
                require(all(existing.get(k) == op.get(k) for k in ('track_id', 'info_hash', 'episode', 'identity_revision', 'request')), 'operation_identity_conflict')
                return
            require(not any(o.get('status') in {'prepared','recovering','accepted'} and not o.get('committed') for o in s['operations'].values()), 'operation_recovery_required')
            op.update(status='prepared', prepared_at=now_iso(), committed=False)
            s['operations'][op['operation_id']] = op
        elif kind == 'record_failed_operation':
            op = s['operations'][f['operation_id']]
            if op.get('status') != 'accepted':
                op.update(status='recovering' if f.get('ambiguous', True) else 'failed', recovery=copy.deepcopy(f['recovery']))
        elif kind == 'record_delivery':
            r = copy.deepcopy(f['receipt'])
            require(r.get('accepted') is True and r.get('status') in SUCCESS_STATUSES, 'delivery_status_not_accepted')
            op = s['operations'].get(r['operation_id'])
            require(op is not None and op['info_hash'] == r['info_hash'] and op['track_id'] == r['track_id'] == s['track_id'], 'delivery_operation_mismatch')
            require(op['identity_revision'] == s['identity_revision'], 'identity_revision_conflict')
            require(op.get('kind') == 'regular' and type(op.get('episode')) is int, 'regular_delivery_required')
            if op.get('committed'):
                return
            op.update(status='accepted', receipt=r)
            if f.get('acceptance_only'):
                return
            if not any(x['operation_id'] == r['operation_id'] for x in s['deliveries']):
                s['deliveries'].append(r)
            op['committed'] = True
            s['progress']['handled_episode'] = max(s['progress']['handled_episode'], op['episode'])
            s['progress']['latest_release_episode'] = max(s['progress']['latest_release_episode'], op['episode'])
            s['extra'].pop('pending_download', None)
            _append(s, {'outbox_id': 'reconcile:' + op['operation_id'], 'kind': 'reconcile_completion', 'payload': {'track_id': s['track_id']}})
        elif kind == 'attach_completion_evidence':
            evidence = copy.deepcopy(f['evidence'])
            _validate_completion(s, evidence)
            old = s['broadcast'].get('completion') or {}
            total = s['broadcast'].get('total_episodes')
            if (old.get('confirmed') and old.get('final_episode') != evidence['final_episode']) or (type(total) is int and total != evidence['final_episode']):
                s['lifecycle'].update(phase='blocked', blocked_reason='completion_evidence_conflict')
                s['broadcast'].setdefault('completion_conflicts', []).append(evidence)
            else:
                s['broadcast'].update(completion=evidence, total_episodes=evidence['final_episode'])
        elif kind == 'reconcile_completion':
            pass
        elif kind == 'record_waiting':
            s['lifecycle']['waiting_reason'] = f.get('reason')
            if type(f.get('latest_release_episode')) is int:
                s['progress']['latest_release_episode'] = max(s['progress']['latest_release_episode'], f['latest_release_episode'])
        elif kind == 'repair_identity':
            require(f.get('evidence', {}).get('reviewed') is True, 'identity_repair_evidence_required')
            require(not any(not o.get('committed') and o['status'] in {'prepared','recovering','accepted'} for o in s['operations'].values()), 'pending_operation_identity_locked')
            s['identity'] = copy.deepcopy(f['identity'])
            s['identity_revision'] += 1
            s['extra'].setdefault('identity_repairs', []).append(copy.deepcopy(f['evidence']))
        elif kind == 'append_outbox_action':
            if 'owner' in f:
                owner = copy.deepcopy(f['owner'])
                require(owner.get('automation_id') and owner.get('scope_hash') and s['track_id'] in owner.get('target_track_ids', []), 'invalid_automation_owner')
                require(owner.get('cleanup_policy') == 'delete_when_all_targets_completed', 'invalid_cleanup_policy')
                require(re.fullmatch('[0-9a-f]{64}', owner['scope_hash']) is not None, 'invalid_scope_hash')
                require(len(set(owner['target_track_ids'])) == len(owner['target_track_ids']), 'duplicate_automation_target')
                s['automation_owners'] = [o for o in s.get('automation_owners', []) if o['automation_id'] != owner['automation_id']] + [owner]
            else:
                require(f['action'].get('kind') != 'delete_owning_automation', 'cleanup_requires_eligibility')
                _append(s, f['action'])
        elif kind == 'ack_outbox_action':
            action = next((x for x in s['outbox'] if x['outbox_id'] == f['outbox_id']), None)
            require(action is not None, 'outbox_not_found')
            if action['status'] == 'done':
                return
            if f.get('success') and action['kind'] == 'delete_owning_automation':
                receipt = f.get('receipt') or {}
                owner = action['payload']
                require(receipt.get('automation_id') == owner['automation_id'] and receipt.get('scope_hash') == owner['scope_hash'] and receipt.get('status') in {'deleted','already_absent'}, 'cleanup_receipt_required')
            action.update(status='done' if f.get('success') else 'pending', last_error=f.get('error'), checked_at=now_iso(), attempts=action.get('attempts', 0)+1)
            if f.get('receipt'):
                action['receipt'] = copy.deepcopy(f['receipt'])

    def attach_completion(self, track_id, evidence, **kw):
        return self.command(track_id, 'attach_completion_evidence', evidence=evidence, **kw)

    def ack_outbox(self, track_id, outbox_id, *, success, error=None, receipt=None):
        return self.command(track_id, 'ack_outbox_action', outbox_id=outbox_id, success=success, error=error, receipt=receipt)


def _validate_completion(show, evidence):
    from urllib.parse import urlsplit
    require(evidence.get('reviewed') is True and evidence.get('confirmed') is True, 'completion_review_required')
    require(evidence.get('source_kind') in {'official','broadcaster'}, 'completion_source_required')
    require(type(evidence.get('final_episode')) is int and evidence['final_episode'] > 0, 'invalid_final_episode')
    require(urlsplit(evidence.get('source_url', '')).scheme == 'https' and urlsplit(evidence['source_url']).hostname and evidence.get('evidence_text'), 'completion_source_required')
    identity = show['identity']
    matched = evidence.get('track_id') == show['track_id'] and evidence.get('identity_revision') == show['identity_revision']
    for provider, binding in identity.get('provider_bindings', {}).items():
        supplied = evidence.get(provider + '_id')
        if supplied is not None:
            require(str(supplied) == str(binding['entry_id']), 'completion_identity_conflict')
            matched = True
    require(matched and evidence.get('season') == identity.get('season') and evidence.get('part') == identity.get('part'), 'completion_identity_conflict')
    checked = datetime.fromisoformat(evidence.get('checked_at', ''))
    require(checked.tzinfo is not None and checked <= datetime.now(timezone.utc), 'invalid_completion_timestamp')
    if evidence.get('end_date'):
        require(evidence['end_date'] <= date.today().isoformat()[:len(evidence['end_date'])], 'future_completion')


V3Repository = StateRepository

def migrate_file(path, *, backup=True, expected_sha256=None):
    return StateRepository(path).migrate(backup=backup, expected_sha256=expected_sha256)
