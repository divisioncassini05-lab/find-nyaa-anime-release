"""Behavioral regression for complete removal; isolated state and fake hosts."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from anime_release.storage import StateFileError, atomic_json
from evidence_artifacts import new_workspace, register
from watch_v3.automation import AutomationSnapshot, local_inventory, scope_hash
from watch_v3.cli import run
from watch_v3.store import StateRepository
from watch_v3.workflow import Workflow, Request, render_report
from watch_v3.evidence import QualityPolicy
from watch_v3.outbox import drain
from test_watch_v3 import (make_repo, delivered, prepared, accepted, evidence,
                           mock_client, fake_validator, manifest, owner, bind, automation)


@pytest.fixture(autouse=True)
def isolated_inventory(tmp_path, monkeypatch):
    import watch_v3.automation as module
    real = module.local_inventory
    monkeypatch.setattr(module, 'local_inventory', lambda data: real(data, tmp_path / 'automations'))


def complete(repo, tid='t', opid='op'):
    delivered(repo, tid=tid, opid=opid)
    repo.attach_completion(tid, evidence(tid))


def reasons(result):
    return {b['reason'] for b in result['blockers']}


def test_preview_is_byte_exact_read_only_and_no_archive(tmp_path):
    repo = make_repo(tmp_path)
    complete(repo)
    before = repo.path.read_bytes()
    files = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = repo.finalize('t')
    assert result['eligible'] is True and result['status'] == 'finalization_preview'
    assert repo.path.read_bytes() == before
    assert files == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert repo.finalize('t', apply=True)['status'] == 'local_record_deleted'
    assert repo.read()['shows'] == []
    assert repo.finalize('t', apply=True)['status'] == 'track_absent'
    assert not list(tmp_path.glob('*.bak')) and not list(tmp_path.glob('*archive*'))


@pytest.mark.parametrize('evidence_first', [True, False])
def test_final_delivery_and_later_reconcile_auto_remove(tmp_path, capsys, evidence_first):
    repo = make_repo(tmp_path)
    client = mock_client()
    if evidence_first:
        repo.attach_completion('t', evidence())
    request = Request('Demo', manifest(tmp_path), QualityPolicy())
    result = Workflow(repo, client, fake_validator()).deliver(request)
    assert result.status == 'delivery_recorded'
    if evidence_first:
        assert result.post_commit['finalization']['status'] == 'local_record_deleted'
        report = render_report(repo, result)
        assert report['progress']['handled_episode'] == 13 and not report['local_record_exists']
    else:
        assert repo.find(track_id='t')['lifecycle']['phase'] == 'finale_pending_evidence'
        path = tmp_path/'completion.json'
        path.write_text(json.dumps(evidence()), encoding='utf8')
        assert run(['--state', str(repo.path), 'reconcile', 'Demo', '--completion-evidence', str(path)]) == 0
        assert json.loads(capsys.readouterr().out)['status'] == 'local_record_deleted'
    assert repo.find(track_id='t') is None
    again = Workflow(repo, client, fake_validator()).deliver(request)
    assert again.status == 'track_absent' and client.submit.call_count == 1
    assert Workflow(repo, client).recover(result.operation_id).status == 'track_absent'
    assert repo.read()['shows'] == []


def test_recovery_of_accepted_finale_auto_removes_without_resubmission(tmp_path):
    repo = make_repo(tmp_path)
    repo.attach_completion('t', evidence())
    request = prepared(repo)
    repo.command('t', 'record_delivery', receipt=accepted(request), acceptance_only=True)
    client = mock_client()
    result = Workflow(repo, client).recover('op')
    assert result.status == 'recovered'
    assert result.post_commit['finalization']['status'] == 'local_record_deleted'
    client.submit.assert_not_called()
    client.inspect.assert_not_called()
    assert render_report(repo, result)['progress']['handled_episode'] == 13


@pytest.mark.parametrize('fault', ['missing_receipt', 'metadata', 'prepared', 'split', 'multi'])
def test_incomplete_proof_blocks_deletion(tmp_path, fault):
    repo = make_repo(tmp_path)
    complete(repo)
    data = repo.read()
    show = data['shows'][0]
    if fault == 'missing_receipt':
        show['deliveries'] = []
    elif fault == 'metadata':
        show['broadcast']['completion']['source_kind'] = 'metadata'
    elif fault == 'prepared':
        op = copy.deepcopy(show['operations']['op'])
        op.update(operation_id='uncommitted', status='recovering', committed=False)
        show['operations']['uncommitted'] = op
    elif fault == 'split':
        show['broadcast']['split_cour_pending'] = True
    else:
        show['broadcast']['mainline_scope'] = 'multi'
    atomic_json(repo.path, data)
    before = repo.path.read_bytes()
    result = repo.finalize('t', apply=True)
    assert result['status'] == 'cleanup_pending' and result['blockers']
    assert repo.path.read_bytes() == before


@pytest.mark.parametrize('fault', ['hash', 'episode', 'identity_revision', 'committed'])
def test_finale_receipt_must_match_current_operation(tmp_path, fault):
    repo = make_repo(tmp_path)
    complete(repo)
    data = repo.read()
    show = data['shows'][0]
    if fault == 'hash':
        # A matching receipt+operation hash still cannot point to another track.
        show['deliveries'][0]['track_id'] = 'other'
    elif fault == 'episode':
        show['operations']['op']['episode'] = 12
    elif fault == 'identity_revision':
        show['operations']['op']['identity_revision'] = 1
    else:
        show['operations']['op']['committed'] = False
    atomic_json(repo.path, data)
    assert 'finale_receipt_required' in reasons(repo.finalize('t'))


def test_shared_owner_waits_for_every_target_then_deletes_together(tmp_path):
    repo = make_repo(tmp_path)
    repo.command('u', 'create_track', identity={'title':'Other', 'season':'S01'}, broadcast={'total_episodes':13})
    own = owner(('t', 'u'))
    bind(repo, own)
    complete(repo)
    assert not repo.finalize('t')['eligible']
    complete(repo, 'u', 'u-op')
    adapter = automation(own)
    drain(repo, automation=adapter, track_id='u')
    assert adapter.delete.call_count == 1
    result = repo.finalize('u', apply=True)
    assert result['deleted_track_ids'] == ['t', 'u'] and repo.read()['shows'] == []


def test_scheduler_failure_keeps_record_then_absence_receipt_finishes(tmp_path):
    repo = make_repo(tmp_path)
    own = owner()
    bind(repo, own)
    complete(repo)
    adapter = automation(own)
    adapter.delete.side_effect = RuntimeError('offline')
    drain(repo, automation=adapter, track_id='t')
    assert repo.finalize('t', apply=True)['status'] == 'cleanup_pending'
    assert repo.find(track_id='t')['operations']['op']['committed']
    adapter.inspect.return_value = AutomationSnapshot(own['automation_id'], False, None)
    drain(repo, automation=adapter, track_id='t')
    assert repo.finalize('t', apply=True)['status'] == 'local_record_deleted'
    assert adapter.delete.call_count == 1


def test_crash_after_external_delete_keeps_receipt_work_recoverable(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    own = owner()
    bind(repo, own)
    complete(repo)
    adapter = automation(own)
    original = repo.ack_outbox
    def crash(tid, outbox_id, **kw):
        if outbox_id.startswith('cleanup:') and kw.get('success'):
            raise KeyboardInterrupt()
        return original(tid, outbox_id, **kw)
    monkeypatch.setattr(repo, 'ack_outbox', crash)
    with pytest.raises(KeyboardInterrupt):
        drain(repo, automation=adapter, track_id='t')
    assert repo.find(track_id='t') is not None
    monkeypatch.setattr(repo, 'ack_outbox', original)
    adapter.inspect.return_value = AutomationSnapshot(own['automation_id'], False, None)
    drain(repo, automation=adapter, track_id='t')
    assert repo.finalize('t', apply=True)['status'] == 'local_record_deleted'
    assert adapter.delete.call_count == 1


def test_cli_ack_deletes_local_after_real_receipt(tmp_path, capsys):
    repo = make_repo(tmp_path)
    own = owner()
    bind(repo, own)
    complete(repo)
    action = next(a for a in repo.find(track_id='t')['outbox'] if a['kind'] == 'delete_owning_automation')
    receipt_path = tmp_path/'deleted.json'
    receipt_path.write_text(json.dumps({'automation_id':own['automation_id'], 'scope_hash':own['scope_hash'],
                                      'status':'deleted'}), encoding='utf8')
    assert run(['--state',str(repo.path),'ack-outbox','--track-id','t','--outbox-id',action['outbox_id'],
                '--receipt',str(receipt_path)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'local_record_deleted'
    assert repo.find(track_id='t') is None


def test_unbound_saved_task_blocks_ownerless_deletion(tmp_path):
    repo = make_repo(tmp_path)
    complete(repo)
    directory = tmp_path/'automations'/'old'
    directory.mkdir(parents=True)
    (directory/'automation.toml').write_text('id = "old"\nname = "追番 Demo"\nprompt = "Track Demo"\n',encoding='utf8')
    assert 'automation_binding_required' in reasons(repo.finalize('t'))
    (directory/'automation.toml').write_text('invalid toml !!',encoding='utf8')
    assert 'automation_inventory_unavailable' in reasons(repo.finalize('t'))


def test_deleted_task_reappearing_with_new_scope_blocks_local_deletion(tmp_path):
    repo = make_repo(tmp_path)
    own = owner()
    bind(repo, own)
    complete(repo)
    drain(repo, automation=automation(own), track_id='t')
    directory = tmp_path/'automations'/own['automation_id']
    directory.mkdir(parents=True)
    (directory/'automation.toml').write_text(f'id = "{own["automation_id"]}"\nprompt = "Demo new scope"\n',encoding='utf8')
    assert 'automation_scope_changed' in reasons(repo.finalize('t'))


def test_concurrent_finalize_and_stale_revision(tmp_path):
    repo = make_repo(tmp_path)
    complete(repo)
    revision = repo.find(track_id='t')['revision']
    with pytest.raises(StateFileError, match='revision_conflict'):
        repo.finalize('t', apply=True, expected_revision=revision-1)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _:repo.finalize('t',apply=True),range(2)))
    assert sorted(r['status'] for r in results) == ['local_record_deleted', 'track_absent']
    assert repo.read()['shows'] == []


def test_unrelated_completed_tracks_are_not_swept(tmp_path):
    repo = make_repo(tmp_path)
    repo.command('u', 'create_track', identity={'title':'Other', 'season':'S01'},broadcast={'total_episodes':13})
    complete(repo, 'u', 'u-op')
    before_other = copy.deepcopy(repo.find(track_id='u'))
    repo.attach_completion('t', evidence())
    Workflow(repo, mock_client(), fake_validator()).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    assert repo.find(track_id='t') is None and repo.find(track_id='u') == before_other


def test_owned_evidence_removed_but_video_and_foreign_files_preserved(tmp_path):
    repo = make_repo(tmp_path)
    complete(repo)
    directory = new_workspace(repo.path)
    listing = directory/'listing.json'
    listing.write_text('{}',encoding='utf8')
    review = directory/'review.json'
    review.write_text(json.dumps({'track_id':'t','listing_reports':[str(listing)]}),encoding='utf8')
    for path in (listing,review): register(path,repo.path)
    outside = tmp_path/'episode.mkv'
    outside.write_bytes(b'video')
    data = repo.read()
    data['shows'][0]['operations']['op'].update(review_path=str(review),torrent_path=str(outside))
    atomic_json(repo.path,data)
    result = repo.finalize('t',apply=True)
    assert result['status'] == 'local_record_deleted' and not directory.exists()
    assert outside.read_bytes() == b'video'


def test_artifact_cleanup_failure_keeps_record_for_retry(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    complete(repo)
    import evidence_artifacts
    monkeypatch.setattr(evidence_artifacts,'cleanup',Mock(side_effect=OSError('locked file')))
    assert repo.finalize('t',apply=True)['status'] == 'cleanup_pending'
    assert repo.find(track_id='t') is not None


def test_state_write_failure_does_not_remove_record(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    complete(repo)
    import watch_v3.finalization as module
    monkeypatch.setattr(module,'atomic_json',Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError): repo.finalize('t',apply=True)
    assert repo.find(track_id='t') is not None


def test_cli_preview_and_read_commands_never_remove(tmp_path, capsys):
    repo = make_repo(tmp_path)
    complete(repo)
    before = repo.path.read_bytes()
    for command in [['finalize','--track-id','t'],['inspect','Demo'],['migrate']]:
        assert run(['--state',str(repo.path),*command]) == 0
        capsys.readouterr()
        assert repo.path.read_bytes() == before
    assert run(['--state',str(repo.path),'finalize','--track-id','t','--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'local_record_deleted'
    assert run(['--state',str(repo.path),'finalize','--track-id','t','--apply']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'track_absent'
