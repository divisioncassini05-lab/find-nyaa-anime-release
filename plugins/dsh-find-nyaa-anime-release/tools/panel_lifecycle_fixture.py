"""Offline Python half of the panel lifecycle audit; all data is synthetic."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/find-nyaa-anime-release/scripts'))
import dsh_panel_run as panel


def read(file):
    return json.loads(file.read_text(encoding='utf-8'))


def write(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value), encoding='utf-8')


def bencode(value):
    if isinstance(value, int):
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, list):
        return b'l' + b''.join(map(bencode, value)) + b'e'
    return b'd' + b''.join(bencode(k) + bencode(v) for k, v in sorted(value.items())) + b'e'


def main():
    root = Path(sys.argv[1]).resolve()
    assert (root / 'SYNTHETIC-AUDIT').is_file(), 'Isolated fixture marker required'
    action, plan_id = sys.argv[2:4]
    episode = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    state = root / 'state.json'
    cloud_file = root / 'fake-cloud.json'
    plan = next(p for p in read(state.with_suffix('.plans.json'))['plans'] if p['id'] == plan_id)
    backup = root / 'qb-backup'
    backup.mkdir(exist_ok=True)
    download = root / 'downloads'
    download.mkdir(exist_ok=True)
    name = f'Atlas-{episode:02d}.mkv'.encode()
    info = {b'name': name, b'length': 4, b'piece length': 4, b'pieces': hashlib.sha1(b'test').digest()}
    info_hash = hashlib.sha1(bencode(info)).hexdigest()

    class FakeCloud:
        def subject(self, subject_id):
            return {'id': subject_id, 'type': 2}

        def collection(self, username, subject_id):
            return {'type': read(cloud_file)['type']}

        def set_collection(self, subject_id, kind):
            cloud = read(cloud_file)
            if cloud.get('offline'):
                raise OSError('fake offline')
            cloud['type'] = kind
            cloud['writes'].append({'source': 'execution', 'type': kind})
            write(cloud_file, cloud)

    def fake_search(_args):
        # The audit starts at the already-reviewed result boundary. It does not
        # pretend to test Nyaa retrieval or model title/quality judgement.
        if action in {'find', 'finale', 'package'}:
            if action == 'package':
                panel.record_found({'status': 'found', 'eligibility': 'passed', 'info_hash': info_hash,
                    'scope': {'kind': 'season', 'title': plan['title'], 'season': plan['season'], 'bangumi_id': 123}})
            else:
                show = {'track_id': plan['trackId'], 'identity': {'provider_bindings': {'bangumi': {'entry_id': 123}}},
                        'broadcast': {'completion': {'confirmed': action == 'finale', 'final_episode': episode}}, 'operations': {}}
                write(state, {'shows': [show]})
                panel.record_found({'status': 'found', 'eligibility': 'passed', 'target_episode': episode,
                    'info_hash': info_hash, 'selected': {'url': 'https://nyaa.si/view/123'}}, show=show)
        return 0

    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden in audit')), \
         patch.object(panel, 'qb_backup_directory', return_value=backup), \
         patch('watch_v3.bangumi_client.load_config', return_value={'username': 'fake'}), \
         patch('watch_v3.bangumi_client.configured_client', return_value=FakeCloud()), \
         patch('watch_v3.cli.run', side_effect=fake_search), \
         patch('package_release.main', side_effect=fake_search):
        if action in {'execute', 'find', 'finale', 'package'}:
            with contextlib.redirect_stdout(io.StringIO()):
                panel.main(['--state', str(state), '--plan-id', plan_id,
                            'package' if action == 'package' else 'watch', 'get'])
        elif action in {'partial', 'download'}:
            (backup / (info_hash + '.torrent')).write_bytes(bencode({b'info': info}))
            (backup / (info_hash + '.fastresume')).write_bytes(bencode({
                b'info-hash': bytes.fromhex(info_hash), b'completed_time': 100 if action == 'download' else 0}))
            (download / name.decode()).write_bytes(b'test')
        elif action != 'snapshot':
            raise ValueError('Unknown fixture action')
        print(json.dumps(panel.snapshot(state)))


if __name__ == '__main__':
    main()
