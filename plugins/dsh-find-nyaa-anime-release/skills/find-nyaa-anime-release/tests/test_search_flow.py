"""Replay full pages through the mechanical flow, retaining semantic boundaries."""
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

import search_flow as flow
from anime_release.models import WorkflowError
from watch_v3.store import StateRepository
from test_agent_reviewed_flow import Replay


def setup(tmp_path, **kwargs):
    state = tmp_path / 'state.json'
    repo = StateRepository(state)
    repo.command('steel', 'create_track', identity={'title': '飙马野郎',
        'aliases': ['Steel Ball Run'], 'season': None, 'provider_bindings': {}})
    client = Replay()
    result = flow.start(state, track_id='steel', query='Steel Ball Run',
                        intent='latest_regular', client=client, **kwargs)
    return state, client, result


def decision(client):
    return {'candidate_id': '2165948', 'episode': 2,
        'coverage': {'complete_for_target': True, 'reason': 'Full chronological page crosses current E02 into older E01.'},
        'selection': {'kind': 'regular', 'work_reason': 'Exact Steel Ball Run subtitle identifies the tracked standalone work.',
            'work_quotes': ['Steel Ball Run'], 'numbering': {'release_label': 'S06E02',
                'reason': 'Source season six E02 maps to local standalone work E02.', 'evidence_quotes': ['S06E02']},
            'subtitle_quotes': []},
        'quality_comparison': {'result': 'unknown', 'reason': 'Only metadata, no evidence of comparative picture advantage.',
                               'limitations': 'Subtitle tracks and picture superiority unverified.', 'alternatives': []}}


def test_query_prompt_reuses_identity_without_writes_or_network(tmp_path):
    state, client, result = setup(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    calls = len(client.calls)
    context = flow.start(state, track_id='steel', client=client)
    assert context['status'] == 'query_required'
    assert context['identity']['identity']['aliases'] == ['Steel Ball Run']
    assert len(client.calls) == calls
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_all_titles_rows_dates_survive_and_no_title_parser_selects(tmp_path):
    state, client, result = setup(tmp_path, pages=1)
    raw = flow.raw.read(Path(result['run']) / 'listing-1.json')
    table = result['listings'][0]
    assert table['rows'] == len(table['values']) == len(raw['rows']) == 27
    assert [v[1] for v in table['values']] == [r['title'] for r in raw['rows']]
    assert [v[0] for v in table['values']] == [r['nyaa_id'] for r in raw['rows']]
    assert all('T' in v[3] and ('+' in v[3] or '-' in v[3][-6:]) for v in table['values'])
    assert 'selected' not in result and 'decision' not in result


def test_package_aggregate_is_only_hint_all_ova_and_mixed_season_rows_remain(tmp_path):
    state, client, result = setup(tmp_path, pages=1)
    raw = flow.raw.read(Path(result['run']) / 'listing-1.json')
    raw['rows'][0].update(title='Example S01-S02 + OVA Complete', size_bytes=60 * 1024**3)
    raw['rows'][1].update(title='Example S01 OVA', size_bytes=200 * 1024**2)
    view = flow.table(raw, flow.policy_from_args(flow.argparse.Namespace()), {'kind': 'season', 'episodes': 12})
    assert len(view['values']) == len(raw['rows'])
    assert view['values'][0][1] == 'Example S01-S02 + OVA Complete'
    assert view['values'][0][-1] == 'above_estimate'
    assert view['values'][1][-1] == 'below_estimate'
    assert view['size_hint_basis']['episodes'] == 12


def test_full_detail_then_semantic_decision_audits_once_and_cleans_without_progress(tmp_path):
    state, client, result = setup(tmp_path, pages=1)
    before = state.read_bytes()
    run = Path(result['run'])
    detailed = flow.details(state, run, ['2165948', '2165948'], client=client)
    assert len(detailed['candidates']) == 1
    assert detailed['candidates'][0]['description'] == client.detail.description
    assert [f[0] for f in detailed['candidates'][0]['files']] == [f.name for f in client.detail.files]
    final = flow.finish(state, run, decision(client), client=client)
    assert final['eligibility'] == 'passed'
    assert final['selected']['nyaa_id'] == '2165948'
    assert final['selected']['subtitle_evidence'] == []
    assert final['qbittorrent']['status'] == 'not_attempted'
    assert state.read_bytes() == before and not run.exists()
    assert sum(c[0] == 'detail' for c in client.calls) == 2  # collect + one fresh audit


@pytest.mark.parametrize('mutate,code', [
    (lambda d: d['selection'].update(work_quotes=['invented title']), 'work_evidence_required'),
    (lambda d: d['coverage'].update(complete_for_target=False), 'coverage_review_required'),
    (lambda d: d['selection']['numbering'].update(release_label='S99E99'), 'release_numbering_evidence_required'),
    (lambda d: d['selection'].update(kind='special'), 'regular_episode_decision_required'),
    (lambda d: d.update(key_decisions=[{'candidate_id':'2165960', 'verdict':'match', 'episode':3, 'reason':'Newer episode observed'}]), 'newer_episode_observed'),
])
def test_semantic_decision_cannot_bypass_existing_validator(tmp_path, mutate, code):
    state, client, result = setup(tmp_path, pages=1)
    run = Path(result['run'])
    flow.details(state, run, ['2165948'], client=client)
    value = decision(client); mutate(value)
    with pytest.raises((WorkflowError, ValueError), match=code):
        flow.finish(state, run, value, client=client)
    assert run.is_dir()


@pytest.mark.parametrize('case', ['small', 'multivideo', 'changed', 'required_subtitles'])
def test_objective_checks_still_reject_invalid_or_changed_release(tmp_path, case):
    policy = flow.policy_from_args(flow.argparse.Namespace(require_zh=case == 'required_subtitles'))
    state, client, result = setup(tmp_path, pages=1, policy=policy)
    if case == 'small':
        client.detail = replace(client.detail, files=(replace(client.detail.files[0], size_bytes=400*1024**2),))
    if case == 'multivideo':
        client.detail = replace(client.detail, files=client.detail.files * 2)
    flow.details(state, result['run'], ['2165948'], client=client)
    if case == 'changed':
        client.detail = replace(client.detail, description=client.detail.description + ' changed')
    with pytest.raises((WorkflowError, ValueError)):
        flow.finish(state, result['run'], decision(client), client=client)


def test_changed_host_binding_and_cross_state_run_are_rejected(tmp_path):
    state, client, result = setup(tmp_path, binding={'plan': 'one', 'revision': 1})
    with pytest.raises(ValueError, match='search_binding_changed'):
        flow.details(state, result['run'], ['2165948'], binding={'plan': 'one', 'revision': 2}, client=client)
    other = state.with_name('other.json')
    with pytest.raises(ValueError, match='run_state_mismatch'):
        flow.load_session(other, result['run'], {'plan': 'one', 'revision': 1})


def test_failed_detail_is_retained_and_blocks_finish_until_retry(tmp_path):
    state, client, result = setup(tmp_path, pages=1)
    class Failed(Replay):
        def get(self, *a, **k):
            raise OSError('network unavailable')
    response = flow.details(state, result['run'], ['2165948'], client=Failed())
    assert response['status'] == 'search_incomplete'
    with pytest.raises(ValueError, match='incomplete_search_evidence'):
        flow.finish(state, result['run'], decision(client), client=client)
    assert flow.details(state, result['run'], ['2165948'], client=client)['status'] == 'details_ready'
    assert flow.finish(state, result['run'], decision(client), client=client)['eligibility'] == 'passed'


def test_exact_episode_is_locked(tmp_path):
    state, client, result = setup(tmp_path, pages=1)
    run, session = flow.load_session(state, result['run'])
    session.update(intent='specific_episode', episode=3)
    flow.save(run / 'session.json', session, state)
    flow.details(state, run, ['2165948'], client=client)
    with pytest.raises(ValueError, match='target_episode_conflict'):
        flow.finish(state, run, decision(client), client=client)


@pytest.mark.parametrize('unclassified', [False, True])
def test_season_requires_ai_file_mapping_despite_aggregate_hint(tmp_path, unclassified):
    state = tmp_path / 'state.json'
    client = Replay()
    file = client.detail.files[0]
    client.detail = replace(client.detail, files=tuple(replace(file, name=name, size_bytes=int(1.3*1024**3), size='1.3 GiB')
        for name in ['Steel Ball Run E01.mkv', 'Steel Ball Run E02.mkv', 'Steel Ball Run OVA.mkv']))
    scope = {'kind': 'season', 'title': 'Steel Ball Run', 'season': None, 'episodes': 2,
             'reviewed': True, 'source_url': 'https://official.example/episodes', 'evidence_text': 'Two regular episodes'}
    listing = flow.start(state, intent='season', scope=scope, query='Steel Ball Run', pages=1, client=client)
    flow.details(state, listing['run'], ['2165948'], client=client)
    value = decision(client)
    value['selection'] = {'work_reason': 'Verified standalone work.', 'work_quotes': ['Steel Ball Run'],
        'subtitle_quotes': [], 'episodes': [{'episode': n, 'files': [f'Steel Ball Run E{n:02}.mkv'],
            'reason': f'Explicit regular E{n:02}', 'quotes': [f'Steel Ball Run E{n:02}.mkv']} for n in (1,2)],
        'excluded_videos': [] if unclassified else [{'file': 'Steel Ball Run OVA.mkv',
                                                    'reason': 'Explicit OVA outside regular scope', 'quotes': ['Steel Ball Run OVA.mkv']}]}
    if unclassified:
        with pytest.raises(WorkflowError, match='unclassified_video_files'):
            flow.finish(state, listing['run'], value, client=client)
    else:
        result = flow.finish(state, listing['run'], value, client=client)
        assert result['eligibility'] == 'passed' and result['coverage']['episodes'] == 2
        assert StateRepository(state).read()['shows'] == []
