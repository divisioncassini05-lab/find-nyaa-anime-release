from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import qbittorrent_submit as qbt


INFO_HASH = "0123456789abcdef0123456789abcdef01234567"
MAGNET = f"magnet:?xt=urn:btih:{INFO_HASH}&dn=fixture"


class QbittorrentSubmitTests(unittest.TestCase):
    def test_extracts_hex_and_base32_btih(self) -> None:
        self.assertEqual(qbt.extract_btih(MAGNET), INFO_HASH)
        encoded = base64.b32encode(bytes.fromhex(INFO_HASH)).decode("ascii")
        self.assertEqual(
            qbt.extract_btih(f"magnet:?xt=urn:btih:{encoded}"),
            INFO_HASH,
        )

    def test_rejects_non_magnet_input(self) -> None:
        with self.assertRaises(qbt.SubmissionError):
            qbt.extract_btih("https://example.test/file.torrent")

    def test_dry_run_builds_silent_running_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            report = qbt.submit_magnet(
                MAGNET,
                executable=executable,
                save_path=root / "downloads",
                backup_dir=root / "backup",
                dry_run=True,
            )

        self.assertEqual(report["status"], "dry_run")
        self.assertIn("--skip-dialog=true", report["command"])
        self.assertIn("--add-stopped=false", report["command"])
        self.assertEqual(report["command"][-1], "<magnet>")

    def test_existing_fastresume_is_not_resubmitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            (backup / f"{INFO_HASH}.fastresume").touch()
            with patch.object(qbt.subprocess, "Popen") as popen:
                report = qbt.submit_magnet(
                    MAGNET,
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=backup,
                )

        self.assertEqual(report["status"], "already_present")
        popen.assert_not_called()

    def test_zero_exit_is_an_accepted_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            process = Mock()
            process.poll.return_value = 0
            with patch.object(qbt.subprocess, "Popen", return_value=process):
                report = qbt.submit_magnet(
                    MAGNET,
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=root / "backup",
                    wait_seconds=0,
                )

        self.assertEqual(report["status"], "submitted")
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
