"""Optional library mirror and write recovery, using fake Bangumi/qBittorrent."""
import copy
import json
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from anime_release.storage import atomic_json, StateFileError
from watch_v3.bangumi_client import BangumiClient, BangumiError, connect, config_path, load_config
from watch_v3.bangumi import BangumiSync, episode_snapshot
from watch_v3.store import StateRepository
from watch_v3.outbox import drain
from watch_v3.workflow import Workflow, Request, commit_delivery
from watch_v3.evidence import QualityPolicy, validation_snapshot
from test_watch_v3 import make_repo, prepared, accepted, mock_client, fake_validator, manifest


class FakeBangumi:
    def __init__(self, total=4):
        self.account = 42
        self.kind = 3
        self.total = total
        self.watched = set()
        self.patch_calls = []
        self.collection_calls = []
        self.fail_write = False
        self.lose_response = False
        self.reads = 0

    def me(self):
        return {'id': self.account, 'username': 'reader'}

    def subject(self, sid):
        return {'id': sid, 'type': 2, 'name': 'Atlas Chronicle', 'name_cn': 'Atlas', 'eps': self.total}

    def collection(self, username, sid):
        self.reads += 1
        return {'type': self.kind, 'subject_id': sid, 'ep_status': len(self.watched)}

    def watching(self, username):
        return self.collections(username, 3)

    def collections(self, username, kind=None):
        self.reads += 1
        return [{'type': kind or 3, 'subject_type': 2, 'subject_id': 10, 'rate': 8,
                 'comment': 'Strong character writing', 'tags': ['drama'],
                 'subject': self.subject(10), 'ep_status': len(self.watched)}]

    def episodes(self, sid):
        self.reads += 1
        return [{'type': 2 if n in self.watched else 0,
                 'episode': {'id': 100 + n, 'sort': n, 'type': 0}} for n in range(1, self.total + 1)]

    def set_watched(self, sid, ids):
        self.patch_calls.append((sid, ids))
        if self.fail_write:
            raise BangumiError('bangumi_network_unavailable')
        self.watched.update(i - 100 for i in ids)
        if self.lose_response:
            self.lose_response = False
            raise BangumiError('bangumi_network_unavailable')

    def set_collection(self, sid, kind):
        self.collection_calls.append((sid, kind))
        self.kind = kind


def setup(tmp_path, monkeypatch, total=4):
    repo = make_repo(tmp_path, total)
    config = {'version': 1, 'account_id': 42, 'username': 'reader', 'token_env': 'TEST_BANGUMI_TOKEN'}
    atomic_json(config_path(repo.path), config)
    fake = FakeBangumi(total)
    monkeypatch.setattr('watch_v3.bangumi.configured_client', lambda _: fake)
    service = BangumiSync(repo, config, fake)
    service.bind('t', 10)
    return repo, fake, service


def test_token_file_is_not_copied_to_config(tmp_path):
    token = tmp_path / 'secret.txt'
    token.write_text('not-a-real-token', encoding='utf-8')
    fake = FakeBangumi()
    result = connect(tmp_path / 'state.json', token_file=token, factory=lambda _: fake)
    assert result['account_id'] == 42
    assert 'not-a-real-token' not in json.dumps(result)
    assert 'not-a-real-token' not in config_path(tmp_path / 'state.json').read_text()


def test_connect_does_not_silently_change_account(tmp_path, monkeypatch):
    repo, fake, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setenv('TEST_BANGUMI_TOKEN', 'test-secret')
    fake.account = 99
    with pytest.raises(BangumiError, match='account_conflict'):
        connect(repo.path, token_env='TEST_BANGUMI_TOKEN', factory=lambda _: fake)
    assert load_config(repo.path)['account_id'] == 42


def test_missing_token_reports_no_secret(tmp_path, monkeypatch):
    monkeypatch.delenv('TEST_BANGUMI_TOKEN', raising=False)
    with pytest.raises(BangumiError, match='token_required'):
        connect(tmp_path / 'state.json', token_env='TEST_BANGUMI_TOKEN')


@pytest.mark.parametrize('error,code', [
    (HTTPError('https://api.bgm.tv/v0/me', 401, 'secret-body', {}, None), 'bangumi_http_401'),
    (HTTPError('https://api.bgm.tv/v0/me', 429, 'secret-body', {}, None), 'bangumi_http_429'),
    (URLError('secret-proxy'), 'bangumi_network_unavailable'),
])
def test_transport_errors_do_not_echo_credentials(error, code):
    opener = Mock()
    opener.open.side_effect = error
    with pytest.raises(BangumiError) as caught:
        BangumiClient('secret-token', opener=opener).me()
    assert str(caught.value) == code


def test_http_methods_and_episode_ids_not_progress_counter():
    client = BangumiClient('fake')
    client.request = Mock()
    client.set_watched(10, [101, 102, 101])
    client.request.assert_called_once_with('PATCH', '/v0/users/-/collections/10/episodes', {'episode_id': [101, 102], 'type': 2})
    client.request.reset_mock()
    client.set_collection(10, 2)
    client.request.assert_called_once_with('POST', '/v0/users/-/collections/10', {'type': 2})


def test_list_pagination():
    client = BangumiClient('fake')
    client.request = Mock(side_effect=[{'total': 101, 'data': list(range(100))}, {'total': 101, 'data': [100]}])
    assert len(client.watching('reader')) == 101
    assert 'offset=100' in client.request.call_args.args[1]


def test_watching_cache_skips_network_and_has_no_full_catalog(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    result = service.watching()
    reads = fake.reads
    cached = service.watching()
    assert cached['cached'] and fake.reads == reads
    assert len(result['items']) == 1
    assert len(repo.read()['shows']) == 1
    assert 'episode_map' not in result['items'][0]


def test_episode_mapping_ignores_specials_and_decimal():
    rows = [{'type': 2, 'episode': {'id': 101, 'sort': 1, 'type': 0}},
            {'type': 2, 'episode': {'id': 102, 'sort': 1.5, 'type': 0}},
            {'type': 2, 'episode': {'id': 103, 'sort': 2, 'type': 1}}]
    assert episode_snapshot(rows) == ({'1': 101}, [1])


def test_absolute_numbering_requires_explicit_offset():
    rows = [{'type': 2, 'episode': {'id': 500, 'sort': 25, 'type': 0}}]
    with pytest.raises(BangumiError, match='numbering_confirmation'):
        episode_snapshot(rows)
    assert episode_snapshot(rows, 24) == ({'1': 500}, [1])


def test_wrong_provider_and_duplicate_bindings_rejected(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    with pytest.raises(BangumiError, match='identity_conflict'):
        service.bind('t', 20)
    repo.command('other', 'create_track', identity={'title': 'Other'})
    with pytest.raises(BangumiError, match='already_bound'):
        service.bind('other', 10)


def test_remote_progress_never_changes_local_target_or_validation(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    fake.watched = {1, 2, 4}
    result = service.refresh_track('t', refresh=True)
    show = repo.find(track_id='t')
    assert result['next_episode'] == 1
    assert result['watched_episodes'] == [1, 2, 4]
    assert show['progress']['handled_episode'] == 0
    assert show['deliveries'] == []
    assert validation_snapshot(show)['watched_episode'] == 0
    fake.watched = {1}
    service.refresh_track('t', refresh=True)
    assert repo.find(track_id='t')['progress']['target_episode'] == 1


@pytest.mark.parametrize('kind', [1, 2, 4, 5])
def test_remote_collection_status_never_stops_new_delivery(tmp_path, monkeypatch, kind):
    repo, fake, service = setup(tmp_path, monkeypatch)
    fake.kind = kind
    service.refresh_track('t', refresh=True)
    assert repo.find(track_id='t')['progress']['target_episode'] == 1
    client = mock_client()
    result = Workflow(repo, client, fake_validator(1)).deliver(Request('Demo', manifest(tmp_path), QualityPolicy()))
    assert result.status == 'delivery_recorded'
    client.submit.assert_called_once()
    assert fake.watched == {1}
    assert fake.kind == kind


def test_accepted_download_queues_once_and_writes_back(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    request = prepare_bound(repo, 1)
    commit_delivery(repo, 't', accepted(request))
    commit_delivery(repo, 't', accepted(request))
    writes = [a for a in repo.find(track_id='t')['outbox'] if a['kind'] == 'bangumi_watched']
    assert len(writes) == 1
    assert repo.find(track_id='t')['progress']['handled_episode'] == 1
    drain(repo, track_id='t', bangumi=service)
    assert fake.watched == {1}
    assert repo.find(track_id='t')['progress']['target_episode'] == 2
    assert len(fake.patch_calls) == 1


def prepare_bound(repo, episode=1):
    from dataclasses import asdict
    from watch_v3.clients import DeliveryRequest
    request = DeliveryRequest('t', 'op', 'a' * 40, 'magnet:?xt=urn:btih:' + 'a' * 40)
    repo.command('t', 'record_pending_operation', operation={
        'operation_id': 'op', 'track_id': 't', 'identity_revision': repo.find(track_id='t')['identity_revision'],
        'info_hash': 'a' * 40, 'episode': episode, 'kind': 'regular', 'request': asdict(request)})
    return request


def test_failed_submission_never_marks_watched(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    prepare_bound(repo)
    repo.command('t', 'record_failed_operation', operation_id='op', recovery={'error_code': 'failed'})
    drain(repo, track_id='t', bangumi=service)
    assert fake.patch_calls == []
    assert repo.find(track_id='t')['progress']['target_episode'] == 1


def test_offline_cloud_preserves_acceptance_and_retries_only_sync(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    req = prepare_bound(repo)
    commit_delivery(repo, 't', accepted(req))
    fake.fail_write = True
    first = drain(repo, track_id='t', bangumi=service)
    assert any(r['status'] == 'pending' for r in first)
    assert repo.find(track_id='t')['progress']['target_episode'] == 2
    assert len(repo.find(track_id='t')['deliveries']) == 1
    fake.fail_write = False
    drain(repo, track_id='t', bangumi=service)
    assert fake.watched == {1}
    assert all(a['status'] == 'done' for a in repo.find(track_id='t')['outbox'])


def test_lost_cloud_response_reads_back_without_duplicate_patch(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    req = prepare_bound(repo)
    commit_delivery(repo, 't', accepted(req))
    fake.lose_response = True
    drain(repo, track_id='t', bangumi=service)
    drain(repo, track_id='t', bangumi=service)
    assert len(fake.patch_calls) == 1
    assert repo.find(track_id='t')['bangumi']['watched_episodes'] == [1]


def test_explicit_episode_does_not_mark_unmentioned_episodes(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    result = service.watched('t', episode=3)
    assert result['status'] == 'bangumi_watched'
    assert fake.watched == {3}
    assert result['next_episode'] == 1
    assert repo.find(track_id='t')['deliveries'] == []


def test_through_and_complete_write_exact_regular_scope(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    assert service.watched('t', through=2)['next_episode'] == 1
    result = service.watched('t', complete=True)
    assert fake.watched == {1, 2, 3, 4}
    assert result['collection_type'] == 2 and result['next_episode'] == 1
    assert repo.find(track_id='t')['deliveries'] == []


def test_complete_with_missing_episode_metadata_refused(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    original = fake.episodes
    fake.episodes = lambda sid: original(sid)[:2]
    with pytest.raises(BangumiError, match='complete_scope_unconfirmed'):
        service.watched('t', complete=True)
    assert fake.patch_calls == []


def test_token_account_change_cannot_flush_another_users_outbox(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    req = prepare_bound(repo)
    commit_delivery(repo, 't', accepted(req))
    service.config = {**service.config, 'account_id': 99}
    results = drain(repo, track_id='t', bangumi=service)
    assert any(r.get('error') == 'bangumi_account_conflict' for r in results)
    assert fake.patch_calls == []


def test_reading_untracked_subject_never_creates_local_track(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    other = StateRepository(tmp_path / 'new-state.json')
    atomic_json(config_path(other.path), service.config)
    fake.watched = {1, 2}
    result = BangumiSync(other, service.config, fake).progress(10)
    assert result['watched_episodes'] == [1, 2]
    assert not other.path.exists()


def test_unconfigured_legacy_use_is_local_and_read_only(tmp_path):
    repo = make_repo(tmp_path)
    before = repo.path.read_bytes()
    from watch_v3.cli import run
    assert run(['--state', str(repo.path), 'inspect', 'Demo']) == 0
    assert repo.path.read_bytes() == before


def test_inspect_uses_no_account_network_even_when_connected(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    monkeypatch.setattr('watch_v3.bangumi.configured_client', Mock(side_effect=AssertionError('unexpected network')))
    from watch_v3.cli import run
    before = repo.path.read_bytes()
    assert run(['--state', str(repo.path), 'inspect', 'Demo']) == 0
    assert repo.path.read_bytes() == before


def test_offline_account_does_not_prevent_download(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    monkeypatch.setattr('watch_v3.bangumi.configured_client', Mock(side_effect=BangumiError('bangumi_network_unavailable')))
    client = mock_client()
    result = Workflow(repo, client, fake_validator(1)).deliver(Request('Demo', manifest(tmp_path), QualityPolicy()))
    assert result.status == 'delivery_recorded'
    client.submit.assert_called_once()
    show = repo.find(track_id='t')
    assert show['progress']['target_episode'] == 2
    assert any(a['kind'] == 'bangumi_watched' and a['status'] == 'pending' for a in show['outbox'])


def test_delivery_lazily_binds_verified_id_without_account_network(tmp_path):
    repo = make_repo(tmp_path, 4)
    show = repo.find(track_id='t')
    identity = {**show['identity'], 'provider_bindings': {'bangumi': {'entry_id': 10}}}
    repo.command('t', 'repair_identity', identity=identity, evidence={'reviewed': True})
    atomic_json(config_path(repo.path), {'version': 1, 'account_id': 42, 'username': 'reader'})
    req = prepare_bound(repo)
    commit_delivery(repo, 't', accepted(req))
    show = repo.find(track_id='t')
    assert show['bangumi']['subject_id'] == 10
    assert show['bangumi']['collection_type'] is None
    assert show['progress']['target_episode'] == 2
    fake = FakeBangumi()
    drain(repo, track_id='t', bangumi=BangumiSync(repo, client=fake))
    assert fake.watched == {1}


@pytest.mark.parametrize('broken_config', [True, False])
def test_optional_setup_errors_do_not_reject_accepted_delivery(tmp_path, broken_config):
    repo = make_repo(tmp_path, 4)
    config = {'version': 999} if broken_config else {'version': 1, 'account_id': 42, 'username': 'reader'}
    atomic_json(config_path(repo.path), config)
    req = prepare_bound(repo)
    commit_delivery(repo, 't', accepted(req))
    show = repo.find(track_id='t')
    assert show['progress']['target_episode'] == 2
    assert len(show['deliveries']) == 1
    assert show['extra']['bangumi_sync_warning'] in {'invalid_bangumi_config', 'bangumi_binding_required'}


def test_library_filters_preserve_personal_ratings_reviews_and_pagination(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    rows = fake.collections('reader', 2)
    fake.collections = Mock(return_value=[{**rows[0], 'subject_id': i} for i in range(1, 61)])
    before = repo.path.read_bytes()
    result = service.collections(collection='completed', query='character', min_rating=8, comments_only=True, limit=5)
    assert result['matched_count'] == 60 and len(result['items']) == 5 and result['next_offset'] == 5
    assert result['items'][0]['rating'] == 8 and result['items'][0]['comment'] == 'Strong character writing'
    assert result['items'][0]['tags'] == ['drama']
    fake.collections.assert_called_once_with('reader', 2)
    cached = service.collections(collection='completed', offset=5, limit=5)
    assert cached['cached'] and cached['items'][0]['subject_id'] == 6
    assert service.collections(collection='completed', min_rating=9)['items'] == []
    assert repo.path.read_bytes() == before


def test_untracked_explicit_watched_does_not_create_history_or_edit_reviews(tmp_path, monkeypatch):
    repo, fake, service = setup(tmp_path, monkeypatch)
    other = StateRepository(tmp_path / 'old-work.json')
    result = BangumiSync(other, service.config, fake).watched_subject(10, complete=True)
    assert result['collection_type'] == 2 and fake.watched == {1, 2, 3, 4}
    assert fake.collection_calls == [(10, 2)]
    assert not other.path.exists()
