import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import local_setup as setup
import setup_gui
import first_use
from watch_v3.bangumi_client import BangumiError, config_path, credentials, load_config


@pytest.fixture
def state(tmp_path, monkeypatch):
    secret_dir = tmp_path / 'private'
    secret_dir.mkdir()
    monkeypatch.setattr(setup, 'credential_directory', lambda: secret_dir)
    return tmp_path / 'host' / 'state.json'


def account(token):
    assert token == 'test-secret'
    return SimpleNamespace(me=lambda: {'id': 123, 'username': 'tester'})


def test_first_use_is_text_only_and_windows_are_explicit(state, monkeypatch, capsys):
    launch = Mock(return_value={'status': 'setup_opened'})
    monkeypatch.setattr(setup_gui, 'launch', launch)
    assert first_use.main(['--state', str(state)]) == 0
    launch.assert_not_called()
    setup_gui.main(['--state', str(state), '--section', 'bangumi'])
    launch.assert_called_once_with(state, 'bangumi')
    launch.reset_mock()
    setup_gui.main(['--state', str(state), '--section', 'qbittorrent'])
    launch.assert_called_once_with(state, 'qbittorrent')
    assert '首次使用提示' in capsys.readouterr().out
    assert not state.exists()


def test_fixed_guidance_omits_configured_bangumi_without_network(state, monkeypatch):
    setup.connect_token(state, 'test-secret', factory=account)
    monkeypatch.setattr(first_use.shutil, 'which', lambda _: None)
    monkeypatch.delenv('QBITTORRENT_EXE', raising=False)
    monkeypatch.delenv('QBITTORRENT_USERNAME', raising=False)
    report = first_use.guidance(state)
    assert report['bangumi'] == 'configured_unverified'
    assert '创建 Access Token' not in report['reply_text']
    assert '不代表没有安装' in report['reply_text']
    assert 'test-secret' not in json.dumps(report)


def test_tutorial_can_be_requested_when_configured(state, monkeypatch, tmp_path):
    setup.connect_token(state, 'test-secret', factory=account)
    exe = tmp_path / 'qb.exe'
    exe.touch()
    setup.save_settings(state, executable=str(exe))
    before = setup.settings_path(state).read_bytes()
    assert first_use.guidance(state)['reply_text'] == ''
    result = first_use.guidance(state, include_guide=True)
    assert result['status'] == 'usage_guide'
    assert '可以这样说' in result['reply_text']
    assert '只要磁力，不下载' in result['reply_text']
    assert '仅返回链接不推进' in result['reply_text']
    assert '创建 Access Token' not in result['reply_text']
    assert setup.settings_path(state).read_bytes() == before
    assert not state.exists()


def test_guidance_recognizes_saved_remote_client_without_network(state, monkeypatch):
    setup.connect_token(state, 'test-secret', factory=account)
    setup.atomic_json(setup.settings_path(state), {'version': 1, 'client': 'webapi',
        'web_url': 'http://localhost:8090', 'web_username': 'test-user',
        'web_password': 'fixture-secret', 'download_directory': '/remote/anime'})
    monkeypatch.delenv('QBITTORRENT_USERNAME', raising=False)
    monkeypatch.delenv('QBITTORRENT_PASSWORD', raising=False)
    monkeypatch.setattr(first_use.shutil, 'which', lambda _: None)
    before = setup.settings_path(state).read_bytes()
    report = first_use.guidance(state)
    assert report['status'] == 'configured_unverified'
    assert report['reply_text'] == ''
    assert 'fixture-secret' not in json.dumps(report)
    assert setup.settings_path(state).read_bytes() == before
    monkeypatch.setenv('QBITTORRENT_PASSWORD', '')
    assert first_use.guidance(state)['status'] == 'setup_guidance'


def test_token_private_not_in_reports_or_settings(state):
    result = setup.connect_token(state, 'test-secret', factory=account)
    setup.save_settings(state)
    config = load_config(state)
    assert credentials(config) == 'test-secret'
    assert Path(config['token_file']).parent == state.parent.parent / 'private'
    public = json.dumps([result, setup.setup_status(state)]) + config_path(state).read_text() + setup.settings_path(state).read_text()
    assert 'test-secret' not in public
    assert not state.exists()


def test_failed_token_or_account_change_preserves_old_config(state):
    setup.connect_token(state, 'test-secret', factory=account)
    before = config_path(state).read_bytes()
    old_files = list((state.parent.parent / 'private').iterdir())
    def reject(_):
        raise BangumiError('bangumi_http_401')
    for factory in [reject, lambda _: SimpleNamespace(me=lambda: {'id': 456, 'username': 'other'})]:
        with pytest.raises(BangumiError):
            setup.connect_token(state, 'new-secret', factory=factory)
        assert config_path(state).read_bytes() == before
        assert list((state.parent.parent / 'private').iterdir()) == old_files


def test_host_state_isolation(state):
    setup.save_settings(state)
    setup.connect_token(state, 'test-secret', factory=account)
    other = state.parent / 'other.json'
    assert setup.setup_status(other)['status'] == 'setup_required'
    assert not setup.setup_status(other)['bangumi_connected']


def test_paths_validate_without_overwriting(state, tmp_path):
    setup.save_settings(state)
    before = setup.settings_path(state).read_bytes()
    with pytest.raises(ValueError):
        setup.save_settings(state, executable=str(tmp_path / 'missing.exe'))
    assert setup.settings_path(state).read_bytes() == before


def test_saved_paths_used_cli_wins_webapi_unchanged(state, tmp_path):
    exe = tmp_path / 'qb.exe'
    exe.touch()
    setup.save_settings(state, executable=str(exe), download_directory=str(tmp_path))
    args = SimpleNamespace(client='desktop', qbittorrent_exe=None, qbittorrent_save_path=None)
    setup.desktop_defaults(args, state)
    assert args.qbittorrent_exe == exe
    assert args.qbittorrent_save_path == tmp_path
    args.qbittorrent_save_path = Path('explicit')
    setup.desktop_defaults(args, state)
    assert args.qbittorrent_save_path == Path('explicit')
    remote = SimpleNamespace(client='webapi', qbittorrent_exe=None, qbittorrent_save_path='/remote/path')
    setup.desktop_defaults(remote, state)
    assert remote.qbittorrent_exe is None and remote.qbittorrent_save_path == '/remote/path'


def test_launch_failure_does_not_claim_open(state, monkeypatch, capsys):
    monkeypatch.setattr(setup_gui, 'launch', lambda *_: {'status': 'gui_unavailable'})
    assert setup_gui.main(['--state', str(state)]) == 1
    assert 'setup_opened' not in capsys.readouterr().out
    assert not setup.settings_path(state).exists()


def test_web_config_used_without_exposing_password_in_args(state, monkeypatch):
    setup.atomic_json(setup.settings_path(state), {'version': 1, 'client': 'webapi',
        'web_url': 'http://localhost:8090', 'web_username': 'test-user', 'web_password': 'fixture-secret'})
    monkeypatch.delenv('QBITTORRENT_USERNAME', raising=False)
    monkeypatch.delenv('QBITTORRENT_PASSWORD', raising=False)
    args = SimpleNamespace(client=None, qb_url=None, qb_username_env='QBITTORRENT_USERNAME',
                           qb_password_env='QBITTORRENT_PASSWORD')
    result = setup.client_defaults(args, state)
    assert args.client == 'webapi'
    assert result == {'url': 'http://localhost:8090', 'username': 'test-user', 'password': 'fixture-secret'}
    assert 'fixture-secret' not in repr(args)
    monkeypatch.setenv('QBITTORRENT_PASSWORD', 'override-secret')
    args.qb_url = 'http://localhost:9000'
    result = setup.client_defaults(args, state)
    assert result['url'] == args.qb_url and result['password'] == 'override-secret'
    setup.save_settings(state)
    assert setup.load_settings(state)['web_password'] == 'fixture-secret'


def test_web_download_directory_default_and_explicit_override(state):
    from urllib.parse import parse_qs
    from watch_v3.cli import parser, client
    from watch_v3.clients import DeliveryRequest
    setup.atomic_json(setup.settings_path(state), {'version': 1, 'client': 'webapi',
        'web_url': 'http://localhost:8090', 'download_directory': '/remote/anime'})
    args = parser().parse_args(['--state', str(state), 'recover', '--operation', 'fixture'])
    configured = client(args)
    request = DeliveryRequest('track', 'operation', 'a' * 40, 'magnet:fixture')
    body, _ = configured._add_payload(request)
    assert parse_qs(body.decode())['savepath'] == ['/remote/anime']
    request = DeliveryRequest('track', 'operation', 'a' * 40, 'magnet:fixture', '/explicit/anime')
    body, _ = configured._add_payload(request)
    assert parse_qs(body.decode())['savepath'] == ['/explicit/anime']
