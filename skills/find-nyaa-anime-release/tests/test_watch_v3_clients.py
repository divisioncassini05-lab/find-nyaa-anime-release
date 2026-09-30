import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError
import pytest
from watch_v3.clients import *
from test_watch_v3 import HASH, make_repo, manifest, fake_validator, mock_client

class Response(io.BytesIO):
    pass

class Opener:
    def __init__(self,responses):
        self.responses=list(responses); self.calls=[]
    def open(self,request,timeout):
        self.calls.append(request)
        value=self.responses.pop(0)
        if isinstance(value,Exception): raise value
        return Response(value)

def request():
    return DeliveryRequest('t','op',HASH,'magnet:?xt=urn:btih:'+HASH)

def test_webapi_login_duplicate_exact_hash():
    opener=Opener([b'Ok.',b'v5.0.0',json.dumps([{'hash':HASH}]).encode()])
    c=QbittorrentWebApiClient(username='u',password='secret',opener=opener)
    r=c.submit(request())
    assert r.status=='already_present' and r.track_id=='t'
    assert not any('/torrents/add' in call.full_url for call in opener.calls)
    assert b'username=u&password=secret'==opener.calls[0].data

@pytest.mark.parametrize('found',[True,False])
def test_webapi_add_and_inspect(found):
    opener=Opener([b'v5.0',b'[]',b'Ok.',json.dumps([{'hash':HASH}] if found else []).encode()])
    r=QbittorrentWebApiClient(opener=opener).submit(request())
    assert r.status==('submitted_verified' if found else 'submitted')
    assert r.accepted
    assert sum('/torrents/add' in call.full_url for call in opener.calls)==1


def test_webapi_substring_hash_cannot_prove_acceptance():
    opener=Opener([json.dumps([{'hash':'b'*40,'name':HASH}]).encode()])
    ev=QbittorrentWebApiClient(opener=opener).inspect(HASH)
    assert not ev.verified

@pytest.mark.parametrize('body',[b'',b'Fails.',b'Ok',b'<html>Ok.</html>'])
def test_webapi_ambiguous_add_is_not_accepted(body):
    c=QbittorrentWebApiClient(opener=Opener([b'v5.0',b'[]',body]))
    with pytest.raises(ClientFailure) as error: c.submit(request())
    assert error.value.recovery.error_code=='client_rejected'
    assert error.value.recovery.same_hash_recovery_allowed

@pytest.mark.parametrize('status,code',[(403,'authentication_failed'),(503,'client_busy')])
def test_webapi_http_failure_has_recovery(status,code):
    error=HTTPError('http://localhost',status,'error',{},None)
    c=QbittorrentWebApiClient(opener=Opener([error]))
    with pytest.raises(ClientFailure) as exc: c.preflight()
    assert exc.value.recovery.error_code==code
    assert exc.value.recovery.next_action=='recover_same_operation'


def test_webapi_login_failed():
    c=QbittorrentWebApiClient(username='u',password='secret',opener=Opener([b'Fails.']))
    with pytest.raises(ClientFailure,match='authentication_failed'): c.preflight()


def test_add_success_inspection_failure_keeps_acceptance():
    c=QbittorrentWebApiClient(opener=Opener([b'v5.0',b'[]',b'Ok.',TimeoutError()]))
    r=c.submit(request())
    assert r.status=='submitted' and r.accepted


def test_desktop_preflight_checks_token(monkeypatch):
    import qbittorrent_submit as qb
    monkeypatch.setattr(qb,'find_executable',lambda path: path)
    def reject(*a): raise qb.SubmissionError('denied',code='client_context_required')
    monkeypatch.setattr(qb,'require_client_context',reject)
    fn=Mock()
    c=DesktopLauncherClient(submit_fn=fn)
    with pytest.raises(ClientFailure) as exc: c.submit(request())
    assert exc.value.recovery.requires_execution_tool_approval
    fn.assert_not_called()


def test_desktop_matches_port_contract(monkeypatch):
    import qbittorrent_submit as qb
    monkeypatch.setattr(qb,'find_executable',lambda path:path)
    monkeypatch.setattr(qb,'require_client_context',lambda *a:{'ok':True})
    c=DesktopLauncherClient(submit_fn=lambda *a,**k:{'status':'submitted_verified','ok':True,'info_hash':HASH})
    r=c.submit(request())
    assert r.validate(request()).status=='submitted_verified' and r.track_id=='t'


def test_hash_mismatch_fails_before_add():
    c=QbittorrentWebApiClient(opener=Opener([]))
    with pytest.raises(ClientFailure,match='magnet_hash_mismatch'):
        c.submit(DeliveryRequest('t','op',HASH,'magnet:?xt=urn:btih:'+'b'*40))
    assert not c.opener.calls


def test_v3_real_raw_review_delivery(tmp_path):
    from test_agent_reviewed_flow import prepared
    from watch_v3.store import StateRepository
    from watch_v3.evidence import ReviewValidator,QualityPolicy
    from watch_v3.workflow import Workflow,Request
    raw_client,args,review=prepared(tmp_path)
    repo=StateRepository(args.state); repo.migrate()
    client=mock_client()
    result=Workflow(repo,client,ReviewValidator(raw_client)).deliver(Request('飙马野郎',args.review,QualityPolicy(require_zh=True)))
    assert result.status=='delivery_recorded'
    assert repo.find(track_id=review['track_id'])['progress']['handled_episode']==2
    assert client.submit.call_count==1
    assert '2165948' in client.submit.call_args.args[0].source_url


def test_v3_real_review_changed_page_rejects_before_client(tmp_path):
    from test_agent_reviewed_flow import prepared
    from watch_v3.store import StateRepository
    from watch_v3.evidence import ReviewValidator,QualityPolicy
    from watch_v3.workflow import Workflow,Request
    raw_client,args,review=prepared(tmp_path)
    repo=StateRepository(args.state); repo.migrate(); before=repo.find(track_id=review['track_id'])['progress']
    raw_client.html=raw_client.html.replace('2166157','2169999')
    client=mock_client()
    with pytest.raises(Exception,match='discovery_changed'):
        Workflow(repo,client,ReviewValidator(raw_client)).deliver(Request('飙马野郎',args.review,QualityPolicy()))
    client.submit.assert_not_called()
    assert repo.find(track_id=review['track_id'])['progress']==before
