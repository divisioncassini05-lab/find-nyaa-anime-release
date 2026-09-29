import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import client_context
import qbittorrent_submit as qbt


def test_sandbox_identity_fails_closed_before_client_launch():
    with patch.object(client_context, 'windows_identity', return_value={
        'account': 'id-paths\\codexsandboxoffline', 'restricted_token': False,
    }):
        report = client_context.inspect_context()
    assert report['status'] == 'client_context_required'
    assert report['client_attempted'] is False
    assert report['submission_attempts'] == 0


def test_submit_preflight_runs_before_profile_lock_or_launch(tmp_path):
    with patch.object(qbt, 'require_client_context', side_effect=qbt.SubmissionError(
            'wrong context', code='client_context_required', retryable=False)):
        try:
            qbt.submit_magnet(
                'magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567',
                executable=tmp_path / 'qbittorrent.exe', backup_dir=tmp_path / 'BT_backup',
                save_path=tmp_path / 'downloads')
        except qbt.SubmissionError as exc:
            assert exc.code == 'client_context_required'
            assert exc.diagnostics.get('info_hash') == '0123456789abcdef0123456789abcdef01234567'
        else:
            raise AssertionError('context guard did not fail closed')
