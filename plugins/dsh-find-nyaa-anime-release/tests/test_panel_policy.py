import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/find-nyaa-anime-release/scripts'))
from dsh_panel_policy import owns_track
from watch_v3.store import _delivery_mirror
from watch_v3.outbox import drain
from watch_v3 import finalization


def setup(tmp_path):
    state = tmp_path / 'state.json'
    state.with_suffix('.plans.json').write_text(json.dumps({'version': 1, 'plans': [{'trackId': 'panel'}]}))
    return state


def test_panel_delivery_never_mirrors_even_with_old_binding(tmp_path):
    state = setup(tmp_path)
    assert owns_track(state, 'panel')
    assert not _delivery_mirror(state, {'track_id': 'panel', 'bangumi': {'subject_id': 1}})
    assert _delivery_mirror(state, {'track_id': 'chat', 'bangumi': {'subject_id': 1}})


def test_old_delivery_outbox_held_but_explicit_user_action_allowed(tmp_path):
    state = setup(tmp_path)
    delivery = {'kind': 'bangumi_watched', 'status': 'pending', 'outbox_id': 'old', 'payload': {'source': 'delivery'}}
    explicit = {'kind': 'bangumi_watched', 'status': 'pending', 'outbox_id': 'new', 'payload': {'source': 'user'}}
    items = [delivery, explicit]
    applied = []
    def ack(tid, oid, **kwargs):
        assert kwargs['success']
        next(a for a in items if a['outbox_id'] == oid)['status'] = 'done'
    repo = SimpleNamespace(path=state, read=lambda: {'shows': [{'track_id': 'panel', 'outbox': items}]}, ack_outbox=ack)
    cloud = SimpleNamespace(apply_action=lambda tid, item: applied.append(item['outbox_id']))
    result = drain(repo, bangumi=cloud)
    assert applied == ['new']
    assert result[0]['status'] == 'manual_sync_required'
    assert delivery['status'] == 'pending'


def test_finalization_retains_panel_without_touching_state(tmp_path, monkeypatch):
    state = setup(tmp_path)
    monkeypatch.setattr(finalization, '_preview', lambda *a: {'status': 'finalization_preview', 'eligible': True, 'target_track_ids': ['panel']})
    repo = SimpleNamespace(path=state, read=lambda: {}, automation_inventory=lambda data: {})
    assert finalization.finalize(repo, 'panel', apply=True)['status'] == 'panel_record_retained'
    assert not state.exists()


def test_old_cleanup_outbox_cannot_delete_panel_schedule(tmp_path):
    state = setup(tmp_path)
    cleanup = {'kind': 'delete_owning_automation', 'status': 'pending', 'outbox_id': 'old-cleanup',
               'payload': {'target_track_ids': ['panel']}}
    repo = SimpleNamespace(path=state, read=lambda: {'shows': [{'track_id': 'panel', 'outbox': [cleanup]}]})
    result = drain(repo, automation=object())
    assert result[0]['status'] == 'panel_record_retained'
    assert cleanup['status'] == 'pending'
