#!/usr/bin/env python3
"""Submit one verified release to the local qBittorrent client."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


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


class SubmissionError(RuntimeError):
    pass


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
        "qBittorrent executable was not found; set QBITTORRENT_EXE or pass --exe."
    )


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
                timeout=5,
                check=False,
                creationflags=creationflags,
            )
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
        return False


def _launch(command: list[str]) -> subprocess.Popen[bytes]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise SubmissionError(f"Failed to start qBittorrent: {exc}") from exc


def ensure_qbittorrent_ready(
    executable: Path,
    *,
    wait_seconds: float = DEFAULT_STARTUP_WAIT_SECONDS,
    settle_seconds: float = DEFAULT_STARTUP_SETTLE_SECONDS,
) -> dict[str, Any]:
    """Cold-start qBittorrent separately and wait until its process is stable."""
    if qbittorrent_process_running(executable):
        return {"client_was_running": True, "client_started": False}

    process = _launch([str(executable), "--no-splash"])
    effective_wait = max(0.0, wait_seconds)
    effective_settle = max(0.0, settle_seconds)
    deadline = time.monotonic() + effective_wait
    stable_since: float | None = None

    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code not in (None, 0):
            raise SubmissionError(f"qBittorrent exited with code {return_code} during startup.")
        running = qbittorrent_process_running(executable) or return_code is None
        now = time.monotonic()
        if running:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= effective_settle:
                return {"client_was_running": False, "client_started": True}
        else:
            stable_since = None
        time.sleep(0.2)

    raise SubmissionError(
        "qBittorrent did not become ready within "
        f"{effective_wait:g} seconds after cold start."
    )


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
        with urlopen(request, timeout=max(1.0, timeout_seconds)) as response:
            data = response.read(MAX_TORRENT_BYTES + 1)
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
    wait_seconds: float = DEFAULT_PERSISTENCE_WAIT_SECONDS,
    startup_wait_seconds: float = DEFAULT_STARTUP_WAIT_SECONDS,
    startup_settle_seconds: float = DEFAULT_STARTUP_SETTLE_SECONDS,
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    magnet = magnet.strip()
    info_hash = extract_btih(magnet)
    exe = find_executable(executable)
    resume_file = backup_path(info_hash, backup_dir)
    metadata_file = torrent_backup_path(info_hash, backup_dir)
    resolved_torrent_url = torrent_url or nyaa_torrent_url(source_url)
    resume_existed = bool(resume_file and resume_file.is_file())

    if resume_existed and (
        not resolved_torrent_url or (metadata_file and metadata_file.is_file())
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

    try:
        client_report = ensure_qbittorrent_ready(
            exe,
            wait_seconds=startup_wait_seconds,
            settle_seconds=startup_settle_seconds,
        )
        process = _launch(command)
        submission_attempts = 1

        effective_wait_seconds = max(0.0, wait_seconds)
        started_at = time.monotonic()
        deadline = started_at + effective_wait_seconds
        retry_at = started_at + max(0.0, retry_delay_seconds)
        return_code: int | None = None
        while time.monotonic() < deadline:
            resume_ready = bool(resume_file and resume_file.is_file())
            metadata_ready = bool(metadata_file and metadata_file.is_file())
            if resume_ready and (torrent_data is None or metadata_ready):
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
                    **client_report,
                }
                report.update(inspect_fastresume(resume_file))
                return report
            return_code = process.poll()
            if return_code not in (None, 0):
                raise SubmissionError(f"qBittorrent exited with code {return_code}.")
            if (
                torrent_data is not None
                and submission_attempts == 1
                and time.monotonic() >= retry_at
                and return_code == 0
            ):
                process = _launch(command)
                submission_attempts = 2
            time.sleep(0.2)

        # qBittorrent may persist BT_backup files during the final polling sleep.
        # Check once more at the deadline before reporting a failed handoff.
        resume_ready = bool(resume_file and resume_file.is_file())
        metadata_ready = bool(metadata_file and metadata_file.is_file())
        if resume_ready and (torrent_data is None or metadata_ready):
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
                **client_report,
            }
            report.update(inspect_fastresume(resume_file))
            return report

        return_code = process.poll()
        if return_code not in (None, 0):
            raise SubmissionError(f"qBittorrent exited with code {return_code}.")
        if torrent_data is not None:
            raise SubmissionError(
                "qBittorrent accepted the torrent file but did not persist its metadata "
                f"within {effective_wait_seconds:g} seconds after {submission_attempts} "
                "submission attempt(s)."
            )
        report = {
            "status": "submitted",
            "ok": True,
            "info_hash": info_hash,
            "executable": str(exe),
            "save_path": str(save_path) if save_path else None,
            "verification": "native_cli_accepted",
            "handoff_process_running": return_code is None,
            "submission_source": "magnet",
            "source_fallback_error": source_error,
            "submission_attempts": submission_attempts,
            **client_report,
        }
        report.update(inspect_fastresume(resume_file))
        return report
    finally:
        if temporary_torrent is not None:
            try:
                temporary_torrent.unlink()
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("magnet")
    parser.add_argument("--source-url")
    parser.add_argument("--torrent-url")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--save-path", type=Path, default=DEFAULT_SAVE_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
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
    try:
        if args.inspect_info_hash:
            report = inspect_torrent(args.inspect_info_hash, args.backup_dir)
        else:
            report = submit_magnet(
                args.magnet,
                source_url=args.source_url,
                torrent_url=args.torrent_url,
                executable=args.exe,
                save_path=args.save_path,
                backup_dir=args.backup_dir,
                wait_seconds=args.wait_seconds,
                startup_wait_seconds=args.startup_wait_seconds,
                startup_settle_seconds=args.startup_settle_seconds,
                retry_delay_seconds=args.retry_delay_seconds,
                dry_run=args.dry_run,
            )
    except SubmissionError as exc:
        report = {"status": "error", "ok": False, "error": str(exc)}
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
