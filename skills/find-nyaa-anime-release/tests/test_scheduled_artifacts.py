"""Temporary repositories, captured review and fake clients only."""
import json

from evidence_artifacts import new_workspace, register, cleanup
from test_watch_v3 import make_repo, mock_client, fake_validator
from watch_v3.workflow import Workflow, Request
from watch_v3.evidence import QualityPolicy
from watch_v3.clients import ClientFailure


def run_evidence(repo):
    run = new_workspace(repo.path)
    listing = run/'listing.json'; listing.write_text('{}', encoding='utf8'); register(listing,repo.path)
    review = run/'review.json'
    review.write_text(json.dumps({'reviewed':True, 'track_id':'t', 'listing_reports':[str(listing)]}), encoding='utf8')
    register(review,repo.path)
    return run, review


def test_no_new_resource_closes_owned_run(tmp_path):
    repo = make_repo(tmp_path); run, review = run_evidence(repo)
    assert cleanup(repo, run=run)['deleted'] == 2
    assert not run.exists() and repo.find(track_id='t')['progress']['handled_episode'] == 0


def test_successful_delivery_automatically_removes_run(tmp_path):
    repo = make_repo(tmp_path); run, review = run_evidence(repo)
    client = mock_client()
    result = Workflow(repo,client,fake_validator()).deliver(Request('Demo',review,QualityPolicy()))
    assert result.status == 'delivery_recorded'
    assert not run.exists() and client.submit.call_count == 1
    show = repo.find(track_id='t')
    assert show['progress']['handled_episode'] == 13 and len(show['deliveries']) == 1


def test_failed_operation_protects_evidence_then_recovery_cleans(tmp_path):
    repo = make_repo(tmp_path); run, review = run_evidence(repo)
    client = mock_client(); client.submit.side_effect = ClientFailure('handoff_unverified')
    flow = Workflow(repo,client,fake_validator())
    result = flow.deliver(Request('Demo',review,QualityPolicy()))
    assert result.status == 'available_enqueue_failed'
    assert cleanup(repo,run=run)['deleted'] == 0 and review.exists()
    assert repo.find(track_id='t')['progress']['handled_episode'] == 0
    recovered = mock_client()
    done = Workflow(repo,recovered).recover(result.operation_id)
    assert done.status in {'delivery_recorded','recovered'}
    assert not run.exists() and repo.find(track_id='t')['progress']['handled_episode'] == 13


def test_accepted_commit_failure_protects_then_cleans_without_resubmit(tmp_path, monkeypatch):
    repo = make_repo(tmp_path); run, review = run_evidence(repo)
    original = repo.command
    def fail_commit(tid, kind, **fields):
        if kind == 'record_delivery' and not fields.get('acceptance_only'):
            raise OSError('injected commit failure')
        return original(tid, kind, **fields)
    monkeypatch.setattr(repo, 'command', fail_commit)
    result = Workflow(repo,mock_client(),fake_validator()).deliver(Request('Demo',review,QualityPolicy()))
    assert result.status == 'accepted_receipt_commit_failed'
    assert cleanup(repo,run=run)['deleted'] == 0 and review.exists()
    monkeypatch.setattr(repo, 'command', original)
    recovered = mock_client()
    assert Workflow(repo,recovered).recover(result.operation_id).status == 'recovered'
    recovered.submit.assert_not_called()
    assert not run.exists()

