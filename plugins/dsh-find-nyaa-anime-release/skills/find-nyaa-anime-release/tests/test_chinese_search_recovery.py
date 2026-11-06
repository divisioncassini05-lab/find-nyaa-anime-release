"""Regression for a known episode whose ordinary releases lack Chinese subs."""
import pytest
import contextlib
import io
import json
from unittest.mock import Mock
import chinese_search
import find_anime_release as finder
import anime_release.workflow as v2_workflow
import release_search_core as core
import search_nyaa_releases as nyaa
from test_release_finder import candidate, search_args


CHS = '穹庐下的魔女'
CHT = '穹廬下的魔女'
JA = '天幕のジャードゥーガル'
LATIN = 'Tenmaku no Jaadugar'


@pytest.mark.parametrize('title', [CHS, CHT])
def test_both_scripts_without_a_stored_counterpart(title):
    names = finder.strict_zh_search_names([LATIN], title, None, cjk_aliases=[JA])
    assert CHS in names and CHT in names
    assert JA not in names


def test_pair_deduplication_does_not_consume_other_title_family():
    names = chinese_search.chinese_search_variants([JA, CHS, CHT, '二十世纪电气目录'])
    assert names == [CHS, CHT, '二十世纪电气目录', '二十世紀電氣目錄']
    assert chinese_search.chinese_search_variants([JA, '한국어', LATIN]) == []


def scenario(monkeypatch, *, supplement='found', strict=True, partial=False):
    args = search_args()
    args.query, args.alias, args.season = LATIN, [], 'S01'
    args.require_zh = args.want_zh = args.inspect_details = strict
    args.detail_limit = 5
    context = core.SearchContext(canonical_title=LATIN, aliases=(CHS, JA),
        search_titles=(LATIN,), resolved_season=1, mainline_scope='single',
        flexible_title_match=True)
    english = candidate('[Group] Tenmaku no Jaadugar S01E12 [1080p][MultiSub]', '1.7 GiB', 600)
    chinese = candidate('[ANi] Tenmaku no Jādūgar / 穹廬下的魔女 - 12 [1080P][CHT]', '1.7 GiB', 589)
    if supplement == 'too_small':
        chinese.size, chinese.size_bytes = '600 MiB', nyaa.parse_size('600 MiB')
    elif supplement == 'previous':
        chinese.title = chinese.title.replace(' - 12 ', ' - 11 ')
    elif supplement == 'wrong_season':
        chinese.title = '[ANi] Tenmaku no Jādūgar S02E12 [1080p][CHT]'
    elif supplement == 'special':
        chinese.title = '[ANi] Tenmaku no Jādūgar S01E12 OVA [1080p][CHT]'
    calls = []

    def collect(query_args, *_):
        calls.append(query_args)
        if not getattr(query_args, '_zh_supplement_done', False):
            return [english], ['ordinary query failed'] if partial else [], 'miss'
        if supplement == 'network':
            return [], ['supplement query failed'], 'refresh-partial'
        if supplement == 'empty':
            return [], [], 'refresh'
        if supplement == 'no_subs':
            return [english], [], 'refresh'
        return [chinese], [], 'refresh'

    monkeypatch.setattr(core, 'collect_raw_candidates', collect)
    monkeypatch.setattr(nyaa, 'fetch_nyaa_detail_text',
        lambda url, *_: 'Subtitle: Traditional Chinese (CHT)' if url == chinese.url else 'Subtitle: English')
    return args, context, calls


def test_latest_recovers_cht_after_non_chinese_episode_already_found(monkeypatch):
    args, context, calls = scenario(monkeypatch)
    report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR, context=context)
    assert report.status == 'found'
    assert report.intent == core.SearchIntent.LATEST_REGULAR
    assert report.requested_episode == report.search_run.target.confirmed_episode == 12
    assert report.selected[0].candidate.detail_chinese_confirmed
    assert len(calls) == 2
    assert core._raw_candidate_source(calls[0]) == 'nyaa_rss_recent'
    assert core._raw_candidate_source(calls[1]) == 'nyaa_html_size_desc'
    assert calls[1].episode == 12
    assert {f'{CHS} 12', f'{CHT} 12', 'Tenmaku 12'} <= {calls[1].query, *calls[1].alias}
    assert len(report.search_run.raw_candidates) == 2
    assert any(q['lane'] == 'strict_zh_exact_supplement' for q in report.search_run.query_plan)
    assert context.aliases == (CHS, JA)  # converted spelling is not persisted as identity


@pytest.mark.parametrize('mode', ['too_small', 'previous', 'wrong_season', 'special', 'no_subs', 'empty', 'network'])
def test_recovery_never_relaxes_target_or_hard_requirements(monkeypatch, mode):
    args, context, calls = scenario(monkeypatch, supplement=mode)
    report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR, context=context)
    assert report.status != 'found'
    assert not report.selected
    assert report.requested_episode == 12
    assert report.diagnostics['strict_zh_supplement']['attempted']
    # Empty/other-episode scans may use the existing bounded numbering fallback,
    # but must never restart the broad search or another Chinese supplement.
    assert sum(not getattr(c, '_zh_supplement_done', False) for c in calls) == 1
    if mode == 'network':
        assert report.status == 'network_error'
        assert report.search_run.completeness == 'partial'


def test_unresolved_latest_does_not_supplement(monkeypatch):
    args, context, calls = scenario(monkeypatch, partial=True)
    report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR, context=context)
    assert report.status == 'latest_unresolved'
    assert len(calls) == 1


def test_soft_chinese_does_not_trigger_strict_recovery(monkeypatch):
    args, context, calls = scenario(monkeypatch, strict=False)
    report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR, context=context)
    assert report.status == 'found'
    assert len(calls) == 1


def test_specific_episode_uses_same_recovery(monkeypatch):
    args, context, calls = scenario(monkeypatch)
    args.episode = 12
    report = core.search_release_report(args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12, context=context)
    assert report.status == 'found'
    assert len(calls) == 2


def test_pinned_failure_never_replaces_reviewed_id(monkeypatch):
    args, context, calls = scenario(monkeypatch)
    args.candidate_id = ['2160124']
    failed = core.ReleaseSearchReport(intent=core.SearchIntent.SPECIFIC_EPISODE,
        requested_season=1, requested_episode=12, status='subtitle_unqualified',
        selected=[], choices=[], diagnostics={}, failures=[], cache='miss')
    monkeypatch.setattr(core, '_search_release_impl', lambda *a, **k: failed)
    report = core.search_release_report(args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12, context=context)
    assert report is failed
    assert not calls
    assert not report.diagnostics.get('strict_zh_supplement')


def test_high_level_latest_recovery_is_readonly_and_reports_both_scripts(monkeypatch, tmp_path):
    scenario(monkeypatch)
    state_path = tmp_path / 'state.json'
    state_path.write_text(json.dumps({'version': 1, 'shows': [{
        'title': CHS, 'aliases': [LATIN, JA], 'search_titles': [LATIN],
        'verified_search_titles': [LATIN], 'watched_episode': 11,
        'next_episode': 12, 'latest_known_episode': 11, 'season': 'S01',
        'mainline_scope': 'single', 'airing': True, 'format': 'TV',
    }]}), encoding='utf-8')
    before = state_path.read_bytes()
    submit = Mock(side_effect=AssertionError('Discovery must not enqueue'))
    monkeypatch.setattr(v2_workflow, 'submit_magnet', submit)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = finder.main([CHS, '--latest', '--require-zh', '--no-state-update',
            '--no-web-resolve', '--json', '--state', str(state_path),
            '--cache', str(tmp_path / 'cache.json'),
            '--schedule-cache', str(tmp_path / 'schedule.json')])
    report = json.loads(output.getvalue())
    assert code == 0
    assert report['status'] == 'found'
    assert report['target_episode'] == 12
    assert report['selected']['detail_chinese_confirmed']
    assert {CHS, CHT, f'{CHS} 12', f'{CHT} 12'} <= set(report['diagnostic']['queries'])
    assert report['diagnostic']['strict_zh_supplement']['attempted']
    assert state_path.read_bytes() == before
    submit.assert_not_called()


def test_completed_supplement_routes_to_rescue_without_repeating(monkeypatch):
    from failure_recovery import recovery_plan
    args, context, _ = scenario(monkeypatch, supplement='too_small')
    report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR, context=context)
    plan = recovery_plan({'status': report.status, 'intent': 'latest_regular',
        'target_episode': report.requested_episode, 'diagnostic': report.diagnostics})
    assert plan['action'] == 'eligible_official_date_rescue'
    assert plan['release_confirmed'] and plan['latest_confirmed']
