"""Regression: details decide comparisons, and no supported add skips validation."""
import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import package_release as package
import qbittorrent_submit as qb
import search_nyaa_releases as nyaa
from anime_release import raw_evidence as raw, reviewed
from anime_release.models import WorkflowError
from nyaa_client import NyaaRelease, NyaaReleaseDetail, NyaaFileEntry
from quality_review import policy_from_args, inspection_key
from submission_gate import SubmissionPermit
from watch_v3.clients import (DeliveryRequest, DesktopLauncherClient, QbittorrentWebApiClient,
                              ClientFailure, AcceptanceEvidence, receipt)


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def fixture(tmp_path, *, count=2, size=1.4, tier='browse', kind='season', require_zh=False):
    cid='123'; info_hash='a'*40
    title='[Fixture] Example S01 Complete [1080p BluRay]'
    files=tuple(NyaaFileEntry(f'Example S01E{i:02d}.mkv', f'{size} GiB', int(size*1024**3)) for i in range(1,count+1))
    release=NyaaRelease(cid,title,'Anime',f'{size*count} GiB',int(size*count*1024**3),None,None,
                        10,0,0,f'https://nyaa.si/view/{cid}',info_hash)
    detail=NyaaReleaseDetail(release=release,description='Subtitles: Chinese, English\nVideo: original grain preserved.',files=files)
    client=Mock();client.get.return_value=detail
    saved=raw.details(cid,client=client)
    dp=tmp_path/'detail.json';lp=tmp_path/'listing.json';rp=tmp_path/'review.json'
    write(dp,saved)
    write(lp,dict(schema_version=1,kind='nyaa_listing',checked_at=raw.now(),rows=[saved['release']],
                  sort='id',order='desc',row_count=1,query='Example',page=1,later_pages=False))
    policy=policy_from_args(SimpleNamespace(tier=tier,require_zh=require_zh))
    review=dict(schema_version=1,kind='package_review',reviewed=True,candidate_id=cid,
        scope=dict(title='Example',kind=kind,episodes=count,season='S01',reviewed=True,
                   source_url='https://official.example/episodes',evidence_text=f'Complete {count} episodes'),
        quality_policy=policy,quality_comparison=dict(result='unknown',reason='No matched comparison in details.',
                   limitations='Metadata only.',alternatives=[]),detail_report=str(dp),listing_reports=[str(lp)],
        selection=dict(work_reason='This complete title matches Example.',work_quotes=['Example'],
                       subtitle_quotes=['Subtitles: Chinese, English'],excluded_videos=[],source_exception=None,
                       episodes=[dict(episode=i,files=[f.name],reason='Explicit episode label.',quotes=[f.name]) for i,f in enumerate(files,1)]))
    write(rp,review)
    return rp,review,policy,client


def fake_download():
    client=Mock()
    client.inspect.side_effect=lambda h:AcceptanceEvidence(h,False)
    client.submit.side_effect=lambda r:receipt(r,'submitted_verified',AcceptanceEvidence(r.info_hash,True))
    return client


@pytest.mark.parametrize('size',[1.0,1.2,1.5,1.9,2.0])
@pytest.mark.parametrize('label',['1080p AVC 8bit','1080p HEVC 10bit','2160p AV1 12bit BluRay Remux'])
def test_size_codec_labels_do_not_rank(size,label):
    release=NyaaRelease('1',f'[G] Example - 01 [{label}]','Anime',f'{size} GiB',int(size*1024**3),None,None,
                        10,0,0,'https://nyaa.si/view/1','a'*40)
    candidate=nyaa.score_release(release,query='Example',want_zh=False,airing_priority=False,desired_resolution=None,
                                 tier='browse',duration_min=24,episodes=None,prefer_groups=[],avoid_groups=[],include_magnets=False)
    assert candidate.score==0 and candidate.score_deprecated
    assert inspection_key(candidate)==(True,-10,True,1)


def test_practical_order_prefers_verified_chinese_then_seeds():
    from test_release_finder import candidate
    larger=candidate('[G] Example - 01','1.9 GiB',999)
    smaller=candidate('[G] Example - 01','1.2 GiB',0)
    smaller.detail_chinese_confirmed=True
    smaller.seeders=2;larger.seeders=100
    assert inspection_key(smaller)<inspection_key(larger)


@pytest.mark.parametrize('forged',[None,{'passed':True},SubmissionPermit()])
def test_raw_desktop_submit_refuses_before_context_or_launch(monkeypatch,forged):
    context=Mock();launch=Mock()
    monkeypatch.setattr(qb,'find_executable',context);monkeypatch.setattr(qb,'_launch',launch)
    with pytest.raises(qb.SubmissionError,match='validated_submission_required'):
        qb.submit_magnet('magnet:?xt=urn:btih:'+'a'*40,validation=forged)
    context.assert_not_called();launch.assert_not_called()


@pytest.mark.parametrize('client_type',[DesktopLauncherClient,QbittorrentWebApiClient])
def test_adapter_add_also_requires_capability(client_type):
    client=client_type();client.preflight=Mock()
    with pytest.raises(ClientFailure,match='validated_submission_required'):
        client.submit(DeliveryRequest('t','op','a'*40,'magnet:?xt=urn:btih:'+'a'*40))
    client.preflight.assert_not_called()


@pytest.mark.parametrize('tier',['browse','watch','premium'])
def test_actual_bad_11_episode_package_never_reaches_client(tmp_path,tier):
    path,review,policy,source=fixture(tmp_path,count=11,size=6.689/11,tier=tier)
    client=fake_download()
    with pytest.raises(WorkflowError,match='per_episode_below_absolute_floor'):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.submit.assert_not_called()
    assert not (tmp_path/'journal').exists()


@pytest.mark.parametrize('change,error',[
    (lambda r:r['selection']['episodes'].pop(),'incomplete_episode_coverage'),
    (lambda r:r['selection']['episodes'][1].update(episode=1),'incomplete_episode_coverage'),
    (lambda r:r['selection']['episodes'][1].update(files=r['selection']['episodes'][0]['files']),'duplicate_episode_file'),
    (lambda r:r['selection'].update(subtitle_quotes=[]),'subtitle_unqualified'),
    (lambda r:r.pop('quality_comparison'),'quality_comparison_required'),
    (lambda r:r['selection'].update(source_exception={'type':'remux','reason':'title','quotes':['BluRay']}),'source_exception_not_applicable'),
])
def test_invalid_package_is_rejected_without_add(tmp_path,change,error):
    path,review,policy,source=fixture(tmp_path,require_zh=True)
    change(review);write(path,review);client=fake_download()
    with pytest.raises(WorkflowError,match=error):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.submit.assert_not_called()


def test_policy_cannot_be_lowered_at_delivery(tmp_path):
    path,review,policy,source=fixture(tmp_path,tier='premium')
    with pytest.raises(WorkflowError,match='quality_policy_mismatch'):
        package.audit(path,{**policy,'tier':'browse'},client=source)


def test_title_only_remux_cannot_exempt_floor(tmp_path):
    path,review,policy,source=fixture(tmp_path,size=.6,tier='premium')
    review['selection']['source_exception']=dict(type='remux',reason='label',quotes=['BluRay'])
    write(path,review)
    with pytest.raises(WorkflowError,match='source_exception_unverified'):
        package.audit(path,policy,client=source)


def test_source_exception_requires_detail_evidence(tmp_path):
    path,review,policy,source=fixture(tmp_path,size=4,tier='premium')
    source.get.return_value=replace(source.get.return_value,description=source.get.return_value.description+'\nRemux: untouched video; no re-encoding.')
    raw.save(Path(review['detail_report']),raw.details('123',client=source))
    review['selection']['source_exception']=dict(type='remux',reason='Original video copied.',quotes=['Remux: untouched video; no re-encoding.'])
    write(path,review)
    _,report,_=package.audit(path,policy,client=source)
    assert report['coverage']['source_exception']['type']=='remux'


@pytest.mark.parametrize('change',['hash','files','description'])
def test_changed_detail_stops_before_submission(tmp_path,change):
    path,review,policy,source=fixture(tmp_path)
    d=source.get.return_value
    if change=='hash':d=replace(d,release=replace(d.release,info_hash='b'*40))
    elif change=='files':d=replace(d,files=d.files[:-1])
    else:d=replace(d,description='changed')
    source.get.return_value=d;client=fake_download()
    with pytest.raises(WorkflowError,match='candidate_details_changed'):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.submit.assert_not_called()


def test_validated_capability_cannot_submit_another_hash(tmp_path,monkeypatch):
    path,review,policy,source=fixture(tmp_path)
    token,report,_=package.audit(path,policy,client=source)
    launch=Mock();monkeypatch.setattr(qb,'_launch',launch)
    with pytest.raises(qb.SubmissionError,match='validated_submission_mismatch'):
        qb.submit_magnet('magnet:?xt=urn:btih:'+'b'*40,validation=token)
    launch.assert_not_called()


@pytest.mark.parametrize('kind,count,size',[('season',2,1.4),('movie',1,11)])
def test_qualified_package_idempotence_without_tracking(tmp_path,kind,count,size):
    path,review,policy,source=fixture(tmp_path,kind=kind,count=count,size=size)
    client=fake_download()
    first=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    again=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    assert first['status']=='delivery_recorded' and again['status']=='already_accepted'
    client.submit.assert_called_once()
    assert not (tmp_path/'state.json').exists()


def test_package_recovery_checks_original_policy_and_details(tmp_path):
    path,review,policy,source=fixture(tmp_path)
    client=fake_download();client.submit.side_effect=ClientFailure('client_busy',retryable=True)
    first=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    assert first['status']=='available_enqueue_failed'
    journal=tmp_path/'journal'/first['operation_id']/'operation.json'
    source.get.return_value=replace(source.get.return_value,description='changed')
    client.submit.reset_mock()
    with pytest.raises(WorkflowError,match='candidate_details_changed'):
        package.recover(journal,client,evidence_client=source)
    client.submit.assert_not_called()


def test_package_recovery_acceptance_finishes_without_revalidation(tmp_path):
    path,review,policy,source=fixture(tmp_path)
    client=fake_download();client.submit.side_effect=RuntimeError('crash after send')
    with pytest.raises(RuntimeError):package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    journal=next((tmp_path/'journal').glob('*/operation.json'))
    client.inspect.side_effect=lambda h:AcceptanceEvidence(h,True)
    source.get.side_effect=RuntimeError('offline');client.submit.reset_mock()
    assert package.recover(journal,client,evidence_client=source)['status']=='recovered'
    client.submit.assert_not_called()


def test_smaller_release_can_win_from_detail_evidence(tmp_path):
    path,review,policy,source=fixture(tmp_path,count=1,size=1.2)
    selected=source.get.return_value
    alternative=replace(selected,release=replace(selected.release,nyaa_id='124',url='https://nyaa.si/view/124',
                         size='1.9 GiB',size_bytes=int(1.9*1024**3)),description='Video: heavy denoising removed grain.')
    source.get.side_effect=lambda cid,**kw:selected if cid=='123' else alternative
    alt_path=tmp_path/'alternative.json';raw.save(alt_path,raw.details('124',client=source))
    review['quality_comparison']=dict(result='clear_advantage',reason='The smaller encode preserves grain while the alternative removes it.',
        selected_quotes=['original grain preserved'],limitations='Based on release descriptions, not a playback test.',
        alternatives=[dict(detail_report=str(alt_path),relation='better',reason='Selected retains source grain.',quotes=['heavy denoising removed grain'])])
    write(path,review)
    _,report,_=package.audit(path,policy,client=source)
    assert report['candidate_id']=='123' and report['quality_comparison']['result']=='clear_advantage'


@pytest.mark.parametrize('tier,sizes', [('browse',[0.8,1.8]), ('watch',[1.5,3.5]),
                                      ('premium',[5.5,7.5]), ('browse',[1.2,2.5])])
def test_package_average_cannot_mask_out_of_range_episode(tmp_path,tier,sizes):
    path,review,policy,source=fixture(tmp_path,tier=tier)
    detail=source.get.return_value
    source.get.return_value=replace(detail,files=tuple(replace(f,size_bytes=int(size*1024**3),size=f'{size} GiB')
                                                    for f,size in zip(detail.files,sizes)))
    raw.save(Path(review['detail_report']),raw.details('123',client=source))
    client=fake_download()
    with pytest.raises(WorkflowError,match='per_episode_below_absolute_floor|release_unqualified'):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.submit.assert_not_called();client.inspect.assert_not_called()


def test_movie_under_ten_gib_rejects_before_client(tmp_path):
    path,review,policy,source=fixture(tmp_path,kind='movie',count=1,size=9.9)
    client=fake_download()
    with pytest.raises(WorkflowError,match='release_unqualified'):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.submit.assert_not_called()


def test_package_retains_requested_path_on_retry(tmp_path):
    path,review,policy,source=fixture(tmp_path)
    client=fake_download();client.submit.side_effect=ClientFailure('client_busy',retryable=True)
    requested=tmp_path/'media'
    first=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source,save_path=requested)
    assert client.submit.call_args.args[0].save_path==str(requested)
    journal=tmp_path/'journal'/first['operation_id']/'operation.json'
    client.submit.side_effect=lambda r:receipt(r,'submitted_verified',AcceptanceEvidence(r.info_hash,True))
    result=package.recover(journal,client,evidence_client=source)
    assert result['status']=='delivery_recorded'
    assert client.submit.call_args.args[0].save_path==str(requested)


def test_package_refreshes_evidence_without_changing_operation(tmp_path):
    path,review,policy,source=fixture(tmp_path)
    client=fake_download();client.submit.side_effect=ClientFailure('client_busy',retryable=True)
    first=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    journal=tmp_path/'journal'/first['operation_id']/'operation.json'
    source.get.return_value=replace(source.get.return_value,description=source.get.return_value.description+'\nAdded release note.')
    raw.save(Path(review['detail_report']),raw.details('123',client=source))
    client.submit.side_effect=lambda r:receipt(r,'submitted_verified',AcceptanceEvidence(r.info_hash,True))
    result=package.recover(journal,client,evidence_client=source,review_path=path)
    assert result['status']=='delivery_recorded' and result['operation_id']==first['operation_id']
    assert len(list((tmp_path/'journal').glob('*/operation.json')))==1


@pytest.mark.parametrize('change', ['missing_policy','partial_policy','lower_policy','hash','unverified_receipt'])
def test_package_journal_cannot_bypass_validation(tmp_path,change):
    path,review,policy,source=fixture(tmp_path,tier='watch',size=2.5)
    client=fake_download();client.submit.side_effect=ClientFailure('client_busy',retryable=True)
    first=package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    journal=tmp_path/'journal'/first['operation_id']/'operation.json'
    op=json.loads(journal.read_text(encoding='utf-8'));kwargs={}
    if change=='missing_policy':op.pop('quality_policy')
    elif change=='partial_policy':op['quality_policy'].pop('require_zh')
    elif change=='lower_policy':kwargs=dict(review_path=path,original_policy={**policy,'tier':'browse'})
    elif change=='hash':op['request'].update(info_hash='b'*40,magnet='magnet:?xt=urn:btih:'+'b'*40)
    else:op['receipt']=dict(accepted=True,info_hash='a'*40,operation_id=first['operation_id'],
                           status='failed',track_id=op['request']['track_id'],evidence=dict(info_hash='a'*40,verified=False))
    write(journal,op);client.submit.reset_mock()
    with pytest.raises((WorkflowError,ClientFailure)):
        package.recover(journal,client,evidence_client=source,**kwargs)
    client.submit.assert_not_called()


@pytest.mark.parametrize('forged',[None, {'passed':True}])
def test_private_desktop_add_guard_is_not_only_in_wrapper(monkeypatch,forged):
    context=Mock();monkeypatch.setattr(qb,'find_executable',context)
    with pytest.raises(qb.SubmissionError,match='validated_submission_required'):
        qb._submit_magnet_locked('magnet:?xt=urn:btih:'+'a'*40,validation=forged)
    context.assert_not_called()


def test_pending_legacy_episode_requires_original_conditions(tmp_path):
    from test_watch_v3 import make_repo, prepared, mock_client, manifest, fake_validator
    from watch_v3.workflow import Workflow
    from quality_review import policy_from_args
    repo=make_repo(tmp_path);prepared(repo)
    client=mock_client();validator=fake_validator()
    flow=Workflow(repo,client,validator)
    assert flow.recover('op').status=='re_review_required'
    client.submit.assert_not_called();validator.validate.assert_not_called()
    refreshed=manifest(tmp_path)
    with pytest.raises(WorkflowError,match='original_quality_policy_required'):
        flow.recover('op',review=refreshed)
    client.submit.assert_not_called()
    explicit=policy_from_args(SimpleNamespace(tier='watch'))
    result=flow.recover('op',review=refreshed,original_policy=explicit)
    assert result.status=='delivery_recorded' and result.operation_id=='op'
    assert validator.validate.call_args.args[2].tier=='watch'
    client.submit.assert_called_once()
    assert flow.recover('op').status=='already_accepted'
    client.submit.assert_called_once()


def test_single_episode_recovery_runs_real_validator_again(tmp_path):
    from test_agent_reviewed_flow import prepared
    from watch_v3.store import StateRepository
    from watch_v3.evidence import ReviewValidator, QualityPolicy
    from watch_v3.workflow import Workflow, Request
    from test_watch_v3 import mock_client
    import hashlib
    source,args,review=prepared(tmp_path,intent='specific_episode')
    repo=StateRepository(args.state)
    repo.migrate(expected_sha256=hashlib.sha256(args.state.read_bytes()).hexdigest())
    client=mock_client();client.submit.side_effect=ClientFailure('client_busy',retryable=True)
    flow=Workflow(repo,client,ReviewValidator(source))
    first=flow.deliver(Request(args.title,args.review,QualityPolicy()))
    assert first.status=='available_enqueue_failed'
    client.submit.reset_mock()
    source.detail=replace(source.detail,description='The release description changed.')
    with pytest.raises(WorkflowError,match='candidate_details_changed'):
        flow.recover(first.operation_id)
    client.submit.assert_not_called()
    assert repo.find(track_id=review['track_id'])['progress']['handled_episode']==0


def test_direct_webapi_add_cannot_bypass_adapter():
    opener=Mock();client=QbittorrentWebApiClient(opener=opener)
    with pytest.raises(ClientFailure,match='validated_submission_required'):
        client._request('/api/v2/torrents/add',b'urls=magnet%3A%3Fxt%3Durn%3Abtih%3A' + b'a'*40)
    opener.open.assert_not_called()


def test_network_failure_during_validation_never_launches_client(tmp_path):
    from nyaa_client import NyaaClientError
    path,review,policy,source=fixture(tmp_path)
    source.get.side_effect=NyaaClientError('offline')
    client=fake_download()
    with pytest.raises(NyaaClientError):
        package.deliver(path,policy,tmp_path/'journal',client,evidence_client=source)
    client.preflight.assert_not_called();client.submit.assert_not_called()


@pytest.mark.parametrize('change',['missing_policy','changed_policy'])
def test_compatibility_journal_also_preserves_original_policy(tmp_path,change):
    from test_architecture_v2 import state_file,release_for,identity_for,request
    from anime_release.delivery import finalize
    path=state_file(tmp_path);release=release_for(identity_for(path))
    client=Mock(side_effect=RuntimeError('interrupted before acceptance'))
    with pytest.raises(RuntimeError):finalize(release,request(),path,client,client_options={})
    journal=next((tmp_path/'.delivery-journal').glob('*.json'))
    op=json.loads(journal.read_text(encoding='utf-8'))
    if change=='missing_policy':op.pop('quality_policy')
    else:op['quality_policy']['tier']='premium'
    write(journal,op);client.reset_mock()
    with pytest.raises(WorkflowError,match='re_review_required|quality_policy_mismatch'):
        finalize(release,request(),path,client,client_options={})
    client.assert_not_called()
