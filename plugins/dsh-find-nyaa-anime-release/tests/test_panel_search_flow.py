"""Real shared flow through the DSH owner wrapper, with captured page transport."""
import io
import json
from pathlib import Path
import sys

import pytest

SKILL = Path(__file__).resolve().parents[1] / 'skills/find-nyaa-anime-release'
sys.path.insert(0, str(SKILL / 'scripts'))
sys.path.insert(0, str(SKILL / 'tests'))
import search_flow as flow
import dsh_panel_run as panel
from test_agent_reviewed_flow import Replay
from test_search_flow import decision
from test_panel_context import setup
from watch_v3.store import StateRepository


def prepared(tmp_path, monkeypatch):
    state, plan = setup(tmp_path, title='飙马野郎', trackId='steel', requireZh=False)
    StateRepository(state).command('steel', 'create_track', identity={'title': '飙马野郎',
        'aliases': ['Steel Ball Run'], 'season': None, 'provider_bindings': {'bangumi': {'entry_id':12345}}})
    client = Replay()
    listing, details = flow.raw.listing, flow.raw.details
    monkeypatch.setattr(flow.raw, 'listing', lambda q, p=1, **kw: listing(q, p, client=client))
    monkeypatch.setattr(flow.raw, 'details', lambda cid, **kw: details(cid, client=client))
    monkeypatch.setattr(panel, 'ensure_watching', lambda *a, **kw: None)
    return state, plan, client


def call(state, capsys, *args):
    code = panel.main(['--state', str(state), '--plan-id', 'wanted', 'search', *args])
    return code, json.loads(capsys.readouterr().out)


def test_no_query_start_never_writes_or_attempts_optional_sync(tmp_path, monkeypatch, capsys):
    state, plan, client = prepared(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('Read-only context attempted a write/sync')
    monkeypatch.setattr(panel, 'ensure_watching', forbidden)
    before = {str(path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    code, result = call(state, capsys, 'start')
    assert code == 0 and result['status'] == 'query_required' and result['read_only'] is True
    assert result['write_directory'] == str(state.resolve().parent)
    assert client.calls == []
    assert before == {str(path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}


def test_panel_full_flow_records_validated_find_and_preserves_manual_progress(tmp_path, monkeypatch, capsys):
    state, plan, client = prepared(tmp_path, monkeypatch)
    before = state.read_bytes()
    _, listing = call(state, capsys, 'start', '--query', 'Steel Ball Run', '--pages', '1')
    run = listing['run']
    assert listing['intent'] == 'latest_regular'
    call(state, capsys, 'details', '--run', run, '--ids', '2165948')
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(decision(client))))
    code, result = call(state, capsys, 'finish', '--run', run)
    assert code == 0 and result['eligibility'] == 'passed'
    assert not Path(run).exists() and state.read_bytes() == before
    saved = panel.read(panel.result_path(state, 'wanted'), {})
    assert saved['finds'][0]['episode'] == 2
    assert Path(saved['finds'][0]['reviewPath']).is_file()  # durable copy before scratch cleanup


def test_changed_plan_cannot_finish_old_session(tmp_path, monkeypatch, capsys):
    state, plan, client = prepared(tmp_path, monkeypatch)
    _, listing = call(state, capsys, 'start', '--query', 'Steel Ball Run', '--pages', '1')
    plans = panel.read(state.with_suffix('.plans.json'), {})
    plans['plans'][0]['revision'] += 1
    state.with_suffix('.plans.json').write_text(json.dumps(plans))
    with pytest.raises(ValueError, match='search_binding_changed'):
        call(state, capsys, 'details', '--run', listing['run'], '--ids', '2165948')


def test_panel_policy_is_supplied_by_plan_and_cannot_be_weakened_in_session(tmp_path, monkeypatch, capsys):
    state, plan, client = prepared(tmp_path, monkeypatch)
    _, listing = call(state, capsys, 'start', '--query', 'Steel Ball Run', '--pages', '1', '--tier', 'premium')
    assert listing['quality_policy']['tier'] == 'browse'
    run = Path(listing['run'])
    session = flow.read(run / 'session.json'); session['policy']['allow_upward'] = True
    flow.save(run / 'session.json', session, state)
    with pytest.raises(ValueError, match='panel_search_scope_mismatch'):
        call(state, capsys, 'details', '--run', str(run), '--ids', '2165948')


def test_panel_does_not_accept_download_flag_when_plan_is_link_only(tmp_path, monkeypatch, capsys):
    state, plan, client = prepared(tmp_path, monkeypatch)
    _, listing = call(state, capsys, 'start', '--query', 'Steel Ball Run', '--pages', '1')
    with pytest.raises(ValueError, match='panel_download_not_authorized'):
        call(state, capsys, 'finish', '--run', listing['run'], '--enqueue-qbittorrent', '--legal-ok')


@pytest.mark.parametrize('mode', ['season_batch', 'movie'])
def test_package_starts_with_exact_plan_binding_and_no_synthetic_track(tmp_path, monkeypatch, capsys, mode):
    state, plan = setup(tmp_path, mode=mode)
    code, result = call(state, capsys, 'start')
    assert code == 0 and result['status'] == 'package_scope_required'
    assert result['package_scope_binding']['bangumi_id'] == 12345
    assert StateRepository(state).find(track_id=plan['trackId']) is None
