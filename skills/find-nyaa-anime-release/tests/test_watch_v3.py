"""Local workflow acceptance: real repository and fault injection, no live clients."""
import copy
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from anime_release.storage import StateFileError, atomic_json
from watch_v3.store import StateRepository, migrate_state, now_iso
from watch_v3.clients import DeliveryRequest, ClientContext, AcceptanceEvidence, receipt, ClientFailure
from watch_v3.evidence import QualityPolicy, SelectionResult
from watch_v3.workflow import Workflow, Request, commit_delivery
from watch_v3.outbox import drain
from watch_v3.automation import AutomationSnapshot, AutomationToolAdapter

HASH = 'a' * 40

def make_repo(tmp_path, total=13):
    repo = StateRepository(tmp_path/'state.json')
    repo.command('t', 'create_track', identity={'title':'Demo', 'season':'S01'}, broadcast={'total_episodes':total})
    return repo


def evidence(tid='t', final=13):
    return {'reviewed':True, 'confirmed':True, 'track_id':tid, 'identity_revision':0,
            'season':'S01', 'source_kind':'official', 'source_url':'https://example.test/finale',
            'evidence_text':'Final episode', 'checked_at':now_iso(), 'final_episode':final}


def prepared(repo, episode=13, tid='t', opid='op', info_hash=HASH):
    request = DeliveryRequest(tid, opid, info_hash, 'magnet:?xt=urn:btih:'+info_hash)
    repo.command(tid, 'record_pending_operation', operation={'operation_id':opid, 'track_id':tid,
        'identity_revision':0, 'info_hash':info_hash, 'episode':episode, 'kind':'regular', 'request':asdict(request)})
    return request


def accepted(request, status='submitted_verified'):
    return asdict(receipt(request, status, AcceptanceEvidence(request.info_hash, True)))


def delivered(repo, **kw):
    request = prepared(repo, **kw)
    commit_delivery(repo, request.track_id, accepted(request))
    return request


def mock_client():
    client = Mock()
    client.preflight.return_value = ClientContext('fake', True)
    client.inspect.side_effect = lambda h: AcceptanceEvidence(h, False)
    client.submit.side_effect = lambda r: receipt(r, 'submitted_verified', AcceptanceEvidence(r.info_hash, True))
    return client


def manifest(tmp_path, tid='t'):
    path = tmp_path/(tid+'-review.json')
    path.write_text(json.dumps({'reviewed':True, 'track_id':tid}), encoding='utf8')
    return path


def fake_validator(episode=13, tid='t'):
    result = SimpleNamespace(info_hash=HASH, magnet='magnet:?xt=urn:btih:'+HASH,
        source_url='https://nyaa.si/view/1', target=SimpleNamespace(episode=episode), candidate_id='1')
    validator = Mock()
    validator.validate.return_value = SelectionResult(result, {'status':'found'})
    return validator


def owner(ids=('t',)):
    return {'automation_id':'automation-4','scope_hash':'b'*64,'target_track_ids':list(ids),
            'cleanup_policy':'delete_when_all_targets_completed','pending_retry_children':[]}


def bind(repo, ownership):
    for tid in ownership['target_track_ids']:
        repo.command(tid, 'append_outbox_action', owner=ownership)


def automation(ownership):
    live = Mock()
    live.inspect.return_value = AutomationSnapshot(ownership['automation_id'], True, ownership['scope_hash'], tuple(ownership['target_track_ids']))
    live.delete.return_value = {'automation_id':ownership['automation_id'], 'scope_hash':ownership['scope_hash'], 'status':'deleted'}
    return live

@pytest.mark.parametrize('evidence_first',[True,False])
def test_finale_order_independent(tmp_path, evidence_first):
    repo=make_repo(tmp_path)
    if evidence_first: repo.attach_completion('t',evidence())
    delivered(repo)
    if not evidence_first:
        assert repo.find(track_id='t')['lifecycle']['phase']=='finale_pending_evidence'
        assert repo.find(track_id='t')['progress']['target_episode'] is None
        repo.attach_completion('t',evidence())
    show=repo.find(track_id='t')
    assert show['lifecycle']['phase']=='completed'
    assert show['progress']['handled_episode']==13 and show['progress']['target_episode'] is None


def test_prepared_and_failed_do_not_advance(tmp_path):
    repo=make_repo(tmp_path); req=prepared(repo)
    repo.command('t','record_failed_operation',operation_id='op',recovery={'error_code':'handoff_unverified'})
    assert repo.find(track_id='t')['progress']['handled_episode']==0
    bad=accepted(req); bad['status']='handoff_unverified'
    with pytest.raises(StateFileError,match='not_accepted'): repo.command('t','record_delivery',receipt=bad)
    assert repo.find(track_id='t')['progress']['handled_episode']==0


def test_accepted_commit_failure_recovers_without_client(tmp_path,monkeypatch):
    repo=make_repo(tmp_path); original=repo.command
    def fail(tid,kind,**kw):
        if kind=='record_delivery' and not kw.get('acceptance_only'): raise OSError('disk full')
        return original(tid,kind,**kw)
    monkeypatch.setattr(repo,'command',fail)
    client=mock_client()
    result=Workflow(repo,client,fake_validator()).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    assert result.status=='accepted_receipt_commit_failed'
    assert repo.find(track_id='t')['progress']['handled_episode']==0
    monkeypatch.setattr(repo,'command',original)
    client.reset_mock()
    result=Workflow(repo,client).recover(result.operation_id)
    assert result.status=='recovered'
    client.submit.assert_not_called(); client.inspect.assert_not_called(); client.preflight.assert_not_called()
    assert repo.find(track_id='t')['progress']['handled_episode']==13


def test_crash_after_client_before_receipt_recovers_exact_hash(tmp_path):
    repo=make_repo(tmp_path); prepared(repo)
    client=mock_client(); client.inspect.side_effect=lambda h:AcceptanceEvidence(h,True)
    Workflow(repo,client).recover('op')
    client.submit.assert_not_called()
    client.inspect.assert_called_once_with(HASH)
    assert repo.find(track_id='t')['progress']['handled_episode']==13


def test_completed_repeat_has_no_discovery_or_client(tmp_path):
    repo=make_repo(tmp_path); delivered(repo); repo.attach_completion('t',evidence())
    client=mock_client(); validator=fake_validator()
    result=Workflow(repo,client,validator).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    assert result.status=='completed'; validator.validate.assert_not_called(); client.submit.assert_not_called()


def test_completed_waiting_and_old_delivery_do_not_reopen(tmp_path):
    repo=make_repo(tmp_path); req=delivered(repo); repo.attach_completion('t',evidence())
    repo.command('t','record_waiting',reason='late retry')
    repo.command('t','record_delivery',receipt=accepted(req))
    assert repo.find(track_id='t')['lifecycle']['phase']=='completed'
    assert repo.find(track_id='t')['progress']['target_episode'] is None
    assert len(repo.find(track_id='t')['deliveries'])==1


def test_completion_conflict_blocks_preserving_progress(tmp_path):
    repo=make_repo(tmp_path); delivered(repo)
    repo.attach_completion('t',evidence(final=14))
    show=repo.find(track_id='t'); assert show['lifecycle']['phase']=='blocked'
    assert show['progress']['handled_episode']==13
    client=mock_client(); validator=fake_validator()
    result=Workflow(repo,client,validator).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    assert result.status=='blocked'; client.submit.assert_not_called(); validator.validate.assert_not_called()


def test_due_date_does_not_veto_undelivered_finale(tmp_path):
    repo=StateRepository(tmp_path/'state.json')
    repo.command('t','create_track',identity={'title':'Demo','season':'S01'},broadcast={'total_episodes':13,'completion':{'end_date':'2000-01-01','confirmed':False}})
    assert repo.find(track_id='t')['lifecycle']['phase']=='finale_pending_evidence'
    assert repo.find(track_id='t')['progress']['target_episode']==1
    client=mock_client()
    Workflow(repo,client,fake_validator()).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    client.submit.assert_called_once()


def test_worker_crash_does_not_lose_event(tmp_path,monkeypatch):
    repo=make_repo(tmp_path); delivered(repo)
    original=repo.ack_outbox
    monkeypatch.setattr(repo,'ack_outbox',lambda *a,**k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): drain(repo)
    monkeypatch.setattr(repo,'ack_outbox',original)
    assert drain(repo)[0]['status']=='done'
    assert drain(repo)==[]
    assert len(repo.find(track_id='t')['deliveries'])==1

@pytest.mark.parametrize('fail',[False,True])
def test_cleanup_success_failure_and_replay(tmp_path,fail):
    repo=make_repo(tmp_path); o=owner(); bind(repo,o); delivered(repo); repo.attach_completion('t',evidence())
    adapter=automation(o)
    if fail: adapter.delete.side_effect=RuntimeError('offline')
    results=drain(repo,automation=adapter)
    assert results[-1]['status']==('pending' if fail else 'done')
    if fail:
        adapter.delete.side_effect=None
        adapter.inspect.return_value=AutomationSnapshot(o['automation_id'],False,None)
        results=drain(repo,automation=adapter)
        assert results[-1]['status']=='done'
    before=adapter.delete.call_count
    assert drain(repo,automation=adapter)==[]
    assert adapter.delete.call_count==before


def test_cleanup_requires_all_tracks_and_final_receipts(tmp_path):
    repo=make_repo(tmp_path); repo.command('u','create_track',identity={'title':'Other','season':'S01'},broadcast={'total_episodes':13})
    o=owner(('t','u')); bind(repo,o)
    delivered(repo); repo.attach_completion('t',evidence())
    assert not any(a['kind']=='delete_owning_automation' for s in repo.read()['shows'] for a in s['outbox'])
    delivered(repo,tid='u',opid='other'); repo.attach_completion('u',evidence('u'))
    assert len([a for s in repo.read()['shows'] for a in s['outbox'] if a['kind']=='delete_owning_automation'])==1

@pytest.mark.parametrize('changed',['scope','targets','child','id'])
def test_cleanup_checks_live_scope(tmp_path,changed):
    repo=make_repo(tmp_path); o=owner(); bind(repo,o); delivered(repo); repo.attach_completion('t',evidence())
    adapter=automation(o)
    adapter.inspect.return_value=AutomationSnapshot('other' if changed=='id' else o['automation_id'], True,
        'changed' if changed=='scope' else o['scope_hash'], ('other',) if changed=='targets' else ('t',), ('retry',) if changed=='child' else ())
    results=drain(repo,automation=adapter)
    assert results[-1]['status']=='pending'; adapter.delete.assert_not_called()


def test_cleanup_missing_adapter_stays_pending(tmp_path):
    repo=make_repo(tmp_path); o=owner(); bind(repo,o); delivered(repo); repo.attach_completion('t',evidence())
    assert drain(repo)[-1]['status']=='cleanup_pending'


def test_revision_and_operation_hash_conflict(tmp_path):
    repo=make_repo(tmp_path); prepared(repo)
    with pytest.raises(StateFileError,match='revision_conflict'): repo.command('t','record_waiting',expected_revision=0)
    with pytest.raises(StateFileError,match='identity_conflict'): prepared(repo,info_hash='b'*40)


def test_same_track_concurrent_delivery_submits_once(tmp_path):
    repo=make_repo(tmp_path); client=mock_client(); validator=fake_validator()
    req=Request('Demo',manifest(tmp_path),QualityPolicy())
    def job(_): return Workflow(repo,client,validator).deliver(req)
    with ThreadPoolExecutor(2) as pool: outcomes=list(pool.map(job,range(2)))
    assert client.submit.call_count==1
    assert repo.find(track_id='t')['progress']['handled_episode']==13


def test_different_tracks_concurrent_progress(tmp_path):
    repo=make_repo(tmp_path,total=20)
    repo.command('u','create_track',identity={'title':'Other','season':'S01'},broadcast={'total_episodes':20})
    def job(tid): delivered(repo,episode=12,tid=tid,opid=tid)
    with ThreadPoolExecutor(2) as pool: list(pool.map(job,['t','u']))
    assert [s['progress']['handled_episode'] for s in repo.read()['shows']]==[12,12]


def legacy():
    return {'version':1,'shows':[{'title':'Demo','season':'S01','anilist_id':123,'aliases':['Alias'],
        'watched_episode':13,'next_episode':14,'latest_known_episode':13,'total_episodes':13,
        'pending_download':{'hash':HASH},'custom_evidence':'keep','completion':{'confirmed':False}}]}


def test_migration_lossless_deterministic_and_no_fake_next(tmp_path):
    old=legacy(); one=migrate_state(old); two=migrate_state(old)
    s=one['shows'][0]
    assert s['track_id']==two['shows'][0]['track_id']
    assert s['extra']['pending_download']==old['shows'][0]['pending_download']
    assert s['extra']['custom_evidence']=='keep'
    assert s['identity']['provider_bindings']['anilist']['entry_id']==123
    assert s['lifecycle']['phase']=='finale_pending_evidence' and s['progress']['target_episode'] is None
    path=tmp_path/'old.json'; atomic_json(path,old); before=path.read_bytes(); repo=StateRepository(path)
    with pytest.raises(StateFileError,match='migration_required'): repo.read()
    repo.migrate(expected_sha256=hashlib.sha256(before).hexdigest())
    assert list(tmp_path.glob('*.v2.bak'))[0].read_bytes()==before
    assert repo.read()['shows'][0]['track_id']==s['track_id']


def test_migration_changed_hash_rejected(tmp_path):
    path=tmp_path/'old.json'; atomic_json(path,legacy()); repo=StateRepository(path)
    with pytest.raises(StateFileError,match='source_changed'): repo.migrate(expected_sha256='wrong')
    assert json.loads(path.read_text())['version']==1


def test_migration_keeps_v3_blocked_and_outbox(tmp_path):
    repo=make_repo(tmp_path); delivered(repo); repo.attach_completion('t',evidence(final=14))
    original=repo.read()
    assert migrate_state(original)==original


def test_migration_rejects_duplicate_tracks():
    data=legacy(); data['shows'][0]['track_id']='t'; data['shows'].append(copy.deepcopy(data['shows'][0]))
    with pytest.raises((StateFileError,ValueError)): migrate_state(data)


def test_legacy_writers_cannot_touch_v3(tmp_path):
    from anime_release.repository import StateRepository as LegacyRepo, save_legacy
    from anime_release.models import StateCommand
    repo=make_repo(tmp_path); before=repo.path.read_bytes()
    with pytest.raises(Exception): LegacyRepo(repo.path).commit(StateCommand('t','waiting',fields={}))
    with pytest.raises(Exception): save_legacy(repo.path,legacy())
    assert repo.path.read_bytes()==before

def test_migrated_receipts_are_committed_not_pending(tmp_path):
    repo=make_repo(tmp_path,total=20); req=delivered(repo,episode=12)
    old={'version':2,'shows':[{'track_id':'t','revision':1,'identity_revision':0,
        'identity':{'title':'Demo','season':'S01'},'bindings':{},'broadcast':{'total_episodes':20},
        'progress':{'watched_episode':12,'next_episode':13},'retrieval':{},
        'operations':{'op':{'operation_id':'op','info_hash':HASH,'episode':12,'kind':'regular','status':'accepted','receipt':accepted(req)}},
        'deliveries':[accepted(req)],'extra':{}}]}
    converted=migrate_state(old)
    op=converted['shows'][0]['operations']['op']
    assert op['committed'] is True and op['track_id']=='t'
    assert op['request']['info_hash']==HASH
    atomic_json(repo.path,converted)
    client=mock_client()
    result=Workflow(repo,client).recover('op')
    assert result.status=='already_accepted'; client.submit.assert_not_called(); client.preflight.assert_not_called()


def test_same_operation_replay_no_extra_client_call(tmp_path):
    repo=make_repo(tmp_path,total=20); client=mock_client(); validator=fake_validator(episode=12)
    request=Request('Demo',manifest(tmp_path),QualityPolicy())
    flow=Workflow(repo,client,validator)
    assert flow.deliver(request).status=='delivery_recorded'
    assert flow.deliver(request).status=='already_accepted'
    assert client.submit.call_count==1


def test_worker_failure_preserves_success_receipt(tmp_path,monkeypatch):
    repo=make_repo(tmp_path); client=mock_client()
    import watch_v3.workflow as module
    monkeypatch.setattr(module,'drain_outbox',Mock(side_effect=OSError('worker unavailable')))
    result=Workflow(repo,client,fake_validator()).deliver(Request('Demo',manifest(tmp_path),QualityPolicy()))
    assert result.status=='delivery_recorded' and result.receipt['accepted'] is True
    assert result.post_commit['status']=='outbox_pending'
    assert repo.find(track_id='t')['progress']['handled_episode']==13


def test_migration_rejects_orphan_receipt():
    data=legacy(); data['shows'][0]['deliveries']=[{'operation_id':'missing','info_hash':HASH}]
    with pytest.raises(StateFileError,match='orphan_receipt'): migrate_state(data)


def test_migration_rejects_conflicting_flat_season():
    data={'version':2,'shows':[{'track_id':'t','season':'S02','identity':{'title':'Demo','season':'S01'}}]}
    with pytest.raises(StateFileError,match='season_conflict'): migrate_state(data)


def test_migration_keeps_accepted_uncommitted_operation_recoverable(tmp_path):
    repo=make_repo(tmp_path); req=prepared(repo)
    data={'version':2,'shows':[{'track_id':'t','identity_revision':0,'identity':{'title':'Demo','season':'S01'},
        'bindings':{},'broadcast':{'total_episodes':13},'progress':{'watched_episode':12,'next_episode':13},
        'operations':{'op':{'operation_id':'op','info_hash':HASH,'episode':13,'kind':'regular','status':'accepted','receipt':accepted(req)}},'deliveries':[]}]}
    atomic_json(repo.path,migrate_state(data))
    client=mock_client()
    assert Workflow(repo,client).recover('op').status=='recovered'
    client.submit.assert_not_called()
    assert repo.find(track_id='t')['progress']['handled_episode']==13


def test_cli_read_only_and_required_delivery_flags(tmp_path,capsys):
    from watch_v3.cli import run
    repo=make_repo(tmp_path); before=repo.path.read_bytes()
    assert run(['--state',str(repo.path),'inspect','Demo'])==0
    assert repo.path.read_bytes()==before
    capsys.readouterr()
    with pytest.raises(SystemExit): run(['--state',str(repo.path),'deliver','--review','unused.json'])
    assert repo.path.read_bytes()==before


def test_process_exit_after_acceptance_recovery(tmp_path):
    import subprocess,sys
    repo=make_repo(tmp_path)
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    code="""
import sys,os,json
from pathlib import Path
from watch_v3.store import StateRepository
from watch_v3.clients import DeliveryRequest, AcceptanceEvidence, receipt
from dataclasses import asdict
repo=StateRepository(sys.argv[1])
r=DeliveryRequest('t','crash-op','a'*40,'magnet:?xt=urn:btih:'+'a'*40)
repo.command('t','record_pending_operation',operation={'operation_id':r.operation_id,'track_id':'t','identity_revision':0,'info_hash':r.info_hash,'episode':13,'kind':'regular','request':asdict(r)})
repo.command('t','record_delivery',receipt=asdict(receipt(r,'submitted_verified',AcceptanceEvidence(r.info_hash,True))),acceptance_only=True)
os._exit(77)
"""
    env=dict(__import__('os').environ,PYTHONPATH=str(scripts))
    child=subprocess.run([sys.executable,'-c',code,str(repo.path)],env=env,capture_output=True)
    assert child.returncode==77,child.stderr
    assert repo.find(track_id='t')['progress']['handled_episode']==0
    client=mock_client()
    result=Workflow(StateRepository(repo.path),client).recover('crash-op')
    assert result.status=='recovered'
    client.submit.assert_not_called(); client.preflight.assert_not_called()
