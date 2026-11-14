import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/find-nyaa-anime-release/scripts'))
import dsh_panel_run as panel
from watch_v3.store import StateRepository


def setup(tmp_path, **changes):
    state = tmp_path / 'state.json'
    plan = {'id': 'wanted', 'revision': 1, 'title': 'Atlas', 'season': None,
            'trackId': 'atlas', 'bangumiSubjectId': 12345, 'mode': 'latest_regular',
            'tier': 'browse', 'requireZh': True, 'enqueue': False, **changes}
    other = {**plan, 'id': 'other', 'trackId': 'other', 'title': 'Other private plan'}
    state.with_suffix('.plans.json').write_text(json.dumps({'version': 1, 'plans': [plan, other]}))
    return state, plan


def files(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_context_is_scoped_read_only_and_does_not_probe_services(tmp_path, monkeypatch, capsys):
    state, plan = setup(tmp_path)
    repo = StateRepository(state)
    repo.command('atlas', 'create_track', identity={'title': 'Atlas', 'aliases': ['Atlas Chronicle'],
                 'season': None, 'provider_bindings': {'bangumi': {'entry_id': 12345}}})
    result = panel.result_path(state, plan['id'])
    result.parent.mkdir(exist_ok=True)
    result.write_text(json.dumps({'finds': [{'scope': 'regular', 'episode': 2}],
                                  'private_marker': 'must-not-export'}))
    before = files(tmp_path)
    def forbidden(*a, **kw):
        pytest.fail('read-only context attempted a mutation or download/cloud probe')
    for name in ('snapshot', 'ensure_watching', 'file_lock', 'atomic_json'):
        monkeypatch.setattr(panel, name, forbidden)
    assert panel.main(['--state', str(state), '--plan-id', 'wanted', 'context']) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['read_only'] is True
    assert report['track']['identity']['aliases'] == ['Atlas Chronicle']
    assert report['recorded']['regular_episodes'] == [2]
    assert report['policy_args'] == ['--tier', 'browse', '--require-zh']
    assert report['quality_policy']['allow_upward'] is False
    assert report['size_bounds']['regular_max_gib'] == 2
    assert 'Other private plan' not in output and 'must-not-export' not in output
    assert files(tmp_path) == before


@pytest.mark.parametrize('mode,reference', [('next_tracked', 'agent-review.md'),
    ('latest_regular', 'agent-review.md'), ('missing_episodes', 'agent-review.md'),
    ('season_batch', 'package-review.md'), ('movie', 'package-review.md')])
def test_context_keeps_missing_tracks_absent_and_retains_package_binding(tmp_path, mode, reference):
    state, plan = setup(tmp_path, mode=mode, tier='watch', requireZh=False)
    before = files(tmp_path)
    report = panel.plan_context(state, plan)
    assert report['track'] is None
    assert report['review_reference'] == 'references/' + reference
    assert report['plan']['intent'] == ('latest_regular' if mode == 'next_tracked' else mode)
    assert report['policy_args'] == ['--tier', 'watch']
    assert report['size_bounds']['regular_min_gib'] == 2
    assert report['size_bounds']['regular_max_gib'] == 4
    assert report['quality_policy']['want_zh'] is False
    if mode in {'season_batch', 'movie'}:
        assert report['package_scope_binding'] == {'title': 'Atlas', 'season': None, 'bangumi_id': 12345}
    assert files(tmp_path) == before


@pytest.mark.parametrize('change,scheduled,code', [({'paused': True}, False, 'plan_paused_or_deleted'),
    ({'deleted': True}, False, 'plan_paused_or_deleted'),
    ({'schedulePaused': True}, True, 'automatic_run_disabled')])
def test_context_preserves_plan_execution_guards(tmp_path, change, scheduled, code):
    state, _ = setup(tmp_path, **change)
    with pytest.raises(ValueError, match=code):
        panel.main(['--state', str(state), '--plan-id', 'wanted',
                    *(['--scheduled'] if scheduled else []), 'context'])


def test_safe_errors_identify_recoverable_stage_without_leaking_exception_text():
    error = PermissionError(13, 'password=do-not-echo', '/state/results.lock')
    report = panel.cli_error(error)
    assert report['error'] == 'permission_denied'
    assert report['path'] == '/state/results.lock'
    assert report['next_action'] == 'use_host_approved_access_or_stop'
    assert 'password' not in json.dumps(report)
    assert panel.cli_error(ValueError('panel_work_mismatch'))['error'] == 'panel_work_mismatch'
    assert panel.cli_error(ValueError('credential=private'))['error'] == 'ValueError'


@pytest.mark.parametrize('mutation', [None, 'different_subject', 'gap', 'tampered', 'outside'])
def test_package_scope_comes_from_bound_retained_ai_review(tmp_path, mutation):
    from submission_gate import digest
    state, plan = setup(tmp_path, mode='season_batch')
    review = {'reviewed': True, 'scope': {'kind': 'season', 'episodes': 24, 'bangumi_id':12345},
              'selection': {'episodes': [{'episode': n} for n in range(1,25)]}}
    if mutation == 'different_subject':
        review['scope']['bangumi_id'] = 999
    if mutation == 'gap':
        review['selection']['episodes'][-1]['episode'] = 26
    root = panel.result_path(state, plan['id']).parent / plan['id'] / ('a'*40)
    root.mkdir(parents=True)
    path = (tmp_path if mutation == 'outside' else root) / ('review-' + digest(review) + '.json')
    if mutation == 'tampered':
        review['scope']['episodes'] = 25
    path.write_text(json.dumps(review), encoding='utf-8')
    entry = {'infoHash':'a'*40, 'scope':'season', 'reviewPath':str(path)}
    assert panel.package_regular_episodes(state,plan,entry) == (None if mutation else 24)
