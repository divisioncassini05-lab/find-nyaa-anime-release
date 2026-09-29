"""Replay real pages: preserve recall, then exercise objective delivery boundaries."""
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from anime_release import raw_evidence as raw
from anime_release import reviewed
from anime_release.cli import build_parser
from anime_release.models import WorkflowError
from anime_release.repository import StateRepository
from nyaa_client import parse_detail
from state_io import save_state
import airing_watch_state as watch

FIXTURES = Path(__file__).parent / 'fixtures' / 'raw_review'


class Replay:
    def __init__(self):
        self.html = (FIXTURES / 'jojo-listing.html').read_text(encoding='utf-8')
        self.detail = parse_detail('2165948', (FIXTURES / 'jojo-detail.html').read_text(encoding='utf-8'))
        self.calls = []

    def fetch_listing(self, *args, **kwargs):
        self.calls.append(('listing', args, kwargs))
        return self.html

    def get(self, cid, **kwargs):
        assert cid == '2165948'
        self.calls.append(('detail', cid, kwargs))
        return self.detail


def prepared(tmp_path, intent='latest_regular'):
    client = Replay()
    state = tmp_path / 'state.json'
    save_state(state, {'shows': [{'title': '飙马野郎', 'aliases': ['Steel Ball Run'],
                                  'airing': True, 'status': 'airing'}]})
    track = StateRepository(state).read()['shows'][0]
    listing, detail, form = [tmp_path / x for x in ('listing.json', 'detail.json', 'review.json')]
    raw.save(listing, raw.listing('Steel Ball Run', client=client))
    raw.save(detail, raw.details('2165948', client=client))
    review = raw.draft(track, [listing], detail, intent, 2)
    review['reviewed'] = True
    review['coverage'] = {'complete_for_target': True, 'reason': 'Reviewed the complete first page: current releases are episode 2, then older episode 1.'}
    # Only a selection-relevant alternative is recorded. The 27 raw rows remain
    # available, with no forced paperwork for irrelevant historical releases.
    review['key_decisions'] = [{'candidate_id': '2165960', 'verdict': 'match', 'episode': 2,
                                'reason': 'Same episode, but below the one-GiB floor.'}]
    review['selection'] = {
        'kind': 'regular', 'work_reason': 'The exact Steel Ball Run subtitle and 2nd-3rd stage identify the tracked seventh part.',
        'work_quotes': ['JoJo no Kimyou na Bouken: Steel Ball Run - 2nd - 3rd STAGE'],
        'numbering': {'target_season': None, 'target_episode': 2, 'release_label': 'S06E02',
                      'reason': 'Source series season 6, episode 2; local standalone work has no season assigned. Its second episode opens the next stage.',
                      'evidence_quotes': ['Steel Ball Run - 2nd - 3rd STAGE', 'S06E02']},
        'video_file': client.detail.files[0].name,
        'subtitle_quotes': [line for line in client.detail.description.splitlines()
                            if '**Subtitles:**' in line]}
    raw.save(form, review)
    flags = ['--latest'] if intent == 'latest_regular' else ['--episode', '2']
    args = build_parser().parse_args(['飙马野郎', '--state', str(state), '--review', str(form),
                                      *flags, '--no-state-update', '--json'])
    return client, args, review


def revise(args, review):
    raw.save(args.review, review)


def test_raw_page_is_verbatim_chronological_and_does_not_filter_seasons():
    client = Replay()
    result = raw.listing('Steel Ball Run', client=client)
    assert len(result['rows']) == result['row_count'] == 27
    assert result['rows'][4]['nyaa_id'] == '2165948'
    assert 'S06E02' in result['rows'][4]['title']
    assert '2nd - 3rd STAGE, Multi-Audio, Multi-Subs)' in result['rows'][4]['title']
    assert client.calls[0][1] == ('Steel Ball Run', '1_0', '0', 1, 20)
    assert client.calls[0][2] == {'sort': 'id', 'order': 'desc'}


def test_query_is_not_cropped_or_expanded():
    client = Replay()
    text = 'A Long Official Title: Part 2 - 3rd STAGE'
    raw.listing(text, client=client)
    assert client.calls[0][1][0] == text and len(client.calls) == 1


def test_full_detail_keeps_languages_and_all_files():
    report = raw.details('2165948', client=Replay())
    assert 'Chinese (Simplified), Chinese (Traditional)' in report['description']
    assert report['description'] == Replay().detail.description
    assert len(report['files']) == 1


def test_reviewed_source_numbering_does_not_change_local_scope(tmp_path):
    client, args, review = prepared(tmp_path)
    before = args.state.read_bytes()
    (release, track), result = reviewed.audit(args, client=client)
    assert release.candidate_id == '2165948' and release.target.episode == 2
    assert release.identity.season is None
    assert result['raw_rows_available'] == 27 and result['key_decisions_recorded'] == 1
    assert args.state.read_bytes() == before


@pytest.mark.parametrize('change,code', [
    (lambda r: r.update(reviewed=False), 'agent_review_required'),
    (lambda r: r['key_decisions'][0].update(candidate_id='9999999'), 'invalid_key_decisions'),
    (lambda r: r['key_decisions'][0].update(verdict='unresolved'), 'latest_unresolved'),
    (lambda r: r['key_decisions'][0].update(episode=3), 'newer_episode_observed'),
    (lambda r: r['selection'].update(work_quotes=['fabricated work name']), 'work_evidence_required'),
    (lambda r: r['selection']['numbering'].update(target_season='S06'), 'review_numbering_conflict'),
    (lambda r: r['selection']['numbering'].update(release_label='S99E99'), 'release_numbering_evidence_required'),
    (lambda r: r.update(identity_revision=10), 'identity_revision_conflict'),
    (lambda r: r['coverage'].update(complete_for_target=False), 'coverage_review_required'),
])
def test_incomplete_or_inconsistent_review_is_blocked(tmp_path, change, code):
    client, args, review = prepared(tmp_path)
    before = args.state.read_bytes()
    change(review)
    revise(args, review)
    with pytest.raises(WorkflowError) as exc:
        reviewed.audit(args, client=client)
    assert exc.value.code == code
    assert args.state.read_bytes() == before


def test_changed_detail_requires_rereview(tmp_path):
    client, args, _ = prepared(tmp_path)
    client.detail = replace(client.detail, description=client.detail.description + ' new material')
    with pytest.raises(WorkflowError, match='candidate_details_changed'):
        reviewed.audit(args, client=client)
    assert raw.read(tmp_path / 'detail.fresh.json')['description'].endswith(' new material')


def test_changed_discovery_saves_fresh_evidence(tmp_path):
    client, args, _ = prepared(tmp_path)
    client.html = client.html.replace('2166157', '2169999')
    with pytest.raises(WorkflowError, match='discovery_changed'):
        reviewed.audit(args, client=client)
    assert (tmp_path / 'listing.fresh.json').exists()


def test_seed_count_change_does_not_invalidate_review(tmp_path):
    client, args, _ = prepared(tmp_path)
    client.detail = replace(client.detail, release=replace(client.detail.release, seeders=9999))
    assert reviewed.audit(args, client=client)[1]['selected']['seeders'] == 9999


def test_subfloor_and_multi_video_cannot_pass_as_single_episode(tmp_path):
    client, args, _ = prepared(tmp_path, 'specific_episode')
    client.detail = replace(client.detail, files=(replace(client.detail.files[0], size_bytes=800 * 1024 ** 2),))
    raw.save(tmp_path / 'detail.json', raw.details('2165948', client=client))
    with pytest.raises(WorkflowError, match='release_unqualified'):
        reviewed.audit(args, client=client)
    client.detail = replace(client.detail, files=client.detail.files * 2)
    raw.save(tmp_path / 'detail.json', raw.details('2165948', client=client))
    with pytest.raises(WorkflowError, match='single_regular_file_unconfirmed'):
        reviewed.audit(args, client=client)


def test_hard_chinese_needs_real_language_evidence(tmp_path):
    client, args, review = prepared(tmp_path)
    args.require_zh = True
    assert reviewed.audit(args, client=client)[1]['status'] == 'found'
    review['selection']['subtitle_quotes'] = ['Multi-Subs']
    revise(args, review)
    with pytest.raises(WorkflowError, match='subtitle_unqualified'):
        reviewed.audit(args, client=client)


def test_audit_never_calls_client_or_changes_state(tmp_path, capsys):
    client, args, _ = prepared(tmp_path)
    before = args.state.read_bytes()
    def forbidden(*a, **k):
        pytest.fail('Audit attempted delivery')
    assert reviewed.run(args, client=client, submit=forbidden) == 0
    assert args.state.read_bytes() == before
    assert json.loads(capsys.readouterr().out)['qbittorrent']['status'] == 'not_attempted'


def test_receipt_advances_once_without_rewriting_identity(tmp_path, capsys):
    client, args, _ = prepared(tmp_path)
    args.no_state_update = False
    args.enqueue_qbittorrent = args.include_magnet = args.legal_ok = True
    submitted = []
    def accepted(magnet, **options):
        submitted.append(magnet)
        return {'ok': True, 'status': 'submitted_verified'}
    assert reviewed.run(args, client=client, submit=accepted) == 0
    capsys.readouterr()
    after = StateRepository(args.state).read()['shows'][0]
    assert after['watched_episode'] == 2 and after['next_episode'] == 3
    assert after.get('season') is None and len(after['deliveries']) == 1
    assert reviewed.run(args, client=client, submit=accepted) == 0
    assert len(submitted) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'latest_already_handled'


def test_rejected_client_does_not_advance(tmp_path, capsys):
    client, args, _ = prepared(tmp_path)
    args.no_state_update = False
    args.enqueue_qbittorrent = args.include_magnet = args.legal_ok = True
    before = args.state.read_bytes()
    assert reviewed.run(args, client=client, submit=lambda *a, **k: {'ok': False, 'status': 'handoff_unverified'}) == 6
    assert args.state.read_bytes() == before
    assert json.loads(capsys.readouterr().out)['status'] == 'available_enqueue_failed'


def test_exact_track_edit_fills_unknown_scope_without_duplicate(tmp_path, capsys):
    _, args, review = prepared(tmp_path)
    assert watch.main(['--state', str(args.state), 'update', '飙马野郎', '--track-id', review['track_id'], '--season', 'S06']) == 0
    state = StateRepository(args.state).read()
    assert len(state['shows']) == 1
    assert state['shows'][0]['track_id'] == review['track_id']
    assert state['shows'][0]['season'] == 'S06'
    assert state['shows'][0]['identity_revision'] == 1


def test_lightweight_review_needs_no_historical_row_forms(tmp_path):
    client, args, review = prepared(tmp_path)
    review.pop('key_decisions')
    revise(args, review)
    assert reviewed.audit(args, client=client)[1]['key_decisions_recorded'] == 0


@pytest.mark.parametrize('change,code', [
    (lambda r: r['selection']['numbering'].update(evidence_quotes=[]), 'numbering_evidence_required'),
    (lambda r: r['selection']['numbering'].update(reason=''), 'numbering_review_required'),
    (lambda r: r.update(candidate_id='9999999'), 'selected_candidate_not_in_evidence'),
    (lambda r: r.update(schema_version=99), 'agent_review_required'),
])
def test_missing_evidence_never_submits(tmp_path, change, code):
    client, args, review = prepared(tmp_path)
    args.no_state_update = False
    args.enqueue_qbittorrent = args.include_magnet = args.legal_ok = True
    before = args.state.read_bytes()
    change(review)
    revise(args, review)
    with pytest.raises(WorkflowError, match=code):
        reviewed.run(args, client=client, submit=lambda *a, **k: pytest.fail('Unexpected delivery'))
    assert args.state.read_bytes() == before


def test_wrong_requested_work_and_readonly_enqueue_blocked(tmp_path):
    client, args, _ = prepared(tmp_path)
    args.title = 'An unrelated work'
    with pytest.raises(WorkflowError, match='review_work_conflict'):
        reviewed.audit(args, client=client)
    args.title = '飙马野郎'
    args.enqueue_qbittorrent = True
    with pytest.raises(WorkflowError, match='read_only_prohibits_enqueue'):
        reviewed.audit(args, client=client)


@pytest.mark.parametrize('info_hash', [None, 'not-a-hash', 'a' * 39])
def test_invalid_magnet_cannot_submit(tmp_path, info_hash):
    client, args, _ = prepared(tmp_path, 'specific_episode')
    client.detail = replace(client.detail, release=replace(client.detail.release, info_hash=info_hash))
    raw.save(tmp_path / 'detail.json', raw.details('2165948', client=client))
    with pytest.raises(WorkflowError, match='magnet_incomplete'):
        reviewed.run(args, client=client, submit=lambda *a, **k: pytest.fail('Unexpected delivery'))


def test_changed_hash_requires_new_review(tmp_path):
    client, args, _ = prepared(tmp_path)
    client.detail = replace(client.detail, release=replace(client.detail.release, info_hash='a' * 40))
    with pytest.raises(WorkflowError, match='candidate_details_changed'):
        reviewed.audit(args, client=client)


def test_cli_review_bypasses_legacy_resolver(tmp_path, monkeypatch, capsys):
    from anime_release import cli, workflow
    client, args, _ = prepared(tmp_path)
    monkeypatch.setattr(reviewed, 'NyaaClient', lambda: client)
    monkeypatch.setattr(workflow, 'run', lambda *a: pytest.fail('Legacy resolver called'))
    assert cli.main(['飙马野郎', '--state', str(args.state), '--review', str(args.review),
                     '--latest', '--no-state-update', '--json']) == 0
    assert json.loads(capsys.readouterr().out)['selected']['nyaa_id'] == '2165948'


def test_unknown_track_edit_cannot_create_record(tmp_path):
    _, args, _ = prepared(tmp_path)
    before = args.state.read_bytes()
    with pytest.raises(Exception):
        watch.main(['--state', str(args.state), 'update', '飙马野郎', '--track-id', 'missing', '--season', 'S06'])
    assert args.state.read_bytes() == before


def test_finale_receipt_preserves_completion_and_cleanup(tmp_path, capsys):
    client, args, _ = prepared(tmp_path)
    state = StateRepository(args.state).read()
    state['shows'][0]['completion'] = {'confirmed': True, 'final_episode': 2}
    save_state(args.state, state)
    args.no_state_update = False
    args.enqueue_qbittorrent = args.include_magnet = args.legal_ok = True
    assert reviewed.run(args, client=client, submit=lambda *a, **k: {'ok': True, 'status': 'submitted_verified'}) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'completed'
    assert result['automation_cleanup']['action'] == 'delete_owning_automation'
    assert StateRepository(args.state).read()['shows'][0]['next_episode'] is None
    client.calls.clear()
    assert reviewed.run(args, client=client, submit=lambda *a, **k: pytest.fail('Duplicate finale')) == 0
    assert not client.calls
    capsys.readouterr()
    args.no_state_update = True
    args.enqueue_qbittorrent = args.include_magnet = False
    assert reviewed.run(args, client=client) == 0
    assert json.loads(capsys.readouterr().out)['automation_cleanup']['action'] == 'keep'


def test_completion_evidence_uses_existing_work_binding_validator(tmp_path):
    client, args, review = prepared(tmp_path)
    state = StateRepository(args.state).read()
    state['shows'][0]['anilist_id'] = 123
    save_state(args.state, state)
    review['identity_revision'] = StateRepository(args.state).read()['shows'][0]['identity_revision']
    revise(args, review)
    args.completion_evidence = tmp_path / 'completion.json'
    completion = {'anilist_id': 123, 'season': None, 'reviewed': True, 'confirmed': True,
                  'final_episode': 2, 'source_kind': 'official', 'source_url': 'https://example.org/finale',
                  'evidence_text': 'Episode 2: finale (test fixture)', 'checked_at': raw.now()}
    raw.save(args.completion_evidence, completion)
    before = args.state.read_bytes()
    assert reviewed.audit(args, client=client)[0][1]['completion']['confirmed']
    assert args.state.read_bytes() == before
    completion['anilist_id'] = 999
    raw.save(args.completion_evidence, completion)
    with pytest.raises(WorkflowError, match='invalid_completion_evidence'):
        reviewed.audit(args, client=client)
