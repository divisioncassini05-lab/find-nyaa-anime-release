import json
from unittest.mock import patch

import pytest

import dsh_panel_run as panel
from dsh_panel_targets import worklist, allows_backfill
from test_panel_execution import state, write


def missing_plan(state):
    data = panel.read(state.with_suffix('.plans.json'), {})
    data['plans'][0].update(mode='missing_episodes', tier='browse', requireZh=False)
    write(state.with_suffix('.plans.json'), data)
    return data['plans'][0]


def entry(n):
    return {'infoHash': f'{n:040x}', 'scope': 'regular', 'episode': n,
            'reviewPath': 'review.json', 'qualityPolicy': {'tier': 'browse'}}


def test_new_follower_through_five_gets_all_five_without_cloud_or_state_writes(state, capsys):
    missing_plan(state)
    with patch.object(panel, 'ensure_watching') as cloud, patch.object(panel, 'atomic_json') as save:
        assert panel.main(['--state', str(state), '--plan-id', 'plan-1', 'targets', '--through', '5']) == 0
        result = json.loads(capsys.readouterr().out)
    assert result['missing_episodes'] == [1, 2, 3, 4, 5]
    cloud.assert_not_called()
    save.assert_not_called()


def test_partial_success_preserves_holes_and_retries_downloads_without_duplicates(state):
    plan = missing_plan(state)
    write(state, {'shows': [{'track_id': 'track-1', 'progress': {'handled_episode': 99, 'target_episode': 100},
                            'bangumi': {'watched_episodes': list(range(1, 100))}}]})
    panel.update_result(state, plan, {'finds': [entry(1), entry(3), entry(5)],
                                     'downloads': {entry(1)['infoHash']: {'status': 'download_submitted'}}})
    result = worklist(state, plan, 5)
    assert result['missing_episodes'] == [2, 4]
    assert [r['episode'] for r in result['pending_downloads']] == [3, 5]
    panel.update_result(state, plan, {'finds': [entry(n) for n in [1, 2, 3, 4, 5]]})
    assert worklist(state, plan, 5)['missing_episodes'] == []
    assert worklist(state, plan, 6)['missing_episodes'] == [6]


def test_failed_candidate_special_and_other_track_do_not_cover_gap(state):
    plan = missing_plan(state)
    panel.update_result(state, plan, {'finds': [dict(entry(2), scope='special')]})
    write(state, {'shows': [{'track_id': 'other', 'operations': {'x': {'episode': 1, 'kind': 'regular',
          'info_hash': 'a' * 40, 'review_manifest': {'reviewed': True}}}}]})
    with patch.object(panel, '_context', (state, plan['id'])):
        panel.record_found({'status': 'release_unqualified', 'target_episode': 1})
    assert worklist(state, plan, 2)['missing_episodes'] == [1, 2]


def test_snapshot_keeps_per_episode_download_controls(state):
    plan = missing_plan(state)
    panel.update_result(state, plan, {'finds': [entry(1), entry(3), entry(5)],
                                     'downloads': {entry(1)['infoHash']: {'status': 'download_submitted'}}})
    with patch.object(panel, 'files_complete', return_value=False):
        result = panel.snapshot(state)[plan['id']]
    assert result['recordedEpisodes'] == [1, 3, 5]
    assert [r['episode'] for r in result['resources']] == [1, 3, 5]
    assert result['resources'][0]['download']['status'] == 'download_submitted'
    assert all(r['canDownload'] for r in result['resources'])


def test_backfill_permission_is_scoped_and_respects_pause(state):
    plan = missing_plan(state)
    assert allows_backfill(state, plan['trackId'])
    assert not allows_backfill(state, 'another')
    plan['paused'] = True
    write(state.with_suffix('.plans.json'), {'version': 1, 'plans': [plan]})
    assert not allows_backfill(state, plan['trackId'])


def test_real_workflow_can_deliver_an_older_gap_after_finale_with_mock_client(state, tmp_path):
    from test_watch_v3 import make_repo, delivered, evidence, manifest, fake_validator, mock_client
    from watch_v3.workflow import Workflow, Request
    from watch_v3.evidence import QualityPolicy
    plan = missing_plan(state)
    plan['trackId'] = 't'
    write(state.with_suffix('.plans.json'), {'version': 1, 'plans': [plan]})
    repo = make_repo(tmp_path, total=5)
    delivered(repo, episode=5, info_hash='b' * 40)
    repo.attach_completion('t', evidence(final=5))
    review = manifest(tmp_path)
    write(review, {'reviewed': True, 'track_id': 't', 'intent': 'specific_episode', 'target_episode': 2})
    client = mock_client()
    result = Workflow(repo, client, fake_validator(episode=2)).deliver(Request(None, review, QualityPolicy()))
    assert result.status == 'delivery_recorded'
    assert client.submit.call_count == 1
    show = repo.find(track_id='t')
    assert show is not None
    assert show['progress']['handled_episode'] == 5
    assert {op['episode'] for op in show['operations'].values()} == {2, 5}


def test_completed_package_scheduled_retry_does_not_search_or_touch_bangumi(state, capsys):
    plan = panel.load_plan(state, 'plan-1')
    plan['mode'] = 'season_batch'
    write(state.with_suffix('.plans.json'), {'version': 1, 'plans': [plan]})
    panel.update_result(state, plan, {'finds': [dict(entry(1), scope='season', episode=None)]})
    with patch.object(panel, 'ensure_watching') as cloud, patch('package_release.main') as search:
        panel.main(['--state', str(state), '--plan-id', plan['id'], '--scheduled', 'package', 'review'])
    assert json.loads(capsys.readouterr().out)['status'] == 'package_already_found'
    cloud.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize('mode,intent', [('latest_regular', 'next_tracked'), ('missing_episodes', 'latest_regular')])
def test_wrong_single_episode_intent_is_rejected(state, mode, intent):
    plan = missing_plan(state)
    plan['mode'] = mode
    write(state.with_suffix('.plans.json'), {'version': 1, 'plans': [plan]})
    with patch.object(panel, 'ensure_watching'), patch('watch_v3.cli.run') as search:
        with pytest.raises(ValueError, match='scope_mismatch'):
            panel.main(['--state', str(state), '--plan-id', plan['id'], 'watch', 'review', '--intent', intent])
    search.assert_not_called()


@pytest.mark.parametrize('command', ['deliver', 'recover'])
def test_completed_package_can_finish_its_authorized_delivery(state, command):
    plan = panel.load_plan(state, 'plan-1')
    plan['mode'] = 'season_batch'
    write(state.with_suffix('.plans.json'), {'version': 1, 'plans': [plan]})
    panel.update_result(state, plan, {'finds': [dict(entry(1), scope='season', episode=None)]})
    with patch.object(panel, 'ensure_watching'), patch('package_release.main', return_value=0) as deliver:
        panel.main(['--state', str(state), '--plan-id', plan['id'], '--scheduled', 'package', command])
    deliver.assert_called_once_with([command])
