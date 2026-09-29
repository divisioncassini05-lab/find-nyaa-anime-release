"""State/identity invariants across actual JSON, processes and interrupted delivery."""
import copy
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import pytest

from anime_release.models import WorkIdentity, ReleaseRequest, TargetDecision, VerifiedRelease, StateCommand, WorkflowError
from anime_release.repository import StateRepository, require_record, handled
from anime_release.schema import adapt, encode
from anime_release.storage import atomic_json
from anime_release.delivery import finalize
from anime_release.evidence import from_raw, validate, unique_repair
from anime_release import evidence_cache
from migrate_tracking_state import migrate
from tracked_identity import tracked_matches

def state_file(tmp_path, rows=None):
    path = tmp_path/'state.json'
    rows = rows or [dict(title='Example Anime Season 4', aliases=['Example', 're0'], season='S04',
        watched_episode=17, latest_known_episode=17, next_episode=18, airing=True, status='airing',
        anilist_id=21355, format='TV')]
    atomic_json(path, {'version': 1, 'shows': rows})
    return path

def identity_for(path, index=0):
    show = StateRepository(path).read()['shows'][index]
    return WorkIdentity(show['track_id'], show['title'], show['season'], revision=show['identity_revision'],
                        aliases=tuple(show['aliases']), format=show['format'])

def release_for(identity, episode=18, kind='regular'):
    target = TargetDecision(identity, 'latest_regular', episode, 'nyaa_candidates', True)
    info_hash = f'{episode:040x}'
    return VerifiedRelease(identity, target, str(episode), f'Example S04E{episode}',
        'magnet:?xt=urn:btih:'+info_hash, info_hash, f'https://nyaa.si/view/{episode}', kind, '{}')

def request(read_only=False):
    return ReleaseRequest('Example', season='S04', intent='latest_regular', enqueue=True, read_only=read_only)

def test_request_intent_matches_retrieval_contract():
    from anime_release.cli import build_parser
    from anime_release.requests import from_args
    from release_search_core import SearchIntent
    request = from_args(build_parser().parse_args(['re0', '--no-state-update']))
    assert request.intent == SearchIntent.NEXT_TRACKED.value

def accepted(*args, **kwargs):
    return {'status': 'submitted_verified', 'ok': True}

def test_identity_immutable_and_request_explicit_priority(tmp_path):
    path = state_file(tmp_path)
    identity = identity_for(path)
    with pytest.raises(FrozenInstanceError):
        identity.season = 'S01'
    raw = json.loads(path.read_text())
    raw['shows'].append(dict(raw['shows'][0], title='Example Anime', season='S01', airing=False, status='completed'))
    state = adapt(raw)
    assert tracked_matches(state, 're0')[0]['season'] == 'S04'
    assert tracked_matches(state, 're0', 'S01')[0]['season'] == 'S01'
    raw['shows'][1].update(airing=True, status='airing')
    assert len(tracked_matches(adapt(raw), 're0')) == 2

def test_migration_preserves_identical_rows_and_shared_ids(tmp_path):
    row = dict(title='Same', aliases=['shared'], season='S01', watched_episode=12,
               latest_known_episode=12, next_episode=None, status='completed', airing=False, anilist_id=99)
    path = state_file(tmp_path, [row, copy.deepcopy(row), dict(row, season='S04', watched_episode=17, next_episode=18)])
    before = path.read_bytes()
    preview = migrate(path)
    assert path.read_bytes() == before and not path.with_suffix('.json.lock').exists()
    assert len(set(preview['track_ids'])) == 3 and preview['progress_preserved']
    applied = migrate(path, True, preview['sha256'])
    assert Path(applied['backup']).read_bytes() == before
    disk = json.loads(path.read_text())
    assert disk['version'] == 2 and len(disk['shows']) == 3
    assert all('identity' in row and 'progress' in row and 'bindings' in row for row in disk['shows'])
    assert all(row['bindings']['anilist']['status'] == 'pending_verification' for row in disk['shows'])

def test_migration_preview_invalidated_by_concurrent_change(tmp_path):
    path = state_file(tmp_path)
    preview = migrate(path)
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='changed'):
        migrate(path, True, preview['sha256'])

def test_external_binding_repair_does_not_merge_records(tmp_path):
    path = state_file(tmp_path)
    repo = StateRepository(path)
    first = repo.read()['shows'][0]
    other = {**first, 'track_id': 'second-track', 'season': 'S01'}
    repo.commit(StateCommand('second-track', 'create', fields=other))
    from dataclasses import asdict
    identity = identity_for(path)
    evidence = [asdict(from_raw('anilist', {'id':189046,'title':{'english':identity.title},'format':'TV'})),
                asdict(from_raw('bangumi', {'id':444,'name':identity.title,'platform':'TV','type':2}))]
    result = repo.commit(StateCommand(first['track_id'], 'metadata_repair', expected_revision=0,
        expected_identity_revision=0, fields={'binding_evidence': {'anilist':
            {'entry_id': 189046, 'status':'verified', 'evidence': evidence}}}))
    assert len(result['shows']) == 2
    assert result['shows'][0]['anilist_id'] == 189046
    assert result['shows'][1]['anilist_id'] == 21355
    assert [s['watched_episode'] for s in result['shows']] == [17,17]

def test_wrong_cached_source_cannot_change_locked_season(tmp_path):
    path = state_file(tmp_path)
    identity = identity_for(path)
    wrong = from_raw('anilist', {'id':21355, 'title':{'english':'Example Anime'}, 'format':'TV', 'status':'RELEASING'})
    evidence_cache.write(tmp_path/'cache', identity, wrong)
    evidence = evidence_cache.read(tmp_path/'cache', identity, 'anilist', 21355)
    with pytest.raises(WorkflowError, match='identity_conflict'):
        validate(identity, evidence)
    assert evidence_cache.read(tmp_path/'cache', replace(identity, revision=1), 'anilist', 21355) is None
    assert identity.season == 'S04'

def test_cache_projection_cannot_contradict_raw_payload(tmp_path):
    identity = identity_for(state_file(tmp_path))
    wrong = from_raw('anilist', {'id':21355, 'title':{'english':'Example Anime'}, 'format':'TV'})
    forged_projection = replace(wrong, titles=(identity.title,), season='S04')
    with pytest.raises(WorkflowError, match='identity_conflict') as error:
        validate(identity, forged_projection)
    assert 'source_payload_mismatch' in error.value.evidence[0]['reasons']

@pytest.mark.parametrize('kind,count,code', [('permission',1,'permission_denied'),('timeout',2,'timeout'),
    ('certificate',1,'tls_certificate_verification_failed')])
def test_metadata_transport_has_typed_bounded_errors(monkeypatch,kind,count,code):
    import ssl
    import urllib.request
    from anime_release.transport import request_json, MetadataTransportError
    failures={'permission':PermissionError('blocked'), 'timeout':TimeoutError('timed out'),
        'certificate':ssl.SSLCertVerificationError('certificate verify failed')}
    attempts=[]
    def fail(*a, **k):
        attempts.append(1)
        raise failures[kind]
    monkeypatch.setattr(urllib.request,'urlopen',fail)
    with pytest.raises(MetadataTransportError) as error:
        request_json(urllib.request.Request('https://graphql.anilist.co'),10)
    assert error.value.detail.stage == 'metadata' and error.value.detail.code == code
    assert len(attempts)==count

def test_repair_requires_unique_independent_source_identity(tmp_path):
    identity = identity_for(state_file(tmp_path))
    a = from_raw('anilist', {'id':189046,'title':{'english':identity.title},'format':'TV'})
    b = from_raw('bangumi', {'id':444,'name':identity.title,'platform':'TV','type':2})
    with pytest.raises(WorkflowError, match='binding_repair_ambiguous'):
        unique_repair(identity, [a,a])
    assert unique_repair(identity, [a,b])['anilist']['entry_id'] == 189046
    c = from_raw('anilist', {'id':555,'title':{'english':identity.title},'format':'TV'})
    with pytest.raises(WorkflowError, match='binding_repair_ambiguous'):
        unique_repair(identity, [a,b,c])

def test_readonly_no_locks_journal_progress_or_client(tmp_path):
    path = state_file(tmp_path)
    before = path.read_bytes()
    result, receipt = finalize(release_for(identity_for(path)), request(True), path,
        lambda *a, **k: pytest.fail('readonly submitted'), client_options={})
    assert result['reason'] == 'read_only' and receipt is None
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]

@pytest.mark.parametrize('kind', ['collection','movie'])
def test_non_regular_delivery_does_not_advance(tmp_path, kind):
    path = state_file(tmp_path)
    finalize(release_for(identity_for(path), kind=kind), request(), path, accepted, client_options={})
    assert handled(StateRepository(path).read()['shows'][0]) == 17

def test_crash_before_acceptance_preserves_progress_and_intent(tmp_path):
    path = state_file(tmp_path)
    before = path.read_bytes()
    release = release_for(identity_for(path))
    def crash(*_, **__):
        raise RuntimeError('process terminated before acceptance')
    with pytest.raises(RuntimeError):
        finalize(release, request(), path, crash, client_options={})
    assert path.read_bytes() == before
    journal = next((tmp_path/'.delivery-journal').glob('*.json'))
    assert json.loads(journal.read_text())['status'] == 'prepared'
    finalize(release, request(), path, accepted, client_options={})
    assert handled(StateRepository(path).read()['shows'][0]) == 18

def test_acceptance_then_state_failure_recovers_exact_hash(tmp_path, monkeypatch):
    import anime_release.repository as repository
    path = state_file(tmp_path)
    release = release_for(identity_for(path))
    real_write = repository.atomic_json
    with monkeypatch.context() as patch:
        patch.setattr(repository, 'atomic_json', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(WorkflowError, match='accepted_state_commit_failed'):
            finalize(release, request(), path, accepted, client_options={})
    assert handled(StateRepository(path).read()['shows'][0]) == 17
    journal = next((tmp_path/'.delivery-journal').glob('*.json'))
    assert json.loads(journal.read_text())['status'] == 'accepted'
    seen=[]
    def check_existing(magnet, **kwargs):
        seen.append(magnet)
        return {'ok':True,'status':'already_present'}
    finalize(release, request(), path, check_existing, client_options={})
    assert seen == [release.magnet]
    assert handled(StateRepository(path).read()['shows'][0]) == 18

def test_stale_identity_prevents_client_call(tmp_path):
    path = state_file(tmp_path)
    release = release_for(identity_for(path))
    StateRepository(path).commit(StateCommand(release.identity.track_id,'manual',expected_revision=0,fields={'season':'S01'}))
    with pytest.raises(WorkflowError, match='identity_revision_conflict'):
        finalize(release, request(), path, lambda *a,**k: pytest.fail('stale submission'), client_options={})

def test_receipt_write_failure_preserves_acceptance_and_recovers(tmp_path, monkeypatch):
    import anime_release.delivery as delivery
    path = state_file(tmp_path)
    release = release_for(identity_for(path))
    original = delivery.atomic_json
    def fail_receipt(path, data):
        if data.get('status') == 'accepted':
            raise OSError('disk full after acceptance')
        original(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(delivery, 'atomic_json', fail_receipt)
        with pytest.raises(WorkflowError, match='accepted_receipt_commit_failed') as error:
            finalize(release, request(), path, accepted, client_options={})
        assert error.value.evidence[0]['accepted'] is True
    assert handled(StateRepository(path).read()['shows'][0]) == 17
    finalize(release, request(), path,
        lambda *a, **k: {'ok': True, 'status': 'already_present'}, client_options={})
    assert handled(StateRepository(path).read()['shows'][0]) == 18

def test_finalizer_rejects_target_from_another_identity(tmp_path):
    path = state_file(tmp_path)
    release = release_for(identity_for(path))
    invalid = replace(release, target=replace(release.target, identity=replace(release.identity, season='S01')))
    with pytest.raises(WorkflowError, match='verified_candidate_conflict'):
        finalize(invalid, request(), path, lambda *a, **k: pytest.fail('conflicting target submitted'), client_options={})

def test_same_hash_cannot_recover_as_another_episode(tmp_path):
    path = state_file(tmp_path)
    release = release_for(identity_for(path))
    def crash(*a, **k):
        raise RuntimeError('crash')
    with pytest.raises(RuntimeError):
        finalize(release, request(), path, crash, client_options={})
    changed = replace(release, target=replace(release.target, episode=19))
    with pytest.raises(WorkflowError, match='journal_target_conflict'):
        finalize(changed, request(), path, lambda *a, **k: pytest.fail('conflicting recovery'), client_options={})

def process_delivery(params):
    path, index, episode = params
    identity = identity_for(Path(path), index)
    finalize(release_for(identity,episode), request(), path, accepted, client_options={})
    return episode

def test_two_processes_same_show_monotonic_and_other_show_preserved(tmp_path):
    path = state_file(tmp_path)
    row = StateRepository(path).read()['shows'][0]
    StateRepository(path).commit(StateCommand('other','create',fields=dict(row, title='Other Show', aliases=['re0'])))
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(process_delivery, [(str(path),0,19),(str(path),0,18)]))
    state = StateRepository(path).read()
    assert handled(state['shows'][0]) == 19 and handled(state['shows'][1]) == 17
    with ProcessPoolExecutor(max_workers=2) as pool:
        list(pool.map(process_delivery, [(str(path),0,20),(str(path),1,21)]))
    assert [handled(s) for s in StateRepository(path).read()['shows']] == [20,21]

def test_completed_cannot_be_reopened_by_waiting(tmp_path):
    path = state_file(tmp_path)
    identity = identity_for(path)
    repo = StateRepository(path)
    repo.commit(StateCommand(identity.track_id,'completed',expected_identity_revision=0,
        fields={'completion': {'confirmed':True,'final_episode':17}}))
    repo.commit(StateCommand(identity.track_id,'waiting',fields={'notes':'old run'}))
    show = repo.read()['shows'][0]
    assert show['status'] == 'completed' and show['next_episode'] is None and handled(show) == 17
