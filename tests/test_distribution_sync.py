import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('distribution_sync', ROOT / 'tools' / 'sync_skills.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def tree(root, entries):
    root.mkdir(parents=True)
    for name, value in entries.items():
        path = root / sync.SKILL / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
    (root / 'UPSTREAM.json').write_text(json.dumps({'source_files': [{'path': name} for name in entries],
                                                  'added_files': []}), encoding='utf-8')
    return root


def test_diff_does_not_write_and_ignores_bytecode(tmp_path):
    expected = tree(tmp_path / 'expected', {'scripts/a.py': 'new'})
    current = tree(tmp_path / 'current', {'scripts/a.py': 'old'})
    cache = current / sync.SKILL / 'scripts/__pycache__/a.pyc'
    cache.parent.mkdir()
    cache.write_bytes(b'cache')
    delta = sync.differences(expected, current)
    assert delta['changed'] == [(sync.SKILL / 'scripts/a.py').as_posix()]
    assert not delta['removed']
    assert (current / sync.SKILL / 'scripts/a.py').read_text() == 'old'


def test_removed_managed_file_is_deleted(tmp_path):
    expected = tree(tmp_path / 'expected', {'scripts/new.py': 'new'})
    current = tree(tmp_path / 'current', {'scripts/old.py': 'old'})
    sync.apply_snapshot(expected, current, sync.differences(expected, current))
    assert not (current / sync.SKILL / 'scripts/old.py').exists()
    assert not any(sync.differences(expected, current).values())


def test_unknown_files_stop_sync_before_any_write(tmp_path):
    expected = tree(tmp_path / 'expected', {'scripts/a.py': 'new'})
    current = tree(tmp_path / 'current', {'scripts/a.py': 'old'})
    unexpected = current / sync.SKILL / 'private-state.json'
    unexpected.write_text('{}')
    with pytest.raises(ValueError, match='Unmanaged'):
        sync.apply_snapshot(expected, current, sync.differences(expected, current))
    assert unexpected.is_file()
    assert (current / sync.SKILL / 'scripts/a.py').read_text() == 'old'


@pytest.mark.parametrize('unsafe', ['../outside', '/outside', 'scripts/../../outside'])
def test_manifest_cannot_authorize_outside_deletion(tmp_path, unsafe):
    (tmp_path / 'UPSTREAM.json').write_text(json.dumps({'source_files': [{'path': unsafe}], 'added_files': []}))
    with pytest.raises(ValueError, match='Unsafe'):
        sync.tracked_payload(tmp_path)


def test_published_distributions_are_in_sync():
    result = subprocess.run([sys.executable, str(ROOT / 'tools/sync_skills.py'), '--check'],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['changed'] is False
