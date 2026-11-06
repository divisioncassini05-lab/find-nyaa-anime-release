import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'find-nyaa-anime-release' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import dsh_host as host
import dsh_paths as paths

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('ANIME_DSH_HOME', str(tmp_path / 'data'))


def task(**patch):
    return {'id': 'schedule-123', 'title': 'Anime check', 'prompt': 'Track alpha "中文"\nDo not change scope.\n',
            'kind': 'weekly', 'time': '22:00', 'timeZone': 'Asia/Shanghai', 'weekdays': [6],
            'scheduledAt': '2026-11-07T14:00:00.000Z', 'status': 'active',
            'target': {'kind': 'session', 'sessionId': 'current-user-session'},
            'updatedAt': '2026-11-07T11:00:00.000Z', **patch}


def page(rows, total=None, offset=0):
    return {'items': rows, 'shown': len(rows), 'total': len(rows) if total is None else total,
            'limit': 100, 'offset': offset}


def inventory(pages=None, **patch):
    return {'observed_at': NOW.isoformat(), 'unfiltered': True,
            'pages': pages if pages is not None else [page([task()])], **patch}


def observed(t=None):
    return {'observed_at': NOW.isoformat(), 'task': t or task()}


def test_state_never_adopts_codex(monkeypatch):
    monkeypatch.setenv('ANIME_TRACKING_STATE', 'C:/publisher-private/state.json')
    monkeypatch.setenv('CODEX_HOME', 'C:/publisher-private/.codex')
    assert paths.state_path() == paths.data_home() / 'airing_watch_state.json'
    assert 'publisher-private' not in str(paths.state_path())
    assert not paths.data_home().exists()


@pytest.mark.parametrize('platform,expected', [('win32', 'DSH/AnimeRelease'),
    ('darwin', 'Library/Application Support/DSH/AnimeRelease'), ('linux', 'dsh/anime-release')])
def test_portable_default_path(monkeypatch, platform, expected):
    monkeypatch.delenv('ANIME_DSH_HOME')
    monkeypatch.setattr(sys, 'platform', platform)
    assert paths.data_home().as_posix().endswith(expected)


def test_relative_home_is_rejected(monkeypatch):
    monkeypatch.setenv('ANIME_DSH_HOME', '../other')
    with pytest.raises(ValueError):
        paths.data_home()


def test_complete_inventory_preserves_scope_hash():
    host.import_inventory(inventory(), NOW)
    result = host.inventory_for_state({'shows': [{'track_id': 'alpha', 'identity': {'title': 'Other'}}]}, NOW)
    assert not result['errors']
    assert result['automations'][0]['referenced_track_ids'] == ['alpha']
    assert result['automations'][0]['scope_hash'] == host.hashlib.sha256(task()['prompt'].encode()).hexdigest()


def test_full_pagination():
    result = host.parse_inventory(inventory([page([task()], 2), page([task(id='two')], 2, 1)]), NOW)
    assert len(result['tasks']) == 2


@pytest.mark.parametrize('bad', [
    inventory([page([task()], 2)]), inventory([page([task()], 2), page([task(id='two')], 3, 1)]),
    inventory([page([task()], 2), page([task()], 2, 1)]), inventory([{'code': 'permission_denied'}]),
    inventory(unfiltered=False), inventory([page([task(status='UNKNOWN')])]),
    inventory(observed_at=(NOW - timedelta(minutes=3)).isoformat()),
    inventory(observed_at=(NOW + timedelta(seconds=1)).isoformat()),
])
def test_bad_inventory_invalidates_old_snapshot(bad):
    host.import_inventory(inventory(), NOW)
    with pytest.raises((ValueError, KeyError, TypeError)):
        host.import_inventory(bad, NOW)
    assert host.inventory_for_state({'shows': []}, NOW)['errors']


def test_no_inventory_is_not_no_schedules():
    assert host.inventory_for_state({'shows': []}, NOW)['errors']


@pytest.mark.parametrize('content', ['not json', '[]', None])
def test_unreadable_import_invalidates_previous_snapshot(tmp_path, content):
    host.import_inventory(inventory(), NOW)
    source = tmp_path / 'input.json'
    if content is not None:
        source.write_text(content, encoding='utf-8')
    assert host.main(['import-inventory', '--input', str(source)]) == 2
    assert host.inventory_for_state({'shows': []}, NOW)['errors']


def test_non_object_saved_inventory_fails_closed():
    host.save_json(paths.data_home() / 'scheduler' / 'inventory.json', [])
    assert host.inventory_for_state({'shows': []}, NOW)['errors']


def test_stale_inventory_blocks_finalization():
    host.import_inventory(inventory(), NOW)
    assert host.inventory_for_state({'shows': []}, NOW + timedelta(minutes=3))['errors']


def test_confirmed_empty_inventory_is_usable():
    host.import_inventory(inventory([page([])]), NOW)
    assert host.inventory_for_state({'shows': []}, NOW) == {'automations': [], 'errors': []}


def test_bridge_does_not_modify_tasks_and_roundtrips_unicode():
    original = task()
    snapshot = host.task_snapshot(observed(original), NOW)
    config = tomllib.loads(host.binding_toml(snapshot))
    assert config['prompt'] == original['prompt']
    assert config['id'] == original['id']
    assert config['status'] == 'ACTIVE'
    assert snapshot['rrule'] == 'RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=22;BYMINUTE=0'
    assert original == task()


@pytest.mark.parametrize('clock', ['22:00', '22:00:00', '22:00:00.000'])
def test_native_weekly_time_normalization(clock):
    snapshot = host.task_snapshot(observed(task(time=clock)), NOW)
    assert snapshot['retry_supported'] is True
    assert snapshot['rrule'] == 'RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=22;BYMINUTE=0'


@pytest.mark.parametrize('clock', ['22:00:01.000', '22:00:00.001'])
def test_second_precision_schedule_not_silently_rounded(clock):
    assert host.task_snapshot(observed(task(time=clock)), NOW)['retry_supported'] is False


@pytest.mark.parametrize('patch', [{'weekdays': [1, 3]}, {'timeZone': 'Europe/Berlin'},
    {'kind': 'cron', 'expression': '* * * * *'}, {'kind': 'at'}, {'weekdays': [True]}])
def test_other_schedule_kinds_not_forced_into_retry(patch):
    assert host.task_snapshot(observed(task(**patch)), NOW)['retry_supported'] is False


def test_dsh_rrule_is_normalized_without_losing_raw_rule():
    rule = 'DTSTART;TZID=Asia/Shanghai:20261107T220000\nRRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=22;BYMINUTE=0'
    snapshot = host.task_snapshot(observed(task(kind='rrule', rrule=rule)), NOW)
    assert snapshot['retry_supported']
    assert snapshot['rrule'] == rule.splitlines()[1]
    assert snapshot['raw_task']['rrule'] == rule


def retry_case(now):
    from scheduled_watch import plan_retry
    snapshot = host.task_snapshot({'observed_at': now.isoformat(), 'task': task()}, now)
    plan = plan_retry({'automation_id': snapshot['id'], 'scope_hash': snapshot['scope_hash'],
                       'regular_rrule': snapshot['rrule'], 'timezone': 'Asia/Shanghai',
                       'window_start': '2026-11-07T22:00:00+08:00', 'now': now.isoformat(),
                       'attempt': 0, 'outcome': 'not_updated'})
    return snapshot, plan


def test_retry_emits_full_rule_and_revision_guard():
    now = NOW + timedelta(hours=2)
    snapshot, plan = retry_case(now)
    result = host.retry_edit(plan, snapshot, dict(plan), now)
    args = result['arguments']
    assert args['id'] == snapshot['id']
    assert args['expectedUpdatedAt'] == task()['updatedAt']
    assert args['rrule'].startswith('DTSTART;TZID=Asia/Shanghai:20261108T020000\nRRULE:')
    assert 'prompt' not in args and 'target' not in args and 'active' not in args


@pytest.mark.parametrize('change', ['revision', 'scope', 'paused', 'stale', 'intent'])
def test_retry_rejects_unsafe_updates(change):
    now = NOW + timedelta(hours=2)
    snapshot, plan = retry_case(now)
    saved = dict(plan)
    if change == 'revision':
        snapshot['raw_task'].pop('updatedAt')
    elif change == 'scope':
        snapshot['prompt'] += 'changed'
    elif change == 'paused':
        snapshot['status'] = 'PAUSED'
    elif change == 'stale':
        snapshot['observed_at'] = NOW.isoformat()
    else:
        saved['attempt'] = 2
    with pytest.raises(ValueError):
        host.retry_edit(plan, snapshot, saved, now)


def test_cli_from_foreign_directory_is_read_only(tmp_path, monkeypatch):
    result = subprocess.run([sys.executable, str(SCRIPTS / 'dsh_doctor.py')], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10)
    report = json.loads(result.stdout)
    assert report['read_only'] is True
    assert not paths.data_home().exists()
    assert 'password' not in result.stdout.casefold()
    result = subprocess.run([sys.executable, str(SCRIPTS / 'watch.py'), 'inspect', 'No such fixture'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    report = json.loads(result.stdout)
    assert report['status'] == 'workflow_error' and report['error'] == 'not_tracked'
    assert not paths.state_path().exists()


def test_core_uses_dsh_inventory_not_codex(tmp_path):
    from watch_v3.automation import local_inventory
    result = local_inventory({'shows': []})
    assert result['errors']
    assert result['errors'][0]['error'] == 'dsh_scheduler_inventory_unavailable'


def test_default_client_paths_are_portable(monkeypatch):
    import qbittorrent_submit as qb
    assert 'C:\\User_data' not in str(qb.DEFAULT_SAVE_PATH)
    assert qb.DEFAULT_SAVE_PATH.is_absolute()


@pytest.mark.parametrize('remote', ['/srv/media/anime', 'D:/Anime/Series', r'\\server\media\anime'])
def test_remote_save_path_survives_cli_and_wire_encoding(remote):
    import argparse
    from urllib.parse import parse_qs
    from watch_v3.cli import client_args, client
    from watch_v3.clients import DeliveryRequest
    parser = argparse.ArgumentParser()
    client_args(parser)
    args = parser.parse_args(['--client', 'webapi', '--qbittorrent-save-path', remote])
    assert args.qbittorrent_save_path == remote
    request = DeliveryRequest('fixture', 'operation', '0' * 40, 'magnet:?xt=urn:btih:' + '0' * 40,
                              save_path=args.qbittorrent_save_path)
    body, content_type = client(args)._add_payload(request)
    assert content_type == 'application/x-www-form-urlencoded'
    assert parse_qs(body.decode())['savepath'] == [remote]
    assert request.saved_request()['save_path'] == remote


def test_unchanged_release_engine_hashes():
    manifest = json.loads((ROOT / 'UPSTREAM.json').read_text())
    changed = set(manifest['adapted_files']) | set(manifest['added_files'])
    for row in manifest['source_files']:
        if row['path'].startswith('scripts/') and row['path'] not in changed:
            assert host.hashlib.sha256((SCRIPTS.parent / row['path']).read_bytes()).hexdigest() == row['sha256']
