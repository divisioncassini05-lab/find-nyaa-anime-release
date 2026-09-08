from __future__ import annotations

import multiprocessing
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from test_qbittorrent_submit import (
    qbt, INFO_HASH, MAGNET, TORRENT_DATA, TORRENT_HASH, TORRENT_MAGNET, resume_data,
)


def process_result(code=0):
    result = Mock()
    result.poll.return_value = code
    return result


@pytest.mark.parametrize("raw", [b"", b"de", b"d", resume_data("a" * 40), resume_data(INFO_HASH) + b"junk"])
def test_empty_corrupt_or_wrong_hash_resume_never_proves_acceptance(tmp_path, raw):
    executable = tmp_path / "qbt.exe"
    executable.touch()
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / f"{INFO_HASH}.fastresume").write_bytes(raw)
    with (patch.object(qbt, "ensure_qbittorrent_ready", return_value={}),
          patch.object(qbt, "qbittorrent_process_running", return_value=True),
          patch.object(qbt, "_launch", return_value=process_result()) as launch):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.submit_magnet(MAGNET, executable=executable, save_path=None, backup_dir=backup, wait_seconds=0)
    assert error.value.code == "handoff_unverified"
    assert not error.value.as_report()["acceptance_evidence"]["fastresume_valid"]
    launch.assert_called_once()


def test_metadata_download_fallback_still_requires_magnet_acceptance(tmp_path):
    executable = tmp_path / "qbt.exe"
    executable.touch()
    with (patch.object(qbt, "download_torrent", side_effect=qbt.SubmissionError("network unavailable")),
          patch.object(qbt, "ensure_qbittorrent_ready", return_value={}),
          patch.object(qbt, "qbittorrent_process_running", return_value=True),
          patch.object(qbt, "_launch", return_value=process_result())):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.submit_magnet(MAGNET, source_url="https://nyaa.si/view/123", executable=executable,
                              save_path=None, backup_dir=tmp_path / "backup", wait_seconds=0)
    report = error.value.as_report()
    assert report["error_code"] == "handoff_unverified"
    assert report["submission_source"] == "magnet"
    assert report["source_fallback_error"] == "network unavailable"


def test_magnet_acceptance_can_precede_torrent_metadata(tmp_path):
    executable = tmp_path / "qbt.exe"
    executable.touch()
    backup = tmp_path / "backup"
    backup.mkdir()

    def launch(command):
        (backup / f"{INFO_HASH}.fastresume").write_bytes(resume_data(INFO_HASH))
        return process_result()

    with (patch.object(qbt, "ensure_qbittorrent_ready", return_value={}),
          patch.object(qbt, "_launch", side_effect=launch)):
        report = qbt.submit_magnet(MAGNET, executable=executable, save_path=None, backup_dir=backup, wait_seconds=0)
    assert report["status"] == "submitted_verified"
    assert not report["download_complete"]
    assert not report["acceptance_evidence"]["torrent_exists"]


@pytest.mark.parametrize("raw", [b"", b"de", TORRENT_DATA.replace(b"fixture", b"changed"), TORRENT_DATA + b"junk"])
def test_torrent_handoff_requires_valid_matching_torrent_metadata(tmp_path, raw):
    executable = tmp_path / "qbt.exe"
    executable.touch()
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / f"{TORRENT_HASH}.fastresume").write_bytes(resume_data(TORRENT_HASH))
    (backup / f"{TORRENT_HASH}.torrent").write_bytes(raw)
    with (patch.object(qbt, "download_torrent", return_value=TORRENT_DATA),
          patch.object(qbt, "ensure_qbittorrent_ready", return_value={}),
          patch.object(qbt, "qbittorrent_process_running", return_value=True),
          patch.object(qbt, "_launch", return_value=process_result())):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.submit_magnet(TORRENT_MAGNET, source_url="https://nyaa.si/view/123", executable=executable,
                              save_path=None, backup_dir=backup, wait_seconds=0)
    assert error.value.code == "handoff_unverified"


def test_launch_permission_error_preserves_target_and_evidence(tmp_path):
    executable = tmp_path / "qbt.exe"
    executable.touch()
    with (patch.object(qbt, "ensure_qbittorrent_ready", return_value={"client_was_running": True}),
          patch.object(qbt, "qbittorrent_process_running", return_value=True),
          patch.object(qbt.subprocess, "Popen", side_effect=PermissionError("denied"))):
        with pytest.raises(qbt.SubmissionError) as error:
            qbt.submit_magnet(MAGNET, executable=executable, save_path=None,
                              backup_dir=tmp_path / "backup", wait_seconds=0)
    report = error.value.as_report()
    assert report["error_code"] == "permission_denied"
    assert report["retryable"] is False
    assert report["info_hash"] == INFO_HASH
    assert report["submission_attempts"] == 0
    assert report["client_was_running"] is True
    assert report["client_process_running"] is True


def test_launch_stderr_is_available_without_pipe_deadlock():
    process = qbt._launch([sys.executable, "-c", "import sys; sys.stderr.write('fixture launch error'); sys.exit(3)"])
    try:
        assert process.wait(timeout=10) == 3
        report = qbt._launch_diagnostics(process)
        assert report["launch_returncode"] == 3
        assert report["launch_stderr"] == "fixture launch error"
    finally:
        qbt._launch_diagnostics(process, close=True)
    assert process._qbt_error_stream.closed


def test_lock_is_released_on_failure(tmp_path):
    with pytest.raises(RuntimeError):
        with qbt._submission_lock(tmp_path, wait_seconds=0):
            raise RuntimeError("fixture")
    with qbt._submission_lock(tmp_path, wait_seconds=0):
        pass


def _concurrent_submit(root_string, info_hash, ready, start, results):
    """Separate interpreter: no shared Python mutex can hide cross-process races."""
    root = Path(root_string)
    backup = root / "backup"

    def launch(command):
        marker = root / "active-submission"
        with marker.open("x"):
            with (root / "launches.txt").open("a") as log:
                log.write(info_hash + "\n")
            time.sleep(0.1)
            (backup / f"{info_hash}.fastresume").write_bytes(resume_data(info_hash))
        marker.unlink()
        return process_result()

    try:
        ready.put(True)
        if not start.wait(10):
            raise RuntimeError("start event timed out")
        with (patch.object(qbt, "ensure_qbittorrent_ready", return_value={}),
              patch.object(qbt, "_launch", side_effect=launch)):
            report = qbt.submit_magnet(f"magnet:?xt=urn:btih:{info_hash}", executable=root / "qbt.exe",
                                      save_path=None, backup_dir=backup, wait_seconds=0)
        results.put(report["status"])
    except Exception as error:
        results.put("error: " + repr(error))


@pytest.mark.parametrize("same_target", [True, False])
def test_processes_serialize_and_recheck_existing_target(tmp_path, same_target):
    (tmp_path / "qbt.exe").touch()
    (tmp_path / "backup").mkdir()
    ctx = multiprocessing.get_context("spawn")
    ready, results, start = ctx.Queue(), ctx.Queue(), ctx.Event()
    hashes = [INFO_HASH, INFO_HASH if same_target else TORRENT_HASH]
    workers = [ctx.Process(target=_concurrent_submit, args=(str(tmp_path), h, ready, start, results)) for h in hashes]
    try:
        for worker in workers:
            worker.start()
        for _ in workers:
            assert ready.get(timeout=15)
        start.set()
        statuses = sorted(results.get(timeout=15) for _ in workers)
        for worker in workers:
            worker.join(timeout=10)
            assert worker.exitcode == 0
        expected = ["already_present", "submitted_verified"] if same_target else ["submitted_verified"] * 2
        assert statuses == expected
        assert len((tmp_path / "launches.txt").read_text().splitlines()) == (1 if same_target else 2)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        ready.close()
        results.close()


def test_lock_contention_reports_client_busy(tmp_path):
    with qbt._submission_lock(tmp_path):
        with pytest.raises(qbt.SubmissionError) as error:
            with qbt._submission_lock(tmp_path, wait_seconds=0):
                pytest.fail("lock must not be reentrant")
    assert error.value.code == "client_busy"
    assert error.value.retryable is True
