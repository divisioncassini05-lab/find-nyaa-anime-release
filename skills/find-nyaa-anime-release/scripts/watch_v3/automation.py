"""Automation cleanup port. Deletion is exclusively a scheduler API operation."""
from dataclasses import dataclass
from typing import Protocol, Callable
from .store import digest, require, SUCCESS_STATUSES

@dataclass(frozen=True)
class AutomationSnapshot:
    automation_id: str
    exists: bool
    scope_hash: str | None
    target_track_ids: tuple[str, ...] = ()
    pending_retry_children: tuple[str, ...] = ()

class AutomationAdapter(Protocol):
    def inspect(self, automation_id: str) -> AutomationSnapshot: ...
    def delete(self, automation_id: str, *, expected_scope_hash: str, idempotency_key: str) -> dict: ...

class AutomationToolAdapter:
    """Inject the host's read/delete tools; never remove scheduler files directly."""
    def __init__(self, inspect: Callable, delete: Callable):
        self._inspect, self._delete = inspect, delete

    def inspect(self, automation_id):
        return self._inspect(automation_id)

    def delete(self, automation_id, *, expected_scope_hash, idempotency_key):
        current = self.inspect(automation_id)
        if not current.exists:
            return {'automation_id':automation_id, 'scope_hash':expected_scope_hash, 'status':'already_absent'}
        require(current.scope_hash == expected_scope_hash, 'automation_scope_changed')
        result = self._delete(automation_id, expected_scope_hash=expected_scope_hash, idempotency_key=idempotency_key)
        require(result.get('status') == 'deleted', 'automation_delete_failed')
        return {**result, 'automation_id':automation_id, 'scope_hash':expected_scope_hash}


def scope_hash(prompt):
    import hashlib
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()


def verify_cleanup(repo, action, adapter):
    owner = action['payload']
    snapshot = adapter.inspect(owner['automation_id'])
    require(snapshot.automation_id == owner['automation_id'], 'automation_id_mismatch')
    if snapshot.exists:
        require(snapshot.scope_hash == owner['scope_hash'], 'automation_scope_changed')
        require(set(snapshot.target_track_ids) == set(owner['target_track_ids']), 'automation_targets_changed')
        require(not snapshot.pending_retry_children, 'pending_retry_child')
    data = repo.read()
    for tid in owner['target_track_ids']:
        show = next((s for s in data['shows'] if s['track_id'] == tid), None)
        require(show is not None and show['lifecycle']['phase'] == 'completed', 'automation_targets_incomplete')
        require(owner in show['automation_owners'], 'automation_owner_changed')
        require(not any(not op.get('committed') and op.get('status') in {'prepared','recovering','accepted'} for op in show['operations'].values()), 'pending_delivery_recovery')
        final = show['broadcast']['completion']['final_episode']
        require(any(r.get('accepted') is True and r['status'] in SUCCESS_STATUSES and show['operations'][r['operation_id']].get('episode') == final for r in show['deliveries']), 'finale_receipt_required')
    return snapshot
