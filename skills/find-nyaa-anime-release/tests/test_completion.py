"""Broadcast completion must not be confused with release delivery."""
import contextlib
import copy
import io
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import completion
import find_anime_release as finder
import anime_release.workflow as v2_workflow
import anime_release.metadata as v2_metadata
import airing_watch_state as watch
import state_io
import release_search_core as core
from test_release_finder import candidate
from release_identity import parse_release_identity


def evidence(**changes):
    return dict({'anilist_id': 190569, 'bangumi_id': 552533, 'season': 'S01',
                 'reviewed': True, 'confirmed': True, 'final_episode': 12,
                 'end_date': '2026-09-12', 'source_kind': 'broadcaster',
                 'source_url': 'https://www.bs-asahi.co.jp/anime-jaadugar/lineup/prg_012/',
                 'evidence_text': '第12幕（最終回）', 'checked_at': '2026-09-20T11:00:00+00:00'}, **changes)


def show(handled=12, **changes):
    return dict({'title': 'Tenmaku no Jaadugar', 'season': 'S01', 'aliases': [],
                 'anilist_id': 190569, 'bangumi_id': 552533, 'format': 'TV',
                 'search_titles': ['Tenmaku no Jaadugar'], 'verified_search_titles': ['Tenmaku no Jaadugar'],
                 'watched_episode': handled, 'latest_known_episode': handled, 'next_episode': handled + 1,
                 'airing': True, 'status': 'airing'}, **changes)


def run(tmp_path, record, flags=(), ev=None, search_result=None, client=None):
    path = tmp_path / 'state.json'
    state_io.save_state(path, {'version': 1, 'shows': [record]})
    before = path.read_bytes()
    argv = [record['title'], '--state', str(path), '--schedule-cache', str(tmp_path / 'schedule.json'),
            '--cache', str(tmp_path / 'rss.json'), '--no-web-resolve', '--json', *flags]
    if ev is not None:
        ep = tmp_path / 'evidence.json'
        ep.write_text(json.dumps(ev), encoding='utf-8')
        argv += ['--completion-evidence', str(ep)]
    out = io.StringIO()
    with patch.object(v2_workflow, 'search_release_report', return_value=search_result) as search, \
         patch.object(v2_metadata, 'hydrate_airing_metadata', side_effect=AssertionError('no metadata request')) as hydrate, \
         patch.object(v2_workflow, 'submit_magnet', return_value=client) as submit, contextlib.redirect_stdout(out):
        code = finder.main(argv)
    return json.loads(out.getvalue()), state_io.load_state(path)['shows'][0], before == path.read_bytes(), search, submit, hydrate, code


@pytest.mark.parametrize('flags', [[], ['--latest']])
@pytest.mark.parametrize('readonly', [False, True])
def test_final_handled_short_circuits_all_network(tmp_path, flags, readonly):
    result, saved, same, search, submit, hydrate, code = run(tmp_path, show(),
        flags + (['--no-state-update'] if readonly else []), evidence())
    assert result['status'] == 'completed' and code == 0
    assert result['progress']['next_episode'] is None
    search.assert_not_called()
    submit.assert_not_called()
    hydrate.assert_not_called()
    assert same == readonly
    if not readonly:
        assert result['automation_cleanup']['action'] == 'delete_owning_automation'
        assert result['automation_cleanup']['executed'] is False
        assert saved['status'] == saved['tracking_status'] == 'completed'
        assert saved['next_episode'] is None and saved['airing'] is False
        assert saved['watched_episode'] == 12
        assert saved['completion']['end_date'] == '2026-09-12'
    else:
        assert result['automation_cleanup']['action'] == 'keep'


def test_completed_record_repeat_is_zero_write(tmp_path):
    record = show(status='completed', tracking_status='completed', airing=False, next_episode=None,
                  total_episodes=12, completion=evidence())
    result, saved, same, search, submit, *_ = run(tmp_path, record, ['--latest'])
    assert result['status'] == 'completed' and same
    assert result['automation_cleanup']['action'] == 'delete_owning_automation'
    search.assert_not_called()
    submit.assert_not_called()


@pytest.mark.parametrize('value,precision', [(None, None), ('2026', 'year'), ('2026-09', 'month'), ('2026-09-12', 'day')])
def test_date_precision(value, precision):
    assert completion.end_date(value) == (value, precision)


@pytest.mark.parametrize('change', [dict(anilist_id=1), dict(season='S02'), dict(reviewed=False),
    dict(final_episode=0), dict(final_episode=True), dict(end_date='2026-02-30'), dict(end_date='2099-01-01'),
    dict(source_kind='search_snippet'), dict(checked_at='2026-09-01'), dict(source_url='file:///tmp/fake')])
def test_bad_evidence_fails_without_side_effects(tmp_path, change):
    result, _, same, search, submit, *rest = run(tmp_path, show(), ['--latest'], evidence(**change))
    assert result['status'] == 'invalid_completion_evidence' and same
    search.assert_not_called()
    submit.assert_not_called()


def empty_report(status='subtitle_unqualified'):
    return core.ReleaseSearchReport(intent=core.SearchIntent.SPECIFIC_EPISODE, requested_season=1,
        requested_episode=12, status=status, selected=[], choices=[], diagnostics={}, failures=[], cache='miss')


@pytest.mark.parametrize('failure', ['subtitle_unqualified', 'release_unqualified', 'network_error'])
def test_unhandled_finale_keeps_requirements_and_progress(tmp_path, failure):
    result, saved, *_rest = run(tmp_path, show(11), ['--latest', '--require-zh'], evidence(), empty_report(failure))
    search, submit = _rest[1:3]
    assert result['status'] == failure and result['target_episode'] == 12
    assert saved['watched_episode'] == 11 and saved['status'] != 'completed'
    assert search.call_args.args[0].episode == 12
    assert search.call_args.args[0].require_zh
    assert search.call_args.args[0].min_gib_per_episode == 1.0
    submit.assert_not_called()


def final_report():
    release = candidate('[Group] Tenmaku no Jaadugar - 12 [1080p]', '1.4 GiB', 12)
    release.magnet = 'magnet:?xt=urn:btih:' + '1' * 40
    release.url = 'https://nyaa.si/view/123'
    item = core.ClassifiedCandidate(release, parse_release_identity(release.title), 'match')
    report = empty_report('found')
    report.selected = [item]
    return report


@pytest.mark.parametrize('client,done', [({'status': 'submitted_verified', 'ok': True}, True),
    ({'status': 'already_present', 'ok': True}, True), ({'status': 'handoff_unverified', 'ok': False}, False)])
def test_final_delivery_boundary(tmp_path, client, done):
    flags = ['--latest', '--candidate-id', '123', '--include-magnet', '--legal-ok', '--enqueue-qbittorrent']
    result, saved, *_ = run(tmp_path, show(11), flags, evidence(), final_report(), client)
    assert (saved['status'] == 'completed') == done
    assert saved['watched_episode'] == (12 if done else 11)
    assert result['progress']['next_episode'] == (None if done else 12)
    assert result['status'] == ('completed' if done else 'download_enqueue_failed')


def test_manual_old_episode_is_retrieval_only(tmp_path):
    record = show(status='completed', airing=False, next_episode=None, total_episodes=12, completion=evidence())
    result, saved, same, search, *_ = run(tmp_path, record,
        ['--episode', '12', '--include-magnet', '--legal-ok'], search_result=final_report())
    assert same and result['status'] == 'found' and search.called


def test_planned_date_does_not_prove_completion(tmp_path):
    result, saved, same, search, *_ = run(tmp_path, show(), ['--latest'], evidence(confirmed=False))
    assert result['status'] == 'needs_completion_review' and same
    search.assert_not_called()
    assert saved['status'] == 'airing'


def test_missing_date_with_final_evidence_still_completes(tmp_path):
    result, *_ = run(tmp_path, show(), ['--latest'], evidence(end_date=None))
    assert result['status'] == 'completed'


def test_metadata_and_merge():
    media = {'id': 190569, 'title': {'romaji': 'Tenmaku no Jaadugar'}, 'format': 'TV',
             'status': 'FINISHED', 'episodes': 12, 'season': 'SUMMER', 'seasonYear': 2026,
             'endDate': {'year': 2026, 'month': 9, 'day': None}}
    fresh, _ = finder.media_to_resolved('Tenmaku no Jaadugar', media, date(2026, 9, 20))
    merged = finder.merge_resolved(finder.resolved_from_state(show(), ''), fresh)
    assert not merged.current and not merged.trackable
    assert merged.completion['end_date'] == '2026-09'
    assert finder.resolved_from_snapshot(finder.resolved_snapshot(merged), merged).completion == merged.completion


def test_conflicting_metadata_needs_review():
    base = finder.resolved_from_state(show(total_episodes=12, completion=evidence()), '')
    fresh = finder.ResolvedAnime('Tenmaku no Jaadugar', episodes=13, status='FINISHED',
        completion={'confirmed': True, 'final_episode': 13})
    merged = finder.merge_resolved(base, fresh)
    assert not completion.confirmed(merged)
    assert completion.review_reasons(merged, 12, date.today()) == ['conflicting_completion_evidence']


def test_delayed_planned_date_replaces_old_date():
    base = finder.ResolvedAnime('A', completion={'confirmed': False, 'end_date': '2026-09-12'})
    fresh = finder.ResolvedAnime('A', status='RELEASING', completion={'confirmed': False, 'end_date': '2026-10-12'})
    merged = finder.merge_resolved(base, fresh)
    assert completion.review_reasons(merged, 11, date(2026, 9, 20)) == []


def test_concurrent_stale_writer_cannot_resurrect():
    base = {'version': 1, 'shows': [show()]}
    done = copy.deepcopy(base)
    resolved = finder.resolved_from_state(show(total_episodes=12, completion=evidence()), '')
    completion.mark_completed(done['shows'][0], resolved)
    saved = state_io.merge_state(base, base, done)
    assert saved['shows'][0]['next_episode'] is None
    stale = copy.deepcopy(base)
    stale['shows'][0].update(status='waiting', next_episode=14, watched_episode=13)
    merged = state_io.merge_state(saved, base, stale)['shows'][0]
    assert merged['status'] == 'completed' and merged['next_episode'] is None and merged['watched_episode'] == 12


def test_low_level_record_cannot_resurrect():
    data = {'shows': [show(status='completed', next_episode=None)]}
    assert watch.record_found_episode(data, 'Tenmaku no Jaadugar', 13)['reason'] == 'season_completed'


def test_split_cour_boundary_retained(tmp_path):
    record = show(total_episodes=12, completion=evidence(), continuation_parts=[{
        'explicit_split_cour': True, 'title': 'Tenmaku Part 2', 'start_date': '2027-01-01'}])
    result, _, _, search, *_ = run(tmp_path, record, ['--latest'])
    assert result['status'] == 'split_cour_break'
    assert result['availability']['part']['return_date'] == '2027-01-01'
    search.assert_not_called()


def test_unavailable_airing_metadata_requests_web_before_nyaa(tmp_path):
    path = tmp_path / 'state.json'
    state_io.save_state(path, {'shows': [show()]})
    resolved = finder.resolved_from_state(show(), '')
    out = io.StringIO()
    with patch.object(v2_metadata, 'hydrate_airing_metadata', return_value=(resolved, 'unavailable')), \
         patch.object(v2_workflow, 'search_release_report') as search, contextlib.redirect_stdout(out):
        finder.main(['Tenmaku no Jaadugar', '--latest', '--state', str(path), '--json', '--no-state-update'])
    report = json.loads(out.getvalue())
    assert report['status'] == 'needs_completion_review'
    assert report['recovery']['action'] == 'verify_official_completion_evidence'
    search.assert_not_called()


def test_completed_show_does_not_stop_batch_other_show(tmp_path):
    path = tmp_path / 'state.json'
    state_io.save_state(path, {'shows': [
        show(status='completed', next_episode=None, total_episodes=12, completion=evidence()),
        {'title': 'Grow Up Show', 'search_titles': ['Grow Up Show'], 'season': 'S01',
         'watched_episode': 11, 'next_episode': 12, 'airing': True} ]})
    out = io.StringIO()
    with patch.object(v2_workflow, 'search_release_report', return_value=empty_report('network_error')) as search, \
         contextlib.redirect_stdout(out):
        finder.main(['Tenmaku no Jaadugar Grow Up Show', '--latest', '--no-web-resolve',
            '--state', str(path), '--json', '--no-state-update'])
    report = json.loads(out.getvalue())
    assert report['status'] == 'batch'
    assert [r['status'] for r in report['results']] == ['completed', 'network_error']
    assert search.call_count == 1
    assert report['automation_cleanup']['action'] == 'keep'


def test_cleanup_requires_every_reported_show_to_be_persisted_and_complete():
    done = {'status': 'completed', 'state_update': 'completed',
            'completion': {'final_episode': 12},
            'progress': {'after_episode': 12, 'next_episode': None}}
    assert completion.automation_cleanup({'status': 'batch', 'results': [done, done]})['eligible']
    for failure in ('network_error', 'download_enqueue_failed', 'split_cour_break', 'needs_completion_review'):
        assert not completion.automation_cleanup({'status': 'batch', 'results': [done, {**done, 'status': failure}]})['eligible']
    assert not completion.automation_cleanup({'status': 'batch', 'results': []})['eligible']
    assert not completion.automation_cleanup({**done, 'progress': {'after_episode': 11, 'next_episode': None}})['eligible']
    assert not completion.automation_cleanup({**done, 'state_update': 'none'})['eligible']
