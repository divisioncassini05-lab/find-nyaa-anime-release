#!/usr/bin/env python3
"""Read-only local prerequisites. Never launch a client or contact the network."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dsh_paths import data_home, state_path, download_directory


def diagnose():
    missing = []
    if sys.version_info < (3, 11):
        missing.append('python_3_11_required')
    try:
        ZoneInfo('Asia/Shanghai')
        timezone = True
    except ZoneInfoNotFoundError:
        timezone = False
        missing.append('timezone_data_missing_install_tzdata_for_schedules')
    qb = os.environ.get('QBITTORRENT_EXE') or shutil.which('qbittorrent') or shutil.which('qbittorrent.exe')
    return {
        'status': 'ready' if not missing else 'missing_dependency',
        'read_only': True,
        'python': sys.version.split()[0],
        'platform': sys.platform,
        'data_directory': str(data_home()),
        'state_path': str(state_path()),
        'default_download_directory': str(download_directory()),
        'timezone_data': timezone,
        'qb_executable_found': bool(qb and Path(qb).is_file()),
        'qb_webapi_credentials_configured': bool(os.environ.get('QBITTORRENT_USERNAME')),
        'scheduler': 'Inspect DSH schedule_create/list/view/edit tools in the active preset.',
        'missing': missing,
        'note': 'Not a network, GUI, scheduler or qBittorrent acceptance test. Nothing was installed or changed.',
    }


if __name__ == '__main__':
    try:
        result = diagnose()
    except ValueError as exc:
        result = {'status': 'invalid_configuration', 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'ready' else 2)
