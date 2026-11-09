"""Inbox actions reuse reviewed evidence; all accounts/clients are synthetic."""
import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import dsh_panel_run as panel
from dsh_panel_download import submit
from test_panel_execution import write, state
from test_quality_delivery_gate import fixture, fake_download


@pytest.fixture(autouse=True)
def no_network():
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('No live connections')):
        yield


def reviewed_package(state, tmp_path):
    import package_release as packages
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0].update(title='Example', mode='season_batch', tier='browse', bangumiSubjectId=None)
    write(state.with_suffix('.plans.json'), plans)
    path, review, policy, source = fixture(tmp_path)
    with patch.object(panel, '_context', (state, 'plan-1')):
        packages.audit(path, policy, client=source)
    return path, review, policy, source


def test_package_download_reuses_durable_review_without_discovery_or_cloud(state, tmp_path):
    path, review, policy, source = reviewed_package(state, tmp_path)
    # Temporary evidence may be gone by the next inbox visit.
    path.unlink()
    Path(review['detail_report']).unlink()
    Path(review['listing_reports'][0]).unlink()
    client = fake_download()
    with patch.object(panel, 'ensure_watching', side_effect=AssertionError('No cloud writes')):
        assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'download_submitted'
        assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'download_submitted'
    assert client.submit.call_count == 1
    entry = panel.snapshot(state)['plan-1']
    assert entry['latestPackage']['canDownload']
    assert 'reviewPath' not in entry['latestPackage']
    assert 'qualityPolicy' not in entry['latestPackage']
    assert entry['download']['status'] == 'download_submitted'
    assert entry['completedDownloads'] == 0


def test_retry_failed_package_submission_keeps_exact_hash(state, tmp_path):
    from watch_v3.clients import ClientFailure, receipt, AcceptanceEvidence
    _, _, _, source = reviewed_package(state, tmp_path)
    client = fake_download()
    client.submit.side_effect = ClientFailure('handoff_unverified', retryable=True)
    assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'download_pending'
    assert panel.snapshot(state)['plan-1']['completedDownloads'] == 0
    client.submit.side_effect = lambda r: receipt(r, 'submitted_verified', AcceptanceEvidence(r.info_hash, True))
    assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'download_submitted'
    assert {c.args[0].info_hash for c in client.submit.call_args_list} == {'a' * 40}
    assert client.submit.call_args_list[0].args[0].operation_id == client.submit.call_args_list[1].args[0].operation_id


def test_stale_requirements_missing_evidence_and_unselected_hash_never_submit(state, tmp_path):
    _, _, _, source = reviewed_package(state, tmp_path)
    client = fake_download()
    assert submit(state, 'plan-1', 'b' * 40, client=client, evidence_client=source)['status'] == 'resource_review_required'
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0]['requireZh'] = True
    write(state.with_suffix('.plans.json'), plans)
    assert not panel.snapshot(state)['plan-1']['latestPackage']['canDownload']
    assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'resource_review_required'
    plans['plans'][0]['requireZh'] = False
    write(state.with_suffix('.plans.json'), plans)
    saved = panel.read(panel.result_path(state, 'plan-1'), {})
    Path(saved['finds'][0]['reviewPath']).unlink()
    assert submit(state, 'plan-1', 'a' * 40, client=client, evidence_client=source)['status'] == 'resource_review_required'
    client.submit.assert_not_called()


def test_auto_off_rejects_scheduled_commands_but_allows_manual_run(state):
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0]['schedulePaused'] = True
    write(state.with_suffix('.plans.json'), plans)
    previous_context = panel._context
    with patch.object(panel, 'ensure_watching') as watching, patch('watch_v3.cli.run', return_value=0) as run:
        with pytest.raises(ValueError, match='automatic_run_disabled'):
            panel.main(['--state', str(state), '--plan-id', 'plan-1', '--scheduled', 'watch', 'get'])
        watching.assert_not_called()
        run.assert_not_called()
        panel.main(['--state', str(state), '--plan-id', 'plan-1', 'watch', 'get'])
        assert run.call_count == watching.call_count == 1
        assert panel._context is previous_context
        run.side_effect = ValueError('simulated failure')
        with pytest.raises(ValueError, match='simulated failure'):
            panel.main(['--state', str(state), '--plan-id', 'plan-1', 'watch', 'get'])
        assert panel._context is previous_context


def test_automatic_package_receipt_is_submitted_not_completed(state, tmp_path):
    reviewed_package(state, tmp_path)
    def delivered(_):
        print(json.dumps({'status': 'delivery_recorded', 'receipt': {'accepted': True, 'info_hash': 'a' * 40}}))
        return 0
    with patch.object(panel, 'ensure_watching'), patch('package_release.main', side_effect=delivered):
        panel.main(['--state', str(state), '--plan-id', 'plan-1', 'package', 'deliver'])
    result = panel.snapshot(state)['plan-1']
    assert result['download']['status'] == 'download_submitted'
    assert not result['completedPackage']


def test_regular_retry_uses_original_operation_and_not_search(state, tmp_path):
    from test_watch_v3 import make_repo, manifest, fake_validator, mock_client
    from watch_v3.clients import ClientFailure
    repo = make_repo(tmp_path)
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0]['trackId'] = 't'
    write(state.with_suffix('.plans.json'), plans)
    folder = panel.result_path(state, 'plan-1').parent
    folder.mkdir(parents=True, exist_ok=True)
    review_path = manifest(folder)
    panel.update_result(state, plans['plans'][0], {'finds': [{'infoHash': 'a' * 40, 'scope': 'regular',
        'episode': 2, 'reviewPath': str(review_path), 'qualityPolicy': {'tier': 'browse'}}], 'completed': []})
    client = mock_client()
    client.submit.side_effect = ClientFailure('handoff_unverified', retryable=True)
    validator = fake_validator(episode=2)
    assert submit(state, 'plan-1', 'a' * 40, client=client, validator=validator)['status'] == 'download_pending'
    from watch_v3.clients import receipt, AcceptanceEvidence
    client.submit.side_effect = lambda r: receipt(r, 'submitted_verified', AcceptanceEvidence(r.info_hash, True))
    assert submit(state, 'plan-1', 'a' * 40, client=client, validator=validator)['status'] == 'download_submitted'
    assert len(repo.find(track_id='t')['operations']) == 1
    assert {c.args[0].info_hash for c in client.submit.call_args_list} == {'a' * 40}


def test_inbox_download_progress_requires_actual_completed_files(state, tmp_path):
    from unittest.mock import Mock
    from watch_v3.clients import AcceptanceEvidence
    root = tmp_path / 'downloads'
    root.mkdir()
    write(state.with_suffix('.setup.json'), {'client': 'webapi', 'web_url': 'http://fake.invalid', 'download_directory': str(root)})
    panel.update_result(state, panel.load_plan(state, 'plan-1'), {'finds': [{'infoHash': 'a' * 40, 'episode': 2, 'scope': 'regular'}], 'completed': []})
    client = Mock()
    torrent = {'progress': .43, 'amount_left': 2, 'save_path': str(root), 'state': 'downloading'}
    client.inspect.side_effect = lambda h: AcceptanceEvidence(h, True, {'torrent': torrent})
    client._request.return_value = json.dumps([{'name': 'episode.mkv', 'size': 4, 'progress': 1}])
    with patch('watch_v3.clients.QbittorrentWebApiClient', return_value=client), patch.object(panel, 'files_complete', return_value=False):
        first = panel.snapshot(state)['plan-1']
        assert first['download']['progress'] == .43
        assert first['completedDownloads'] == 0
        torrent.update(progress=1, amount_left=0)
        assert panel.snapshot(state)['plan-1']['completedDownloads'] == 0
        (root / 'episode.mkv').write_bytes(b'test')
        complete = panel.snapshot(state)['plan-1']
        assert complete['download'] == {'status': 'completed', 'progress': 1}
        assert complete['completedEpisodes'] == [2]
        assert client.inspect.call_count == 3
