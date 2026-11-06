"""DSH-owned data paths, independent of plugin location and Codex state."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def absolute_setting(name, default):
    value = Path(os.environ.get(name, str(default))).expanduser()
    if not value.is_absolute():
        raise ValueError(name + ' must be an absolute path')
    return value


def data_home():
    home = Path.home()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local')) / 'DSH' / 'AnimeRelease'
    elif sys.platform == 'darwin':
        base = home / 'Library' / 'Application Support' / 'DSH' / 'AnimeRelease'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', home / '.local' / 'share')) / 'dsh' / 'anime-release'
    return absolute_setting('ANIME_DSH_HOME', base)


def state_path():
    # Deliberately do not inherit ANIME_TRACKING_STATE from a Codex installation.
    return data_home() / 'airing_watch_state.json'


def download_directory():
    return absolute_setting('ANIME_DSH_DOWNLOAD_DIR', Path.home() / 'Downloads' / 'Anime')


def qb_backup_directory():
    home = Path.home()
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', home / 'AppData' / 'Local')) / 'qBittorrent' / 'BT_backup'
    elif sys.platform == 'darwin':
        base = home / 'Library' / 'Application Support' / 'qBittorrent' / 'BT_backup'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', home / '.local' / 'share')) / 'qBittorrent' / 'BT_backup'
    return absolute_setting('ANIME_DSH_QB_BACKUP_DIR', base)
