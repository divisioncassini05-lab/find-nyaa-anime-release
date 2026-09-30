"""At-least-once worker. External actions are idempotent and never enqueue torrents."""
from contextlib import ExitStack
from .automation import verify_cleanup
from anime_release.storage import file_lock


def drain(repo, *, automation=None, track_id=None):
    results = []
    # Separate worker lock; delivery holds only a per-work lock, never the
    # global state lock while doing network IO.
    with file_lock(repo.path.with_suffix('.outbox.lock')):
        for show in repo.read()['shows']:
            if track_id and show['track_id'] != track_id:
                continue
            for old in show['outbox']:
                current = repo.find(track_id=show['track_id'])
                item = next(x for x in current['outbox'] if x['outbox_id'] == old['outbox_id'])
                if item['status'] == 'done':
                    continue
                try:
                    result = None
                    if item['kind'] == 'reconcile_completion':
                        repo.command(show['track_id'], 'reconcile_completion')
                    elif item['kind'] == 'delete_owning_automation':
                        if automation is None:
                            results.append({'outbox_id':item['outbox_id'], 'status':'cleanup_pending',
                                            'required_tool':'automation_update', 'payload':item['payload']})
                            continue
                        owner = item['payload']
                        # Hold target locks while checking ownership and deleting;
                        # all state commands use the same per-work locks.
                        with ExitStack() as stack:
                            for tid in sorted(owner['target_track_ids']):
                                stack.enter_context(repo.work_lock(tid))
                            snapshot = verify_cleanup(repo, item, automation)
                            if snapshot.exists:
                                result = automation.delete(owner['automation_id'], expected_scope_hash=owner['scope_hash'], idempotency_key=item['outbox_id'])
                            else:
                                result = {'automation_id':owner['automation_id'], 'scope_hash':owner['scope_hash'], 'status':'already_absent'}
                    else:
                        raise ValueError('unknown_outbox_action')
                    repo.ack_outbox(show['track_id'], item['outbox_id'], success=True, receipt=result)
                    results.append({'outbox_id':item['outbox_id'], 'status':'done'})
                except Exception as exc:
                    repo.ack_outbox(show['track_id'], item['outbox_id'], success=False, error=str(exc))
                    results.append({'outbox_id':item['outbox_id'], 'status':'pending', 'error':str(exc)})
    return results
