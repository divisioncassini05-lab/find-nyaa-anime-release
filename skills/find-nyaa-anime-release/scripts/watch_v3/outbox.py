"""At-least-once worker. External actions are idempotent and never enqueue torrents."""
from contextlib import ExitStack
from .automation import verify_cleanup
from .finalization import related_tracks
from anime_release.storage import file_lock


def drain(repo, *, automation=None, track_id=None):
    results = []
    # Separate worker lock; delivery holds only a per-work lock, never the
    # global state lock while doing network IO.
    with file_lock(repo.path.with_suffix('.outbox.lock')):
        processed = set()
        while True:
            data = repo.read()
            selected = set(related_tracks(data, track_id)) if track_id else {s['track_id'] for s in data['shows']}
            pending = [(s['track_id'], a) for s in data['shows'] if s['track_id'] in selected
                       for a in s['outbox'] if a['status'] != 'done'
                       and (s['track_id'], a['outbox_id']) not in processed]
            if not pending:
                break
            tid, item = pending[0]
            processed.add((tid, item['outbox_id']))
            try:
                result = None
                if item['kind'] == 'reconcile_completion':
                    repo.command(tid, 'reconcile_completion')
                elif item['kind'] == 'delete_owning_automation':
                    if automation is None:
                        results.append({'track_id':tid, 'outbox_id':item['outbox_id'], 'status':'cleanup_pending',
                                        'required_tool':'automation_update', 'payload':item['payload']})
                        continue
                    owner = item['payload']
                    with ExitStack() as stack:
                        for target in sorted(owner['target_track_ids']):
                            stack.enter_context(repo.work_lock(target))
                        snapshot = verify_cleanup(repo, item, automation)
                        if snapshot.exists:
                            result = automation.delete(owner['automation_id'], expected_scope_hash=owner['scope_hash'], idempotency_key=item['outbox_id'])
                        else:
                            result = {'automation_id':owner['automation_id'], 'scope_hash':owner['scope_hash'], 'status':'already_absent'}
                        # Keep ownership locks through the receipt commit.
                        repo.ack_outbox(tid, item['outbox_id'], success=True, receipt=result)
                    results.append({'track_id':tid, 'outbox_id':item['outbox_id'], 'status':'done'})
                    continue
                else:
                    raise ValueError('unknown_outbox_action')
                repo.ack_outbox(tid, item['outbox_id'], success=True, receipt=result)
                results.append({'track_id':tid, 'outbox_id':item['outbox_id'], 'status':'done'})
            except Exception as exc:
                repo.ack_outbox(tid, item['outbox_id'], success=False, error=str(exc))
                results.append({'track_id':tid, 'outbox_id':item['outbox_id'], 'status':'pending', 'error':str(exc)})
    return results
