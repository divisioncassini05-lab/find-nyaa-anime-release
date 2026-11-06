#!/usr/bin/env python3
"""Preview/apply lossless v1 -> v2 migration; never deduplicate records."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from anime_release.schema import adapt, encode, PROGRESS
from anime_release.storage import file_lock, read_json, atomic_json
from runtime_paths import DEFAULT_STATE

def migrate(path, apply=False, expected_sha256=None):
    path = Path(path)
    # Preview is genuinely read-only, including no lock file creation.
    if not apply:
        before = path.read_bytes()
        raw = read_json(path)
        converted = encode(raw)
        old, new = adapt(raw), adapt(converted)
        return {'status': 'preview', 'version_before': raw.get('version', 1), 'version_after': 2,
                'sha256': hashlib.sha256(before).hexdigest(), 'records': len(new['shows']),
                'progress_preserved': [{k: s.get(k) for k in PROGRESS} for s in old['shows']] ==
                                      [{k: s.get(k) for k in PROGRESS} for s in new['shows']],
                'track_ids': [s['track_id'] for s in new['shows']], 'deduplicated': 0}
    if not expected_sha256:
        raise ValueError('Apply requires --expected-sha256 from a fresh preview')
    with file_lock(path.with_suffix(path.suffix + '.lock')):
        before = path.read_bytes()
        if hashlib.sha256(before).hexdigest() != expected_sha256:
            raise ValueError('State changed since preview; stop and preview again')
        raw = read_json(path)
        if raw.get('version') == 2:
            return {'status': 'already_v2', 'records': len(raw['shows'])}
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = path.with_name(path.name + '.v1-' + stamp + '.bak')
        # No overwrites of earlier backups.
        with backup.open('xb') as stream:
            stream.write(before)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        converted = encode(raw)
        assert len(converted['shows']) == len(raw['shows'])
        if [{k: s.get(k) for k in PROGRESS} for s in adapt(raw)['shows']] != [{k: s.get(k) for k in PROGRESS} for s in adapt(converted)['shows']]:
            raise ValueError('Progress preservation validation failed')
        atomic_json(path, converted)
        return {'status': 'migrated', 'records': len(converted['shows']), 'backup': str(backup),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, default=DEFAULT_STATE)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--preview', action='store_true')
    p.add_argument('--expected-sha256')
    args = p.parse_args(argv)
    print(json.dumps(migrate(args.state, args.apply, args.expected_sha256), ensure_ascii=False))

if __name__ == '__main__':
    main()
