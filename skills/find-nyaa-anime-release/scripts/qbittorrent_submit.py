#!/usr/bin/env python3
"""Submit one verified release to the local qBittorrent client."""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from http_transport import fetch_bytes, TransportError
from client_context import ClientContextError, require_context

_DEFAULT_URLOPEN = urlopen


DEFAULT_SAVE_PATH = Path(r"C:\User_data\Download\qBittorrent")
DEFAULT_BACKUP_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "qBittorrent"
    / "BT_backup"
)
KNOWN_EXECUTABLES = (
    Path(r"C:\Apps\Tools\qBittorrent\qbittorrent.exe"),
    Path(r"C:\Program Files\qBittorrent\qbittorrent.exe"),
    Path(r"C:\Program Files (x86)\qBittorrent\qbittorrent.exe"),
)
SUCCESS_STATUSES = {"already_present", "submitted", "submitted_verified"}
MAX_TORRENT_BYTES = 16 * 1024 * 1024
DEFAULT_PERSISTENCE_WAIT_SECONDS = 30.0
DEFAULT_STARTUP_WAIT_SECONDS = 30.0
DEFAULT_STARTUP_SETTLE_SECONDS = 2.0
DEFAULT_RETRY_DELAY_SECONDS = 5.0
DEFAULT_LOCK_WAIT_SECONDS = 90.0
_LOCAL_LOCKS: dict[str, threading.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


class SubmissionError(RuntimeError):
    def __init__(self, message: str, *, code: str = "submission_failed", retryable: bool | None = None,
                 diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.diagnostics = diagnostics or {}

    def as_report(self) -> dict[str, Any]:
        recovery = {}
        if self.code in {"startup_exited_without_client", "handoff_unverified", "client_context_required"}:
            recovery = {"client_recovery": {
                "action": "retry_full_resolver_in_approved_user_context",
                "requires_execution_tool_approval": True,
                "preserve_reviewed_candidate": True,
                "recheck_acceptance_before_submission": True,
                "startup_only_is_insufficient": True,
                "do_not_repeat_unchanged_context": True,
                "max_context_retries": 1,
                "cause_confirmed": self.code == "client_context_required",
                "scheduled_retry_allowed": False,
            }}
        return {**self.diagnostics, **recovery, "status": "error", "ok": False, "error": str(self),
                "error_code": self.code, "retryable": self.retryable}


def require_client_context(executable: Path | None = None) -> dict[str, Any]:
    try:
        return require_context() if executable is None else require_context_for_executable(executable)
    except ClientContextError as exc:
        raise SubmissionError(str(exc), code=exc.report['status'], retryable=False,
                              diagnostics={'stage': 'client_context',
                                           'execution_context': exc.report,
                                           'submission_attempts': 0,
                                           'client_attempted': False}) from exc


def require_context_for_executable(executable: Path) -> dict[str, Any]:
    from client_context import inspect_context
    report = inspect_context(executable=executable)
    if not report['ok']:
        raise ClientContextError(report)
    return report


@contextmanager
def _submission_lock(profile: Path, wait_seconds: float = DEFAULT_LOCK_WAIT_SECONDS):
    """Serialize one client profile across threads/processes; recheck tasks inside it."""
    key = os.path.normcase(str(profile.resolve()))
    with _LOCAL_LOCKS_GUARD:
        local_lock = _LOCAL_LOCKS.setdefault(key, threading.Lock())
    deadline = time.monotonic() + max(0.0, wait_seconds)
    if not local_lock.acquire(timeout=max(0.0, wait_seconds)):
        raise SubmissionError("Another submission is using this qBittorrent profile.",
                              code="client_busy", retryable=True)
    try:
        directory = Path(tempfile.gettempdir()) / "codex-qbittorrent-locks"
        directory.mkdir(parents=True, exist_ok=True)
        lock_file = directory / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
        # Do not unlink lock files: waiters must always lock the same inode.
        with lock_file.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            while True:
                stream.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if time.monotonic() >= deadline:
                        raise SubmissionError("Another process is submitting to this qBittorrent profile.",
                                              code="client_busy", retryable=True) from exc
                    time.sleep(0.1)
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        local_lock.release()


def extract_btih(magnet: str) -> str | None:
    parsed = urlsplit(magnet)
    if parsed.scheme.casefold() != "magnet":
        raise SubmissionError("Only magnet links can be submitted.")
    exact_topics = parse_qs(parsed.query).get("xt", [])
    for topic in exact_topics:
        match = re.fullmatch(r"urn:btih:([0-9a-fA-F]{40}|[A-Z2-7a-z2-7]{32})", topic)
        if not match:
            continue
        value = match.group(1)
        if len(value) == 40:
            return value.casefold()
        try:
            return base64.b32decode(value.upper()).hex()
        except (ValueError, base64.binascii.Error) as exc:
            raise SubmissionError("The magnet contains an invalid BTIH value.") from exc
    if any(topic.casefold().startswith("urn:btmh:") for topic in exact_topics):
        return None
    raise SubmissionError("The magnet has no supported BitTorrent exact topic.")


def _registry_executables() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    locations: list[Path] = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    uninstall_paths = (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for root in roots:
        for uninstall_path in uninstall_paths:
            try:
                uninstall = winreg.OpenKey(root, uninstall_path)
            except OSError:
                continue
            with uninstall:
                for index in range(winreg.QueryInfoKey(uninstall)[0]):
                    try:
                        child_name = winreg.EnumKey(uninstall, index)
                        child = winreg.OpenKey(uninstall, child_name)
                    except OSError:
                        continue
                    with child:
                        try:
                            display_name = str(winreg.QueryValueEx(child, "DisplayName")[0])
                        except OSError:
                            continue
                        if display_name.casefold() != "qbittorrent":
                            continue
                        for value_name in ("DisplayIcon", "InstallLocation"):
                            try:
                                value = str(winreg.QueryValueEx(child, value_name)[0]).strip('"')
                            except OSError:
                                continue
                            value = value.split('",', 1)[0]
                            path = Path(value)
                            locations.append(path if path.suffix else path / "qbittorrent.exe")
    return locations


def find_executable(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit)
    configured = os.environ.get("QBITTORRENT_EXE")
    if configured:
        candidates.append(Path(configured))
    discovered = shutil.which("qbittorrent") or shutil.which("qbittorrent.exe")
    if discovered:
        candidates.append(Path(discovered))
    candidates.extend(KNOWN_EXECUTABLES)
    candidates.extend(_registry_executables())

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    raise SubmissionError(
        "qBittorrent executable was not found; set QBITTORRENT_EXE or pass --exe.",
        code="executable_missing", retryable=False,
    )


def _windows_process_probe_fallback(executable: Path) -> bool:
    """Use .NET process enumeration when tasklist is unavailable or denied."""
    process_name = executable.stem.replace("'", "''")
    powershell = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
    )
    script = (
        "$ErrorActionPreference='Stop'; try { "
        f"if ([System.Diagnostics.Process]::GetProcessesByName('{process_name}').Length -gt 0) "
        "{ exit 0 }; exit 1 } catch { exit 2 }"
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
            timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SubmissionError(
            "Cannot inspect qBittorrent processes: tasklist and the .NET fallback failed; "
            "check process-query permissions before retrying.",
            code="process_probe_failed", retryable=None,
        ) from exc
    if result.returncode not in (0, 1):
        raise SubmissionError(
            "Cannot inspect qBittorrent processes: tasklist and the .NET fallback failed; "
            "check process-query permissions before retrying.",
            code="process_probe_failed", retryable=None,
        )
    return result.returncode == 0


def qbittorrent_process_running(executable: Path) -> bool:
    """Return whether the local qBittorrent GUI process is already running."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"IMAGENAME eq {executable.name}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=5,
                check=False,
                creationflags=creationflags,
            )
            if result.returncode != 0 or result.stdout is None:
                return _windows_process_probe_fallback(executable)
            return f'"{executable.name.casefold()}"' in result.stdout.casefold()
        result = subprocess.run(
            ["pgrep", "-x", executable.name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        if os.name == "nt":
            return _windows_process_probe_fallback(executable)
        return False


def _launch(command: list[str]) -> subprocess.Popen[bytes]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    error_stream = tempfile.TemporaryFile()
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=error_stream,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        process._qbt_error_stream = error_stream
        return process
    except OSError as exc:
        error_stream.close()
        raise SubmissionError(
            f"Failed to start qBittorrent: {exc}",
            code="permission_denied" if isinstance(exc, PermissionError) else "client_launch_failed",
            retryable=False if isinstance(exc, PermissionError) else None,
        ) from exc


def _launch_diagnostics(process: subprocess.Popen[bytes], *, close: bool = False) -> dict[str, Any]:
    report = {"launch_returncode": process.poll()}
    if isinstance(process.pid, int):
        report["launcher_pid"] = process.pid
    stream = vars(process).get("_qbt_error_stream")
    if stream is not None and not stream.closed:
        try:
            stream.seek(0)
            report["launch_stderr"] = stream.read(4096).decode("utf-8", errors="replace").strip()
        except OSError as exc:
            report["launch_stderr_error"] = str(exc)
        finally:
            if close:
                stream.close()
    return report


def ensure_qbittorrent_ready(
    executable: Path,
    *,
    wait_seconds: float = DEFAULT_STARTUP_WAIT_SECONDS,
    settle_seconds: float = DEFAULT_STARTUP_SETTLE_SECONDS,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """Cold-start qBittorrent separately and wait until its process is stable."""
    if profile_path is None and qbittorrent_process_running(executable):
        return {"client_was_running": True, "client_started": False}

    startup_command = [str(executable), "--no-splash"]
    if profile_path is not None:
        profile_path.mkdir(parents=True, exist_ok=True)
        startup_command.append(f"--profile={profile_path}")
    process = _launch(startup_command)
    effective_wait = max(0.0, wait_seconds)
    effective_settle = max(0.0, settle_seconds)
    started_at = time.monotonic()
    deadline = started_at + effective_wait
    stable_since: float | None = None

    try:
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code not in (None, 0):
                raise SubmissionError(f"qBittorrent exited with code {return_code} during startup.",
                                      code="startup_process_failed")
            running = return_code is None or qbittorrent_process_running(executable)
            now = time.monotonic()
            if running:
                if stable_since is None:
                    stable_since = now
                if now - stable_since >= effective_settle:
                    return {"client_was_running": False, "client_started": True}
            else:
                stable_since = None
                if now - started_at >= max(1.0, effective_settle):
                    raise SubmissionError(
                        "qBittorrent launcher exited with code 0 but no client process was detected; "
                        "no torrent was handed off. Check process visibility, execution permissions "
                        "and the user/profile context before retrying; a zero exit is not readiness.",
                        code="startup_exited_without_client", retryable=None,
                    )
            time.sleep(0.2)
        raise SubmissionError(
            f"qBittorrent did not become ready within {effective_wait:g} seconds after cold start.",
            code="startup_timeout", retryable=True,
        )
    except SubmissionError as exc:
        exc.diagnostics.update(_launch_diagnostics(process))
        exc.diagnostics["stage"] = "startup"
        raise
    finally:
        _launch_diagnostics(process, close=True)


def backup_path(info_hash: str | None, backup_dir: Path) -> Path | None:
    return backup_dir / f"{info_hash}.fastresume" if info_hash else None


def torrent_backup_path(info_hash: str | None, backup_dir: Path) -> Path | None:
    return backup_dir / f"{info_hash}.torrent" if info_hash else None


def _decode_bencode(data: bytes, index: int = 0) -> tuple[Any, int]:
    """Decode the small bencoded dictionaries qBittorrent writes in fastresume files."""
    if index >= len(data):
        raise SubmissionError("The qBittorrent fastresume file is truncated.")
    marker = data[index : index + 1]
    if marker == b"i":
        end = data.find(b"e", index + 1)
        if end < 0:
            raise SubmissionError("The qBittorrent fastresume integer is invalid.")
        try:
            value = int(data[index + 1 : end])
        except ValueError as exc:
            raise SubmissionError("The qBittorrent fastresume integer is invalid.") from exc
        return value, end + 1
    if marker == b"l":
        values: list[Any] = []
        index += 1
        while index < len(data) and data[index : index + 1] != b"e":
            value, index = _decode_bencode(data, index)
            values.append(value)
        if index >= len(data):
            raise SubmissionError("The qBittorrent fastresume list is truncated.")
        return values, index + 1
    if marker == b"d":
        values: dict[bytes, Any] = {}
        index += 1
        while index < len(data) and data[index : index + 1] != b"e":
            key, index = _decode_bencode(data, index)
            value, index = _decode_bencode(data, index)
            if isinstance(key, bytes):
                values[key] = value
        if index >= len(data):
            raise SubmissionError("The qBittorrent fastresume dictionary is truncated.")
        return values, index + 1
    if marker.isdigit():
        return _read_byte_string(data, index)
    raise SubmissionError("The qBittorrent fastresume file contains invalid bencode.")


def inspect_fastresume(path: Path | None) -> dict[str, Any]:
    """Return completion evidence without confusing metadata persistence with completion."""
    if path is None or not path.is_file():
        return {
            "download_complete": False,
            "completion_source": "fastresume_missing",
            "fastresume_exists": False,
        }
    try:
        raw = path.read_bytes()
        value, _ = _decode_bencode(raw)
    except (OSError, SubmissionError) as exc:
        return {
            "download_complete": False,
            "completion_source": "fastresume_unreadable",
            "fastresume_exists": True,
            "completion_error": str(exc),
        }
    if not isinstance(value, dict):
        return {
            "download_complete": False,
            "completion_source": "fastresume_invalid",
            "fastresume_exists": True,
        }
    completed_time = value.get(b"completed_time")
    finished_time = value.get(b"finished_time")
    complete = any(isinstance(item, int) and item > 0 for item in (completed_time, finished_time))
    return {
        "download_complete": complete,
        "completion_source": (
            "fastresume_completed_time" if complete else "fastresume_present_not_complete"
        ),
        "fastresume_exists": True,
    }


def inspect_torrent(info_hash: str, backup_dir: Path = DEFAULT_BACKUP_DIR) -> dict[str, Any]:
    """Inspect one local qBittorrent task by its exact info-hash."""
    normalized = info_hash.strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{40}", normalized):
        raise SubmissionError("The info-hash must be a 40-character hexadecimal value.")
    report = inspect_fastresume(backup_path(normalized, backup_dir))
    report.update(
        {
            "status": "complete" if report["download_complete"] else "pending",
            "ok": True,
            "info_hash": normalized,
        }
    )
    return report


def _acceptance_evidence(info_hash: str | None, backup_dir: Path) -> dict[str, Any]:
    """Existence alone is insufficient: validate saved records for this exact hash."""
    evidence: dict[str, Any] = {
        "fastresume_exists": False, "fastresume_valid": False,
        "torrent_exists": False, "torrent_valid": False,
    }
    if not info_hash:
        evidence["verification_error"] = "No supported v1 info-hash is available for verification."
        return evidence
    for kind, path in (
        ("fastresume", backup_path(info_hash, backup_dir)),
        ("torrent", torrent_backup_path(info_hash, backup_dir)),
    ):
        try:
            with path.open("rb") as stream:
                evidence[kind + "_exists"] = True
                raw = stream.read(MAX_TORRENT_BYTES + 1)
            if len(raw) > MAX_TORRENT_BYTES:
                raise SubmissionError("Saved metadata exceeds the inspection size limit.")
            value, end = _decode_bencode(raw)
            if not isinstance(value, dict) or end != len(raw):
                raise SubmissionError("Saved metadata is not a complete bencoded dictionary.")
            if kind == "fastresume":
                valid = (value.get(b"file-format") == b"libtorrent resume file"
                         and value.get(b"info-hash") == bytes.fromhex(info_hash))
            else:
                valid = isinstance(value.get(b"info"), dict) and torrent_info_hash(raw) == info_hash
            evidence[kind + "_valid"] = valid
            if not valid:
                evidence[kind + "_error"] = "Saved metadata format or info-hash does not match."
        except FileNotFoundError:
            pass
        except (OSError, SubmissionError, ValueError, RecursionError) as exc:
            evidence[kind + "_error"] = str(exc)
    return evidence


def nyaa_torrent_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    parsed = urlsplit(source_url.strip())
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.path.casefold().endswith(".torrent"):
        return source_url.strip()
    match = re.fullmatch(r"/view/(\d+)/?", parsed.path)
    if not match or parsed.hostname not in {"nyaa.si", "www.nyaa.si"}:
        return None
    return f"https://nyaa.si/download/{match.group(1)}.torrent"


def _read_byte_string(data: bytes, index: int) -> tuple[bytes, int]:
    colon = data.find(b":", index)
    if colon < 0 or not data[index:colon].isdigit():
        raise SubmissionError("The torrent file contains invalid bencode.")
    length = int(data[index:colon])
    start = colon + 1
    end = start + length
    if end > len(data):
        raise SubmissionError("The torrent file is truncated.")
    return data[start:end], end


def _skip_bencode(data: bytes, index: int) -> int:
    if index >= len(data):
        raise SubmissionError("The torrent file is truncated.")
    marker = data[index : index + 1]
    if marker == b"i":
        end = data.find(b"e", index + 1)
        if end < 0:
            raise SubmissionError("The torrent file contains invalid bencode.")
        int(data[index + 1 : end])
        return end + 1
    if marker in {b"l", b"d"}:
        index += 1
        while index < len(data) and data[index : index + 1] != b"e":
            index = _skip_bencode(data, index)
            if marker == b"d":
                index = _skip_bencode(data, index)
        if index >= len(data):
            raise SubmissionError("The torrent file is truncated.")
        return index + 1
    if marker.isdigit():
        return _read_byte_string(data, index)[1]
    raise SubmissionError("The torrent file contains invalid bencode.")


def torrent_info_hash(data: bytes) -> str:
    if not data.startswith(b"d"):
        raise SubmissionError("The downloaded file is not a BitTorrent metainfo file.")
    index = 1
    while index < len(data) and data[index : index + 1] != b"e":
        key, index = _read_byte_string(data, index)
        value_start = index
        index = _skip_bencode(data, index)
        if key == b"info":
            return hashlib.sha1(data[value_start:index]).hexdigest()
    raise SubmissionError("The torrent file has no info dictionary.")


def download_torrent(
    torrent_url: str,
    *,
    expected_info_hash: str | None,
    timeout_seconds: float = 20.0,
) -> bytes:
    request = Request(torrent_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data, _ = fetch_bytes(request, timeout=max(1.0, timeout_seconds),
                              max_bytes=MAX_TORRENT_BYTES, opener=urlopen,
                              native_fallback=urlopen is _DEFAULT_URLOPEN)
    except TransportError as exc:
        if exc.code == "response_too_large":
            raise SubmissionError("The torrent metadata file is unexpectedly large.") from exc
        raise SubmissionError(f"Failed to download torrent metadata: {exc}") from exc
    except OSError as exc:
        raise SubmissionError(f"Failed to download torrent metadata: {exc}") from exc
    if len(data) > MAX_TORRENT_BYTES:
        raise SubmissionError("The torrent metadata file is unexpectedly large.")
    actual_info_hash = torrent_info_hash(data)
    if expected_info_hash and actual_info_hash != expected_info_hash:
        raise SubmissionError(
            "The downloaded torrent metadata does not match the verified magnet infohash."
        )
    return data


def submit_magnet(
    magnet: str,
    *,
    source_url: str | None = None,
    torrent_url: str | None = None,
    executable: Path | None = None,
    save_path: Path | None = DEFAULT_SAVE_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    profile_path: Path | None = None,
    wait_seconds: float = DEFAULT_PERSISTENCE_WAIT_SECONDS,
    startup_wait_seconds: float = DEFAULT_STARTUP_WAIT_SECONDS,
    startup_settle_seconds: float = DEFAULT_STARTUP_SETTLE_SECONDS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    context = {
        "info_hash": extract_btih(magnet.strip()),
        "backup_dir": str(backup_dir.resolve()),
        "profile_path": str(profile_path.resolve()) if profile_path else None,
    }
    options = dict(
        source_url=source_url, torrent_url=torrent_url, executable=executable,
        save_path=save_path, backup_dir=backup_dir, profile_path=profile_path,
        wait_seconds=wait_seconds, startup_wait_seconds=startup_wait_seconds,
        startup_settle_seconds=startup_settle_seconds, retry_delay_seconds=retry_delay_seconds,
        dry_run=dry_run,
    )
    try:
        if dry_run:
            return _submit_magnet_locked(magnet, **options)
        # Profile identity does not include the torrent hash: distinct targets also serialize.
        with _submission_lock(profile_path if profile_path is not None else backup_dir):
            return _submit_magnet_locked(magnet, **options)
    except SubmissionError as exc:
        exc.diagnostics = {**context, **exc.diagnostics}
        raise
    except OSError as exc:
        raise SubmissionError(str(exc),
                              code="permission_denied" if isinstance(exc, PermissionError) else "submission_io_failed",
                              retryable=False if isinstance(exc, PermissionError) else None,
                              diagnostics=context) from exc


def _submit_magnet_locked(
    magnet: str,
    *,
    source_url: str | None = None,
    torrent_url: str | None = None,
    executable: Path | None = None,
    save_path: Path | None = DEFAULT_SAVE_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    profile_path: Path | None = None,
    wait_seconds: float = DEFAULT_PERSISTENCE_WAIT_SECONDS,
    startup_wait_seconds: float = DEFAULT_STARTUP_WAIT_SECONDS,
    startup_settle_seconds: float = DEFAULT_STARTUP_SETTLE_SECONDS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    magnet = magnet.strip()
    info_hash = extract_btih(magnet)
    exe = find_executable(executable)
    require_client_context(exe)
    resume_file = backup_path(info_hash, backup_dir)
    metadata_file = torrent_backup_path(info_hash, backup_dir)
    resolved_torrent_url = torrent_url or nyaa_torrent_url(source_url)
    evidence = _acceptance_evidence(info_hash, backup_dir)
    resume_existed = evidence["fastresume_exists"]

    if evidence["fastresume_valid"] and (
        not resolved_torrent_url or evidence["torrent_valid"]
    ):
        report = {
            "status": "already_present",
            "ok": True,
            "info_hash": info_hash,
            "executable": str(exe),
            "save_path": str(save_path) if save_path else None,
            "verification": (
                "torrent_metadata_exists"
                if metadata_file and metadata_file.is_file()
                else "fastresume_exists"
            ),
        }
        report.update(inspect_fastresume(resume_file))
        report["acceptance_evidence"] = evidence
        return report

    torrent_data: bytes | None = None
    source_error: str | None = None
    if resolved_torrent_url and not dry_run:
        try:
            torrent_data = download_torrent(
                resolved_torrent_url,
                expected_info_hash=info_hash,
            )
        except SubmissionError as exc:
            source_error = str(exc)
            if resume_existed:
                raise SubmissionError(
                    "The existing qBittorrent task has no saved torrent metadata, and the "
                    f"metadata refresh failed: {source_error}"
                ) from exc

    command = [
        str(exe),
        "--no-splash",
        "--skip-dialog=true",
        "--add-stopped=false",
    ]
    if profile_path is not None:
        if not dry_run:
            profile_path.mkdir(parents=True, exist_ok=True)
        command.append(f"--profile={profile_path}")
    if save_path:
        if not dry_run:
            save_path.mkdir(parents=True, exist_ok=True)
        command.append(f"--save-path={save_path}")
    temporary_torrent: Path | None = None
    if torrent_data is not None:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".torrent",
            prefix=f"nyaa-{info_hash or 'release'}-",
            delete=False,
        )
        try:
            handle.write(torrent_data)
        finally:
            handle.close()
        temporary_torrent = Path(handle.name)
        command.append(str(temporary_torrent))
    else:
        command.append(magnet)

    if dry_run:
        return {
            "status": "dry_run",
            "ok": True,
            "info_hash": info_hash,
            "executable": str(exe),
            "save_path": str(save_path) if save_path else None,
            "command": command[:-1]
            + (["<torrent-file>"] if resolved_torrent_url else ["<magnet>"]),
            "submission_source": "torrent" if resolved_torrent_url else "magnet",
        }

    processes: list[subprocess.Popen[bytes]] = []
    client_report: dict[str, Any] = {}
    submission_attempts = 0
    try:
        client_report = ensure_qbittorrent_ready(
            exe,
            wait_seconds=startup_wait_seconds,
            settle_seconds=startup_settle_seconds,
            profile_path=profile_path,
        )
        process = _launch(command)
        processes.append(process)
        submission_attempts = 1

        effective_wait_seconds = max(0.0, wait_seconds)
        started_at = time.monotonic()
        deadline = started_at + effective_wait_seconds
        retry_at = started_at + max(0.0, retry_delay_seconds)
        return_code: int | None = None
        while True:
            evidence = _acceptance_evidence(info_hash, backup_dir)
            if evidence["fastresume_valid"] and (torrent_data is None or evidence["torrent_valid"]):
                report = {
                    "status": "submitted_verified",
                    "ok": True,
                    "info_hash": info_hash,
                    "executable": str(exe),
                    "save_path": str(save_path) if save_path else None,
                    "verification": (
                        "torrent_metadata_saved" if torrent_data is not None else "fastresume_created"
                    ),
                    "submission_source": "torrent" if torrent_data is not None else "magnet",
                    "source_fallback_error": source_error,
                    "submission_attempts": submission_attempts,
                    "acceptance_evidence": evidence,
                    **client_report,
                }
                report.update(inspect_fastresume(resume_file))
                return report
            return_code = process.poll()
            if return_code not in (None, 0):
                raise SubmissionError(f"qBittorrent exited with code {return_code}.", code="handoff_process_failed")
            if time.monotonic() >= deadline:
                break
            if (
                torrent_data is not None
                and submission_attempts == 1
                and time.monotonic() >= retry_at
                and return_code == 0
            ):
                process = _launch(command)
                processes.append(process)
                submission_attempts = 2
            time.sleep(0.2)

        raise SubmissionError(
            "qBittorrent handoff was not verified: no valid matching task records appeared "
            f"within {effective_wait_seconds:g} seconds after {submission_attempts} submission attempt(s). "
            "Launcher exit is not acceptance. Desktop-session/IPC permissions are a possible, "
            "unconfirmed cause; inspect diagnostics before retrying in an approved user context.",
            code="handoff_unverified", retryable=None,
        )
    except SubmissionError as exc:
        exc.diagnostics = {
            "executable": str(exe), "submission_source": "torrent" if torrent_data is not None else "magnet",
            "source_fallback_error": source_error, "submission_attempts": submission_attempts,
            "acceptance_evidence": _acceptance_evidence(info_hash, backup_dir),
            **client_report, **exc.diagnostics,
        }
        if processes:
            exc.diagnostics["launches"] = [_launch_diagnostics(item) for item in processes]
        try:
            exc.diagnostics["client_process_running"] = qbittorrent_process_running(exe)
        except SubmissionError as probe_error:
            exc.diagnostics["client_process_running"] = None
            exc.diagnostics["client_probe_error"] = str(probe_error)
        raise
    finally:
        for item in processes:
            _launch_diagnostics(item, close=True)
        if temporary_torrent is not None:
            try:
                temporary_torrent.unlink()
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("magnet", nargs='?')
    parser.add_argument('--check-context', action='store_true',
                        help='Inspect the execution token without network, client launch or state writes.')
    parser.add_argument("--source-url")
    parser.add_argument("--torrent-url")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--save-path", type=Path, default=DEFAULT_SAVE_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument(
        "--profile",
        type=Path,
        help="Use an isolated qBittorrent profile directory (intended for controlled testing).",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=DEFAULT_PERSISTENCE_WAIT_SECONDS,
        help=(
            "Seconds to wait for qBittorrent to persist .torrent and .fastresume metadata "
            f"(default: {DEFAULT_PERSISTENCE_WAIT_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--startup-wait-seconds",
        type=float,
        default=DEFAULT_STARTUP_WAIT_SECONDS,
        help=(
            "Seconds to wait for a cold-started qBittorrent process "
            f"(default: {DEFAULT_STARTUP_WAIT_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--startup-settle-seconds",
        type=float,
        default=DEFAULT_STARTUP_SETTLE_SECONDS,
        help=(
            "Seconds the cold-started qBittorrent process must remain stable before submission "
            f"(default: {DEFAULT_STARTUP_SETTLE_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        help=(
            "Seconds before retrying a metadata-bearing torrent handoff once "
            f"(default: {DEFAULT_RETRY_DELAY_SECONDS:g})."
        ),
    )
    parser.add_argument(
        "--inspect-info-hash",
        help="Inspect local completion evidence for an existing 40-character info-hash without submitting it.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.check_context or args.inspect_info_hash or args.magnet):
        build_parser().error('magnet is required unless inspecting context or an existing info hash')
    try:
        if args.check_context:
            report = require_client_context()
        elif args.inspect_info_hash:
            report = inspect_torrent(args.inspect_info_hash, args.backup_dir)
        else:
            report = submit_magnet(
                args.magnet,
                source_url=args.source_url,
                torrent_url=args.torrent_url,
                executable=args.exe,
                save_path=args.save_path,
                backup_dir=args.backup_dir,
                profile_path=args.profile,
                wait_seconds=args.wait_seconds,
                startup_wait_seconds=args.startup_wait_seconds,
                startup_settle_seconds=args.startup_settle_seconds,
                retry_delay_seconds=args.retry_delay_seconds,
                dry_run=args.dry_run,
            )
    except SubmissionError as exc:
        report = exc.as_report()
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(report["error"], file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
