"""Scoped, repeatable deletion after finale delivery and scheduler cleanup.

Completed records are kept only while cleanup is unfinished. There is no archive
or tombstone. Preview never creates locks, files, or scheduler actions.
"""
from contextlib import ExitStack
import copy

from anime_release.storage import atomic_json, file_lock
from .store import SUCCESS_STATUSES, _validate_completion, now_iso, require, validate


def related_tracks(data, track_id):
    """Include shared owners transitively; never infer ownership from a title."""
    selected = {track_id}
    while True:
        before = set(selected)
        for show in data['shows']:
            for owner in show.get('automation_owners', []):
                targets = set(owner.get('target_track_ids', []))
                if targets & selected:
                    selected.update(targets)
        if selected == before:
            return sorted(selected)


def completion_blockers(show):
    reasons = []
    if show['lifecycle']['phase'] != 'completed':
        reasons.append('scope_not_completed')
    completion = show['broadcast'].get('completion') or {}
    try:
        _validate_completion(show, completion)
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        reasons.append(str(exc))
    final = completion.get('final_episode')
    total = show['broadcast'].get('total_episodes')
    if type(final) is not int or final <= 0 or total != final:
        reasons.append('final_episode_scope_mismatch')
    if type(final) is int and show['progress']['handled_episode'] < final:
        reasons.append('finale_not_delivered')
    operations = show.get('operations', {})
    if any(not op.get('committed') and op.get('status') in {'prepared', 'recovering', 'accepted'}
           for op in operations.values()):
        reasons.append('pending_delivery_recovery')
    def accepted_finale(receipt):
        op = operations.get(receipt.get('operation_id'), {})
        return (receipt.get('accepted') is True and receipt.get('status') in SUCCESS_STATUSES
                and op.get('committed') is True and op.get('kind') == 'regular'
                and op.get('status') == 'accepted'
                and op.get('episode') == final and op.get('identity_revision') == show['identity_revision']
                and receipt.get('track_id') == op.get('track_id') == show['track_id']
                and receipt.get('info_hash') == op.get('info_hash') and bool(op.get('info_hash')))
    if not any(accepted_finale(r) for r in show.get('deliveries', [])):
        reasons.append('finale_receipt_required')
    return list(dict.fromkeys(reasons))


def _preview(data, track_id, inventory):
    by_id = {s['track_id']: s for s in data['shows']}
    if track_id not in by_id:
        return {'status': 'track_absent', 'track_id': track_id, 'eligible': False,
                'target_track_ids': [], 'blockers': [], 'deleted_track_ids': []}
    tids = related_tracks(data, track_id)
    reasons = []
    owners = {}
    for tid in tids:
        show = by_id.get(tid)
        if show is None:
            reasons.append({'track_id': tid, 'reason': 'automation_target_missing'})
            continue
        reasons.extend({'track_id': tid, 'reason': r} for r in completion_blockers(show))
        if any(a.get('status') != 'done' and a.get('kind') != 'reconcile_completion'
               for a in show.get('outbox', [])):
            reasons.append({'track_id': tid, 'reason': 'outbox_cleanup_pending'})
        for owner in show.get('automation_owners', []):
            owners[(owner['automation_id'], owner['scope_hash'])] = owner
    entries = inventory['automations']
    for entry in entries:
        matches = set(entry['referenced_track_ids']) & set(tids)
        for tid in sorted(matches):
            if tid in by_id and not any(o['automation_id'] == entry['automation_id'] for o in by_id[tid].get('automation_owners', [])):
                reasons.append({'track_id': tid, 'automation_id': entry['automation_id'],
                                'reason': 'automation_binding_required'})
    for owner in owners.values():
        aid, sha = owner['automation_id'], owner['scope_hash']
        records = [by_id.get(t) for t in owner['target_track_ids']]
        if (owner.get('cleanup_policy') != 'delete_when_all_targets_completed'
                or not all(s is not None and owner in s.get('automation_owners', []) for s in records)):
            reasons.append({'automation_id': aid, 'reason': 'automation_owner_changed'})
        if owner.get('pending_retry_children'):
            reasons.append({'automation_id': aid, 'reason': 'pending_retry_child'})
        live = next((e for e in entries if e['automation_id'] == aid), None)
        if live is not None:
            reason = 'automation_scope_changed' if live['scope_hash'] != sha else 'automation_cleanup_pending'
            reasons.append({'automation_id': aid, 'reason': reason, 'required_tool': 'automation_update'})
        acknowledged = any(
            a.get('kind') == 'delete_owning_automation' and a.get('status') == 'done'
            and a.get('payload') == owner and a.get('receipt', {}).get('automation_id') == aid
            and a['receipt'].get('scope_hash') == sha
            and a['receipt'].get('status') in {'deleted', 'already_absent'}
            for s in data['shows'] for a in s.get('outbox', []))
        if not acknowledged:
            reasons.append({'automation_id': aid, 'reason': 'automation_cleanup_receipt_required',
                            'required_tool': 'automation_update'})
    if inventory.get('errors'):
        reasons.append({'reason': 'automation_inventory_unavailable', 'errors': inventory['errors']})
    return {'status': 'finalization_preview', 'track_id': track_id, 'eligible': not reasons,
            'target_track_ids': tids, 'revisions': {t: by_id[t]['revision'] for t in tids if t in by_id},
            'blockers': reasons, 'deleted_track_ids': [],
            'records': [{'track_id': t, 'identity': copy.deepcopy(by_id[t]['identity']),
                         'progress': copy.deepcopy(by_id[t]['progress'])} for t in tids if t in by_id]}


def finalize(repo, track_id, *, apply=False, expected_revision=None):
    data = repo.read()
    preview = _preview(data, track_id, repo.automation_inventory(data))
    if not apply or preview['status'] == 'track_absent':
        return preview
    if not preview['eligible']:
        return {**preview, 'status': 'cleanup_pending'}
    # The worker takes this lock before work locks; use the same order here.
    with file_lock(repo.path.with_suffix('.outbox.lock')), ExitStack() as locks:
        for tid in preview['target_track_ids']:
            locks.enter_context(repo.work_lock(tid))
        with file_lock(repo.path.with_suffix(repo.path.suffix + '.lock')):
            data = repo.read()
            current = _preview(data, track_id, repo.automation_inventory(data))
            if current['status'] == 'track_absent':
                return current
            if current['target_track_ids'] != preview['target_track_ids']:
                return {**current, 'status': 'cleanup_pending', 'eligible': False,
                        'blockers': [{'reason': 'finalization_scope_changed'}]}
            if expected_revision is not None:
                require(current['revisions'][track_id] == expected_revision, 'revision_conflict')
            if not current['eligible']:
                return {**current, 'status': 'cleanup_pending'}
            from evidence_artifacts import cleanup
            try:
                artifacts = cleanup(repo, purge_tracks=set(current['target_track_ids']))
                require(not artifacts.get('retained_owned'), 'owned_artifacts_still_referenced')
                refreshed = _preview(data, track_id, repo.automation_inventory(data))
                require(refreshed['eligible'], 'automation_inventory_changed')
            except Exception as exc:
                return {**current, 'status': 'cleanup_pending', 'eligible': False,
                        'blockers': [{'reason': 'local_cleanup_failed', 'error': str(exc)}]}
            removed = set(current['target_track_ids'])
            data['shows'] = [s for s in data['shows'] if s['track_id'] not in removed]
            data['revision'] = data.get('revision', 0) + 1
            data['updated_at'] = now_iso()
            validate(data)
            atomic_json(repo.path, data)
            return {**current, 'status': 'local_record_deleted', 'deleted_track_ids': sorted(removed),
                    'artifacts': artifacts}
