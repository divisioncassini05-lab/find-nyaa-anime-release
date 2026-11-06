#!/usr/bin/env python3
"""Verify the npm payload and archive only declared source/build inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_sets():
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'UPSTREAM.json').read_text(encoding='utf-8'))
    skill_files = {item['path'] for item in manifest['source_files']} | set(manifest['added_files'])
    runtime_skill = {path for path in skill_files if not path.startswith('tests/') and path != 'pytest.ini'}
    root_files = {path for path in package['files'] if (ROOT / path).is_file()} | {'package.json'}
    locales = {path.relative_to(ROOT).as_posix() for path in (ROOT / 'locale').glob('*.json')}
    assets = {path.relative_to(ROOT).as_posix() for path in (ROOT / 'assets').rglob('*') if path.is_file()}
    prefix = 'skills/find-nyaa-anime-release/'
    runtime = root_files | locales | assets | {prefix + path for path in runtime_skill}
    source = runtime | {prefix + path for path in skill_files} | {'.gitignore', '.npmignore', 'skills/.npmignore'}
    source.update(path.relative_to(ROOT).as_posix() for path in (ROOT / 'tools').glob('*.py'))
    source.update(path.relative_to(ROOT).as_posix() for path in (ROOT / 'tests').glob('*')
                  if path.is_file() and path.suffix in {'.py', '.mjs'})
    source.update('overlays/' + path for path in manifest['added_files'])
    for name in source:
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or ROOT not in path.resolve().parents:
            raise ValueError('Missing or unsafe build input: ' + name)
    return package, runtime, source


def build(tarball, output):
    package, expected, source = file_sets()
    actual = set()
    with tarfile.open(tarball, 'r:gz') as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or len(parts) < 2 or parts[0] != 'package' or '..' in parts:
                raise ValueError('Unsafe tar member: ' + member.name)
            name = PurePosixPath(*parts[1:]).as_posix()
            if name not in expected or name in actual:
                raise ValueError('Unexpected or duplicate runtime file: ' + name)
            content = archive.extractfile(member).read()
            if content != (ROOT / name).read_bytes():
                raise ValueError('Packed file differs from source: ' + name)
            if name.endswith('.py'):
                compile(content, name, 'exec')
            actual.add(name)
    if actual != expected:
        raise ValueError('Runtime files missing: ' + ', '.join(sorted(expected - actual)))
    output.mkdir(parents=True, exist_ok=True)
    destination = output / tarball.name
    if destination.resolve() != tarball.resolve():
        shutil.copyfile(tarball, destination)
    zip_path = output / f"{package['name']}-{package['version']}-source.zip"
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(source):
            archive.write(ROOT / name, package['name'] + '/' + name)
    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(source):
            raise ValueError('Source archive verification failed')
    checksums = '\n'.join(f'{digest(path)}  {path.name}' for path in (destination, zip_path)) + '\n'
    (output / 'SHA256SUMS.txt').write_text(checksums, encoding='ascii')
    print(json.dumps({'status': 'verified', 'runtime_files': len(actual), 'source_files': len(source),
                      'tarball': str(destination), 'source_zip': str(zip_path),
                      'sha256': {path.name: digest(path) for path in (destination, zip_path)}}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tarball', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    build(args.tarball, args.output_dir)
