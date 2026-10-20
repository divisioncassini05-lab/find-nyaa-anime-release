"""Automation cleanup port. Deletion is exclusively a scheduler API operation."""
from dataclasses import dataclass
from typing import Protocol, Callable
from .store import require

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
    from .finalization import completion_blockers
    for tid in owner['target_track_ids']:
        show = next((s for s in data['shows'] if s['track_id'] == tid), None)
        require(show is not None and not completion_blockers(show), 'automation_targets_incomplete')
        require(owner in show['automation_owners'], 'automation_owner_changed')
    return snapshot


def local_inventory(data, directory=None):
    """Read saved configs; a possible unbound title match blocks deletion.

    This is conservative detection, not semantic ownership inference. Actual
    deletion still requires the bound automation's host-tool receipt.
    """
    import os
    import re
    import tomllib
    from pathlib import Path
    base = Path(directory) if directory is not None else Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'automations'
    entries, errors = [], []
    try:
        configs = sorted(base.glob('*/automation.toml'))
    except OSError as exc:
        return {'automations': [], 'errors': [str(exc)]}
    for path in configs:
        try:
            config = tomllib.loads(path.read_text(encoding='utf-8-sig'))
            aid, prompt = config['id'], config['prompt']
            require(isinstance(aid, str) and isinstance(prompt, str), 'invalid_automation_config')
            text = (prompt + '\n' + config.get('name', '')).casefold()
            matches = []
            for show in data['shows']:
                tid = show['track_id']
                names = [show['identity']['title'], *show['identity'].get('aliases', [])]
                explicit = re.search(r'(?<![\w-])' + re.escape(tid.casefold()) + r'(?![\w-])', text)
                named = any(name and (re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', text)
                                      if name.isascii() else name.casefold() in text) for name in names)
                if explicit or named:
                    matches.append(tid)
            entries.append({'automation_id': aid, 'scope_hash': scope_hash(prompt),
                            'referenced_track_ids': matches})
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errors.append({'path': str(path), 'error': str(exc)})
    if len({e['automation_id'] for e in entries}) != len(entries):
        errors.append({'error': 'duplicate_automation_id'})
    return {'automations': entries, 'errors': errors}
