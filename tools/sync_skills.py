#!/usr/bin/env python3
"""Synchronize the DSH payload from the public canonical skill, or verify drift."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'dsh-find-nyaa-anime-release'
CORE = ROOT / 'skills' / 'find-nyaa-anime-release'
SKILL = Path('skills/find-nyaa-anime-release')
IGNORED = {'__pycache__', '.pytest_cache', '.hypothesis', '.git'}


def payload_files(root):
    files = {'UPSTREAM.json'} if (root / 'UPSTREAM.json').is_file() else set()
    for path in (root / SKILL).rglob('*'):
        if any(part in IGNORED for part in path.parts) or path.suffix in {'.pyc', '.pyo'}:
            continue
        if path.is_symlink():
            raise ValueError('Generated payload must not contain symlinks: ' + str(path))
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    return files


def differences(expected, current):
    wanted, actual = payload_files(expected), payload_files(current)
    return {'added': sorted(wanted - actual), 'removed': sorted(actual - wanted),
            'changed': sorted(name for name in wanted & actual
                              if (expected / name).read_bytes() != (current / name).read_bytes())}


def tracked_payload(root):
    path = root / 'UPSTREAM.json'
    if not path.is_file():
        return set()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    names = {item['path'] for item in manifest['source_files']} | set(manifest['added_files'])
    for name in names:
        parts = PurePosixPath(name).parts
        if not parts or '..' in parts or '\\' in name or PurePosixPath(name).is_absolute():
            raise ValueError('Unsafe source manifest path')
    return {'UPSTREAM.json'} | {(SKILL / name).as_posix() for name in names}


def apply_snapshot(expected, current, delta):
    unknown = set(delta['removed']) - tracked_payload(current)
    if unknown:
        raise ValueError('Unmanaged files in generated payload; review before publishing: ' + ', '.join(sorted(unknown)))
    destinations = {}
    for name in delta['added'] + delta['changed'] + delta['removed']:
        destination = (current / name).resolve()
        if current.resolve() not in destination.parents or (current / name).is_symlink():
            raise ValueError('Unsafe generated target: ' + name)
        destinations[name] = destination
    for name in delta['added'] + delta['changed']:
        destination = destinations[name]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(expected / name, destination)
    for name in delta['removed']:
        destinations[name].unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only reproducibility check')
    parser.add_argument('--bump', choices=['patch'], help='Bump DSH patch version when the generated payload changes')
    args = parser.parse_args(argv)
    if args.check and args.bump:
        parser.error('--check cannot change a version')
    spec = importlib.util.spec_from_file_location('dsh_skill_builder', PLUGIN / 'tools' / 'sync_skill.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='dsh-skill-sync-') as temporary:
        expected = Path(temporary)
        builder.rebuild(CORE, expected, emit=False)
        delta = differences(expected, PLUGIN)
        changed = any(delta.values())
        if not args.check and changed:
            apply_snapshot(expected, PLUGIN, delta)
            if args.bump:
                package_path = PLUGIN / 'package.json'
                package = json.loads(package_path.read_text(encoding='utf-8'))
                match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', package['version'])
                if not match:
                    raise ValueError('Review prerelease version manually')
                package['version'] = f'{match[1]}.{match[2]}.{int(match[3]) + 1}'
                package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(json.dumps({'status': 'out_of_sync' if changed and args.check else 'synchronized',
                          'changed': changed, 'files': delta}, ensure_ascii=False, indent=2))
        return int(args.check and changed)


if __name__ == '__main__':
    raise SystemExit(main())
