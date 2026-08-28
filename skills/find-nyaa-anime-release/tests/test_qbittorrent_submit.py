from __future__ import annotations

import base64
import hashlib
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
INFO_DICT = b"d6:lengthi1e4:name7:fixturee"
TORRENT_DATA = b"d8:announce14:https://t.test4:info" + INFO_DICT + b"e"
TORRENT_HASH = hashlib.sha1(INFO_DICT).hexdigest()
TORRENT_MAGNET = f"magnet:?xt=urn:btih:{TORRENT_HASH}&dn=fixture"


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.data[:size] if size >= 0 else self.data


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

    def test_dry_run_can_target_an_isolated_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            profile = root / "profile"
            report = qbt.submit_magnet(
                MAGNET,
                executable=executable,
                save_path=root / "downloads",
                backup_dir=root / "backup",
                profile_path=profile,
                dry_run=True,
            )

        self.assertIn(f"--profile={profile}", report["command"])

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
            with (
                patch.object(
                    qbt,
                    "ensure_qbittorrent_ready",
                    return_value={"client_was_running": True, "client_started": False},
                ),
                patch.object(qbt.subprocess, "Popen", return_value=process),
            ):
                report = qbt.submit_magnet(
                    MAGNET,
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=root / "backup",
                    wait_seconds=0,
                )

        self.assertEqual(report["status"], "submitted")
        self.assertTrue(report["ok"])

    def test_nyaa_page_is_converted_to_torrent_download(self) -> None:
        self.assertEqual(
            qbt.nyaa_torrent_url("https://nyaa.si/view/2141829"),
            "https://nyaa.si/download/2141829.torrent",
        )

    def test_torrent_metadata_is_preferred_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            (backup / f"{TORRENT_HASH}.fastresume").touch()

            def accept_torrent(command: list[str], **_: object) -> Mock:
                submitted = Path(command[-1])
                self.assertEqual(submitted.suffix, ".torrent")
                self.assertEqual(submitted.read_bytes(), TORRENT_DATA)
                (backup / f"{TORRENT_HASH}.torrent").write_bytes(TORRENT_DATA)
                process = Mock()
                process.poll.return_value = 0
                return process

            with (
                patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)),
                patch.object(
                    qbt,
                    "ensure_qbittorrent_ready",
                    return_value={"client_was_running": True, "client_started": False},
                ),
                patch.object(qbt.subprocess, "Popen", side_effect=accept_torrent),
            ):
                report = qbt.submit_magnet(
                    TORRENT_MAGNET,
                    source_url="https://nyaa.si/view/2141829",
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=backup,
                )

        self.assertEqual(report["status"], "submitted_verified")
        self.assertEqual(report["verification"], "torrent_metadata_saved")
        self.assertEqual(report["submission_source"], "torrent")

    def test_waits_long_enough_for_delayed_qbittorrent_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            elapsed = 0.0

            process = Mock()
            process.poll.return_value = 0

            def monotonic() -> float:
                return elapsed

            def sleep(seconds: float) -> None:
                nonlocal elapsed
                elapsed += seconds
                if elapsed >= 9.0:
                    (backup / f"{TORRENT_HASH}.fastresume").touch()
                    (backup / f"{TORRENT_HASH}.torrent").write_bytes(TORRENT_DATA)

            with (
                patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)),
                patch.object(
                    qbt,
                    "ensure_qbittorrent_ready",
                    return_value={"client_was_running": True, "client_started": False},
                ),
                patch.object(qbt.subprocess, "Popen", return_value=process),
                patch.object(qbt.time, "monotonic", side_effect=monotonic),
                patch.object(qbt.time, "sleep", side_effect=sleep),
            ):
                report = qbt.submit_magnet(
                    TORRENT_MAGNET,
                    source_url="https://nyaa.si/view/2141829",
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=backup,
                )

        self.assertGreater(elapsed, 8.0)
        self.assertEqual(report["status"], "submitted_verified")
        self.assertEqual(report["verification"], "torrent_metadata_saved")

    def test_cold_start_is_ready_before_torrent_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            commands: list[list[str]] = []

            startup_process = Mock()
            startup_process.poll.return_value = None
            submission_process = Mock()
            submission_process.poll.return_value = 0

            def launch(command: list[str]) -> Mock:
                commands.append(command)
                if len(commands) == 1:
                    return startup_process
                submitted = Path(command[-1])
                self.assertEqual(submitted.read_bytes(), TORRENT_DATA)
                (backup / f"{TORRENT_HASH}.fastresume").touch()
                (backup / f"{TORRENT_HASH}.torrent").write_bytes(TORRENT_DATA)
                return submission_process

            with (
                patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)),
                patch.object(qbt, "qbittorrent_process_running", side_effect=[False, True]),
                patch.object(qbt, "_launch", side_effect=launch),
            ):
                report = qbt.submit_magnet(
                    TORRENT_MAGNET,
                    source_url="https://nyaa.si/view/2141829",
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=backup,
                    startup_settle_seconds=0,
                )

        self.assertEqual(commands[0], [str(executable.resolve()), "--no-splash"])
        self.assertTrue(commands[1][-1].endswith(".torrent"))
        self.assertTrue(report["client_started"])
        self.assertEqual(report["submission_attempts"], 1)

    def test_retries_torrent_handoff_once_before_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            elapsed = 0.0
            launches = 0

            process = Mock()
            process.poll.return_value = 0

            def monotonic() -> float:
                return elapsed

            def sleep(seconds: float) -> None:
                nonlocal elapsed
                elapsed += seconds

            def launch(_: list[str]) -> Mock:
                nonlocal launches
                launches += 1
                if launches == 2:
                    (backup / f"{TORRENT_HASH}.fastresume").touch()
                    (backup / f"{TORRENT_HASH}.torrent").write_bytes(TORRENT_DATA)
                return process

            with (
                patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)),
                patch.object(
                    qbt,
                    "ensure_qbittorrent_ready",
                    return_value={"client_was_running": True, "client_started": False},
                ),
                patch.object(qbt, "_launch", side_effect=launch),
                patch.object(qbt.time, "monotonic", side_effect=monotonic),
                patch.object(qbt.time, "sleep", side_effect=sleep),
            ):
                report = qbt.submit_magnet(
                    TORRENT_MAGNET,
                    source_url="https://nyaa.si/view/2141829",
                    executable=executable,
                    save_path=root / "downloads",
                    backup_dir=backup,
                    wait_seconds=5,
                    retry_delay_seconds=1,
                )

        self.assertEqual(launches, 2)
        self.assertEqual(report["status"], "submitted_verified")
        self.assertEqual(report["submission_attempts"], 2)

    def test_rejects_torrent_metadata_with_wrong_infohash(self) -> None:
        with patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)):
            with self.assertRaises(qbt.SubmissionError):
                qbt.download_torrent(
                    "https://nyaa.si/download/2141829.torrent",
                    expected_info_hash=INFO_HASH,
                )

    def test_existing_metadata_placeholder_fails_when_refresh_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / "qbittorrent.exe"
            executable.touch()
            backup = root / "backup"
            backup.mkdir()
            (backup / f"{INFO_HASH}.fastresume").touch()
            with (
                patch.object(qbt, "urlopen", return_value=FakeResponse(TORRENT_DATA)),
                patch.object(qbt.subprocess, "Popen") as popen,
            ):
                with self.assertRaises(qbt.SubmissionError):
                    qbt.submit_magnet(
                        MAGNET,
                        source_url="https://nyaa.si/view/2141829",
                        executable=executable,
                        backup_dir=backup,
                    )

        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
