"""Host-scoped setup preferences; credentials never enter reports or argv."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from anime_release.storage import atomic_json, file_lock
from watch_v3.bangumi_client import BangumiClient, BangumiError, connect, load_config


def settings_path(state):
    path = Path(state)
    return path.with_name(path.stem + '.setup.json')


def load_settings(state):
    path = settings_path(state)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('invalid_setup_settings')
    return data


def save_settings(state, *, executable='', download_directory=''):
    fields = {}
    for key, value, directory in [('qbittorrent_exe', executable, False),
                                  ('download_directory', download_directory, True)]:
        if not str(value).strip():
            continue
        path = Path(value).expanduser()
        if not path.is_absolute() or not (path.is_dir() if directory else path.is_file()):
            raise ValueError('invalid_' + key)
        fields[key] = str(path.resolve())
    value = {**load_settings(state), 'version': 1, 'completed': True, **fields}
    atomic_json(settings_path(state), value)
    return {'status': 'setup_saved'}


def setup_status(state):
    settings = load_settings(state)
    account = load_config(state)
    return {'status': 'setup_complete' if settings.get('completed') else 'setup_required',
            'bangumi_connected': bool(account),
            'bangumi_username': account.get('username') if account else None,
            'qbittorrent_configured': bool(settings.get('qbittorrent_exe') or settings.get('web_url')),
            'download_directory_configured': bool(settings.get('download_directory'))}


def credential_directory():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    path = base / 'AnimeRelease' / 'credentials'
    path.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        path.chmod(0o700)
    return path


def connect_token(state, token, *, factory=BangumiClient):
    token = token.strip()
    if not token or any(c.isspace() for c in token):
        raise BangumiError('bangumi_token_required')
    # Unique private files allow failed validation to leave old credentials intact.
    fd, name = tempfile.mkstemp(prefix='bangumi-', suffix='.token', dir=credential_directory())
    path = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(token)
        with file_lock(settings_path(state).with_suffix('.setup.lock')):
            connect(state, token_file=path, factory=factory)
        return {'status': 'bangumi_connected'}
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def desktop_defaults(args, state):
    """Explicit CLI values win; remote Web API paths are never replaced."""
    if args.client != 'desktop':
        return
    settings = load_settings(state)
    if args.qbittorrent_exe is None and settings.get('qbittorrent_exe'):
        args.qbittorrent_exe = Path(settings['qbittorrent_exe'])
    if args.qbittorrent_save_path is None and settings.get('download_directory'):
        args.qbittorrent_save_path = Path(settings['download_directory'])


def client_defaults(args, state):
    """Resolve private Web API settings without copying credentials into argv."""
    settings = load_settings(state)
    if args.client is None:
        args.client = settings.get('client') or ('webapi' if settings.get('web_url') else 'desktop')
    if args.client not in {'desktop', 'webapi'}:
        raise ValueError('invalid_client_settings')
    desktop_defaults(args, state)
    return {
        'url': args.qb_url or settings.get('web_url') or 'http://127.0.0.1:8080',
        'username': os.environ.get(args.qb_username_env, settings.get('web_username')),
        'password': os.environ.get(args.qb_password_env, settings.get('web_password')),
    }
