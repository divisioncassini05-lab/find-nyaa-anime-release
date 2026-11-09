import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import dsh_panel_run as panel


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def state(tmp_path):
    path = tmp_path / 'state.json'
    write(path.with_suffix('.plans.json'), {'version': 1, 'plans': [dict(id='plan-1', trackId='track-1',
        title='Atlas Chronicle', season='S01', revision=1, mode='next_tracked', paused=False, bangumiSubjectId=123)]})
    return path


@pytest.mark.parametrize('old,expected', [(1, 3), (3, 3), (4, 3), (5, 3), (2, 2)])
def test_execution_marks_watching_except_watched(state, old, expected):
    class Client:
        kind = old
        writes = []
        def subject(self, subject):
            return {'id': subject, 'type': 2}
        def collection(self, username, subject):
            return {'type': self.kind}
        def set_collection(self, subject, kind):
            self.kind = kind
            self.writes.append(kind)
    client = Client()
    with patch('watch_v3.bangumi_client.load_config', return_value={'username': 'fake'}), patch('watch_v3.bangumi_client.configured_client', return_value=client):
        result = panel.start_watching(state, panel.load_plan(state, 'plan-1'))
    assert client.kind == expected
    assert result['startSync'] == 'synced'
    assert result['startedCollectionType'] == expected
    if old == 2:
        assert client.writes == []


def test_verified_found_records_without_delivery_and_rejects_wrong_track(state):
    report = dict(status='found', eligibility='passed', target_episode=5,
                  selected={'magnet': 'magnet:?xt=urn:btih:' + 'a' * 40, 'url': 'https://nyaa.si/view/1'})
    show = {'track_id': 'track-1', 'broadcast': {'completion': {'confirmed': True, 'final_episode': 5}}}
    with patch.object(panel, '_context', (state, 'plan-1')):
        panel.record_found(report, show=show)
        with pytest.raises(ValueError, match='panel_track_mismatch'):
            panel.record_found(report, show={**show, 'track_id': 'other'})
    result = panel.snapshot(state)['plan-1']
    assert result['latestFound']['episode'] == 5
    assert result['latestFound']['finalEpisode'] == 5
    assert result['completedDownloads'] == 0


def test_paused_deleted_and_failed_results_do_not_create_found_progress(state):
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0]['paused'] = True
    write(state.with_suffix('.plans.json'), plans)
    with pytest.raises(ValueError, match='paused_or_deleted'):
        panel.load_plan(state, 'plan-1')
    with patch.object(panel, '_context', (state, 'plan-1')):
        panel.record_found({'status': 'no_match'})
    assert not panel.result_path(state, 'plan-1').exists()


def bencode(value):
    if isinstance(value, int):
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, list):
        return b'l' + b''.join(bencode(v) for v in value) + b'e'
    return b'd' + b''.join(bencode(k) + bencode(v) for k, v in sorted(value.items())) + b'e'


def test_completion_requires_actual_files_and_completion_evidence_and_keeps_history(state, tmp_path):
    root = tmp_path / 'downloads'
    backup = tmp_path / 'backup'
    root.mkdir(); backup.mkdir()
    info = {b'name': b'Atlas-05.mkv', b'length': 4, b'piece length': 4, b'pieces': hashlib.sha1(b'test').digest()}
    info_hash = hashlib.sha1(bencode(info)).hexdigest()
    (backup / (info_hash + '.torrent')).write_bytes(bencode({b'info': info}))
    resume = backup / (info_hash + '.fastresume')
    # A preallocated full-size file must not appear in completed history.
    (root / 'Atlas-05.mkv').write_bytes(b'test')
    resume.write_bytes(bencode({b'completed_time': 0, b'info-hash': bytes.fromhex(info_hash)}))
    assert not panel.files_complete(info_hash, root, backup)
    resume.write_bytes(bencode({b'completed_time': 100, b'info-hash': bytes.fromhex(info_hash)}))
    assert panel.files_complete(info_hash, root, backup)
    write(state.with_suffix('.setup.json'), {'download_directory': str(root)})
    write(panel.result_path(state, 'plan-1'), {'version': 1, 'finds': [{'infoHash': info_hash, 'episode': 5, 'scope': 'regular'}], 'completed': []})
    with patch.object(panel, 'qb_backup_directory', return_value=backup):
        first = panel.snapshot(state)['plan-1']
        assert first['completedEpisodes'] == [5]
        assert first['completedDownloads'] == 1
        (root / 'Atlas-05.mkv').unlink()
        plans = panel.read(state.with_suffix('.plans.json'), {})
        plans['plans'][0].update(paused=True, collectionType=5)
        write(state.with_suffix('.plans.json'), plans)
        second = panel.snapshot(state)['plan-1']
        assert second['completedDownloads'] == 1
        assert second['completedEpisodes'] == [5]


def test_broadcast_latest_is_never_found_progress(state):
    write(state, {'shows': [{'track_id': 'track-1', 'progress': {'latest_release_episode': 99, 'target_episode': 100}}]})
    assert panel.snapshot(state)['plan-1']['latestFound'] is None


@pytest.mark.parametrize('status', ['pending', 'synced', 'binding_required'])
def test_multiple_commands_do_not_repeat_optional_bangumi_requests(state, status):
    plan = panel.load_plan(state, 'plan-1')
    with patch.object(panel, 'connection_revision', return_value='fake-config'), patch.object(panel, 'start_watching', return_value={'startSync': status}) as start:
        for _ in range(6):
            assert panel.ensure_watching(state, plan)['startSync'] == status
        assert start.call_count == 1
        panel.ensure_watching(state, {**plan, 'revision': 2})
        assert start.call_count == 2


def test_changed_credentials_binding_and_expired_retry_are_not_stuck(state):
    plan = panel.load_plan(state, 'plan-1')
    with patch.object(panel, 'connection_revision', return_value='config-a') as config, patch.object(panel, 'start_watching', return_value={'startSync':'pending'}) as start:
        panel.ensure_watching(state, plan)
        config.return_value = 'config-b'
        panel.ensure_watching(state, plan)
        assert start.call_count == 2
        panel.ensure_watching(state, plan, 456)
        assert start.call_count == 3
        panel.update_result(state, plan, {'startedAt':'2000-01-01T00:00:00+00:00'})
        panel.ensure_watching(state, plan, 456)
        assert start.call_count == 4


def test_snapshot_without_new_download_evidence_does_not_rewrite_files(state):
    with patch.object(panel, 'atomic_json') as save:
        panel.snapshot(state)
        panel.snapshot(state)
    save.assert_not_called()


def test_package_binding_is_recorded_without_regular_episode_progress(state):
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0].update(mode='season_batch', bangumiSubjectId=None)
    write(state.with_suffix('.plans.json'), plans)
    report = dict(status='found', eligibility='passed', info_hash='b' * 40, source_url='https://nyaa.si/view/123',
                  scope={'kind': 'season', 'title': 'Atlas Chronicle', 'season': 'S01', 'bangumi_id': 123})
    with patch.object(panel, '_context', (state, 'plan-1')), patch.object(panel, 'start_watching', return_value={'startSync': 'synced', 'bangumiSubjectId': 123}) as start:
        panel.record_found(report)
        assert start.call_args.args[-1] == 123
    result = panel.snapshot(state)['plan-1']
    assert result['foundPackage']
    assert result['latestFound'] is None
    assert result['latestPackage']['sourceUrl'] == 'https://nyaa.si/view/123'
    assert result['latestPackage']['scope'] == 'season'
    assert result['bangumiSubjectId'] == 123


@pytest.mark.parametrize('command', ['watched', 'flush', 'finalize'])
def test_panel_execution_rejects_automatic_write_and_cleanup(state, command):
    with patch.object(panel, 'start_watching') as cloud:
        with pytest.raises(ValueError, match='panel_manual_sync_required'):
            panel.main(['--state', str(state), '--plan-id', 'plan-1', 'watch', command])
        cloud.assert_not_called()


def test_web_completion_checks_exact_local_files(tmp_path):
    from watch_v3.clients import AcceptanceEvidence
    class Client:
        progress = 1
        def inspect(self, info_hash):
            return AcceptanceEvidence(info_hash, True, {'torrent': {'save_path': str(tmp_path), 'amount_left': 0, 'progress': self.progress}})
        def _request(self, route):
            return json.dumps([{'name': 'episode.mkv', 'size': 4, 'progress': self.progress}]).encode()
    client = Client()
    assert not panel.web_files_complete(client, 'a' * 40, tmp_path)
    (tmp_path / 'episode.mkv').write_bytes(b'test')
    assert panel.web_files_complete(client, 'a' * 40, tmp_path)
    client.progress = 0.5
    assert not panel.web_files_complete(client, 'a' * 40, tmp_path)
