"""Only tracking writer. Commands address track_id, never aliases/provider IDs."""
import copy
from pathlib import Path
from .models import StateCommand, WorkflowError
from .schema import adapt, encode, IDENTITY, BROADCAST, RETRIEVAL
from .storage import StateFileError, read_json, atomic_json, file_lock

class StateView(dict):
    def __init__(self, data):
        super().__init__(data)
        self.baseline = copy.deepcopy(data)

def load(path):
    try:
        return StateView(adapt(read_json(path)))
    except (ValueError, TypeError, KeyError) as exc:
        raise StateFileError(f'Invalid tracking schema: {path}: {exc}') from exc

def require_record(state, track_id):
    matches = [s for s in state['shows'] if s['track_id'] == track_id]
    if len(matches) != 1:
        raise WorkflowError('state_commit', 'track_not_found', False, (track_id,), 'resolve_local_identity')
    return matches[0]

def handled(show):
    values = [show.get('watched_episode')]
    if isinstance(show.get('next_episode'), int) and show['next_episode'] > 1:
        values.append(show['next_episode'] - 1)
    return max((v for v in values if isinstance(v, int)), default=0)

def apply_command(state, command):
    if command.kind == 'create':
        if any(s['track_id'] == command.track_id for s in state['shows']):
            raise WorkflowError('state_commit', 'track_exists')
        record = copy.deepcopy(command.fields)
        record.update(track_id=command.track_id, revision=0, identity_revision=0)
        state['shows'].append(adapt({'shows': [record]})['shows'][0])
        return
    show = require_record(state, command.track_id)
    if command.expected_identity_revision is not None and show['identity_revision'] != command.expected_identity_revision:
        raise WorkflowError('state_commit', 'identity_revision_conflict', False,
                            (command.track_id,), 'repeat_identity_verification')
    if command.kind in {'manual', 'delete', 'metadata_repair'} and command.expected_revision != show['revision']:
        raise WorkflowError('state_commit', 'revision_conflict', True, (), 'reload_and_review')
    before = copy.deepcopy(show)
    fields = copy.deepcopy(command.fields)
    if command.kind == 'delete':
        state['shows'].remove(show)
        return
    if command.kind == 'manual':
        if set(fields) & {'track_id', 'revision', 'identity_revision'}:
            raise WorkflowError('state_commit', 'protected_field')
        show.update(fields)
        if any(show.get(k) != before.get(k) for k in IDENTITY | {'anilist_id', 'bangumi_id'}):
            show['identity_revision'] += 1
    elif command.kind == 'metadata_repair':
        from .models import MetadataEvidence, WorkIdentity
        from .evidence import unique_repair
        bindings = fields.get('binding_evidence', {})
        if not bindings or any(b.get('status') != 'verified' or len(b.get('evidence', [])) < 2 for b in bindings.values()):
            raise WorkflowError('state_commit', 'repair_evidence_incomplete')
        identity = WorkIdentity(show['track_id'], show['title'], show.get('season'), show.get('part'),
                                show['identity_revision'], tuple(show.get('aliases', [])), show.get('format'))
        raw_evidence = next(iter(bindings.values()))['evidence']
        verified = unique_repair(identity, [MetadataEvidence(**{**e, 'titles':tuple(e['titles'])}) for e in raw_evidence])
        if any(provider not in verified or binding['entry_id'] != verified[provider]['entry_id']
               for provider, binding in bindings.items()):
            raise WorkflowError('state_commit', 'repair_evidence_conflict')
        show.setdefault('binding_evidence', {}).update(bindings)
        for provider, binding in bindings.items():
            show[provider + '_id'] = binding['entry_id']
        show['identity_revision'] += 1
    elif command.kind == 'metadata_bind':
        from .models import MetadataEvidence, WorkIdentity
        from .evidence import validate
        identity = WorkIdentity(show['track_id'], show['title'], show.get('season'), show.get('part'),
                                show['identity_revision'], tuple(show.get('aliases', [])), show.get('format'))
        for raw in fields.get('evidence', []):
            raw['titles'] = tuple(raw['titles'])
            evidence = validate(identity, MetadataEvidence(**raw))
            key = evidence.provider + '_id'
            if show.get(key) not in (None, int(evidence.entry_id)):
                raise WorkflowError('state_commit', 'binding_repair_required')
            show[key] = int(evidence.entry_id)
            show.setdefault('binding_evidence', {})[evidence.provider] = {
                'entry_id': int(evidence.entry_id), 'status': 'verified', 'evidence': [raw],
                'checked_at': evidence.checked_at}
        if any(show.get(k) != before.get(k) for k in ('anilist_id', 'bangumi_id')):
            show['identity_revision'] += 1
    elif command.kind == 'broadcast':
        if set(fields) - (BROADCAST | RETRIEVAL):
            raise WorkflowError('state_commit', 'broadcast_field_not_allowed')
        show.update(fields)
    elif command.kind == 'waiting':
        if set(fields) - {'notes', 'updated_at'}:
            raise WorkflowError('state_commit', 'waiting_cannot_advance')
        if show.get('status') != 'completed':
            show.update(fields, status='waiting')
    elif command.kind == 'operation':
        operation = fields['operation']
        show.setdefault('operations', {})[operation['operation_id']] = operation
    elif command.kind == 'delivery_success':
        receipt = command.receipt
        if not receipt or not receipt.accepted or receipt.track_id != command.track_id:
            raise WorkflowError('state_commit', 'delivery_receipt_required')
        operation = show.get('operations', {}).get(receipt.operation_id)
        if not operation or operation.get('info_hash') != receipt.info_hash:
            raise WorkflowError('state_commit', 'delivery_operation_mismatch')
        from dataclasses import asdict
        deliveries = show.setdefault('deliveries', [])
        if not any(d['operation_id'] == receipt.operation_id for d in deliveries):
            deliveries.append(asdict(receipt))
        operation.update(status='accepted', receipt=asdict(receipt))
        episode = operation.get('episode')
        if operation.get('kind') == 'regular' and isinstance(episode, int) and show.get('status') != 'completed':
            if episode > handled(show):
                show.update(watched_episode=episode,
                    latest_known_episode=max(episode, show.get('latest_known_episode') or 0),
                    next_episode=episode + 1, status='airing', airing=True)
                show.pop('pending_download', None)
    elif command.kind == 'completed':
        evidence = fields.get('completion', show.get('completion', {}))
        finale = evidence.get('final_episode')
        if evidence.get('confirmed') is not True or not isinstance(finale, int) or handled(show) < finale:
            raise WorkflowError('state_commit', 'finale_not_delivered')
        show.update(completion=evidence, status='completed', tracking_status='completed', airing=False, next_episode=None)
    else:
        raise WorkflowError('state_commit', 'unknown_state_operation', False, (command.kind,))
    if before.get('status') == 'completed' and command.kind != 'manual':
        for key in ('status', 'tracking_status', 'airing', 'next_episode', 'watched_episode', 'latest_known_episode'):
            if key in before:
                show[key] = before[key]
    if show != before:
        show['revision'] += 1

class StateRepository:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        return load(self.path)

    def work_lock(self, track_id):
        import hashlib
        key = hashlib.sha256(track_id.encode()).hexdigest()
        return file_lock(self.path.parent / '.locks' / (key + '.lock'))

    def commit(self, *commands):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for track_id in sorted({c.track_id for c in commands}):
                stack.enter_context(self.work_lock(track_id))
            stack.enter_context(file_lock(self.path.with_suffix(self.path.suffix + '.lock')))
            state = self.read()
            for command in commands:
                apply_command(state, command)
            atomic_json(self.path, encode(state))
            return state

def merge_legacy(current, base, desired):
    """Compatibility for manual commands. No provider-ID or alias equality."""
    current, base, desired = adapt(current), adapt(base), adapt(desired)
    previous = {s['track_id']: s for s in base['shows']}
    wanted = {s['track_id']: s for s in desired['shows']}
    present = {s['track_id']: s for s in current['shows']}
    for key in previous.keys() - wanted.keys():
        if key in present:
            if present[key]['revision'] != previous[key]['revision']:
                raise WorkflowError('state_commit', 'revision_conflict')
            current['shows'].remove(present[key])
    for key, show in wanted.items():
        old = previous.get(key)
        if old == show:
            continue
        now = present.get(key)
        if old is not None and now is None:
            raise WorkflowError('state_commit', 'track_removed')
        if now is None:
            current['shows'].append(copy.deepcopy(show))
            continue
        before = copy.deepcopy(now)
        for field, value in show.items():
            if field in {'track_id', 'revision', 'identity_revision'} or (old and old.get(field) == value):
                continue
            if field in IDENTITY or field.endswith('_id') or field == 'binding_evidence':
                if old and now['revision'] != old['revision'] and now.get(field) != value:
                    raise WorkflowError('state_commit', 'revision_conflict')
            if field in {'watched_episode', 'latest_known_episode', 'next_episode'} and isinstance(value, int):
                value = max(value, now.get(field) or 0)
            now[field] = copy.deepcopy(value)
        for field in (old or {}).keys() - show.keys():
            if field not in {'track_id', 'revision', 'identity_revision'}:
                now.pop(field, None)
        if before.get('status') == 'completed':
            for field in ('status', 'tracking_status', 'airing', 'next_episode', 'watched_episode', 'latest_known_episode'):
                if field in before:
                    now[field] = before[field]
        if now != before:
            now['revision'] += 1
            if any(now.get(k) != before.get(k) for k in IDENTITY | {'anilist_id', 'bangumi_id'}):
                now['identity_revision'] += 1
    return current

def save_legacy(path, data, *, base=None):
    normalized = adapt(data)
    data.clear()
    data.update(normalized)
    baseline = base if base is not None else getattr(data, 'baseline', None)
    from contextlib import ExitStack
    repo = StateRepository(path)
    track_ids = {s['track_id'] for s in normalized['shows']}
    if baseline is not None:
        track_ids.update(s['track_id'] for s in adapt(baseline)['shows'])
    with ExitStack() as stack:
        for track_id in sorted(track_ids):
            stack.enter_context(repo.work_lock(track_id))
        stack.enter_context(file_lock(Path(path).with_suffix(Path(path).suffix + '.lock')))
        current = load(path)
        if baseline is None:
            if current['shows']:
                raise StateFileError('An update requires its read snapshot; refusing whole-state overwrite')
            payload = normalized
        else:
            payload = merge_legacy(current, baseline, normalized)
        atomic_json(path, encode(payload))
