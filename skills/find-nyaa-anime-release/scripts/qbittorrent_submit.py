#!/usr/bin/env python3
"""Submit one verified magnet to the local qBittorrent client."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


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


def backup_path(info_hash: str | None, backup_dir: Path) -> Path | None:
    return backup_dir / f"{info_hash}.fastresume" if info_hash else None


def submit_magnet(
    magnet: str,
    *,
    executable: Path | None = None,
    save_path: Path | None = DEFAULT_SAVE_PATH,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    wait_seconds: float = 8.0,
    dry_run: bool = False,
) -> dict[str, Any]:
    magnet = magnet.strip()
    info_hash = extract_btih(magnet)
    exe = find_executable(executable)
    resume_file = backup_path(info_hash, backup_dir)

    if resume_file and resume_file.is_file():
        return {
            "status": "already_present",
            "ok": True,
            "info_hash": info_hash,
            "executable": str(exe),
            "save_path": str(save_path) if save_path else None,
            "verification": "fastresume_exists",
        }

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
    command.append(magnet)

    if dry_run:
        return {
            "status": "dry_run",
            "ok": True,
            "info_hash": info_hash,
            "executable": str(exe),
            "save_path": str(save_path) if save_path else None,
            "command": command[:-1] + ["<magnet>"],
        }

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise SubmissionError(f"Failed to start qBittorrent: {exc}") from exc

    deadline = time.monotonic() + max(0.0, wait_seconds)
    return_code: int | None = None
    while time.monotonic() < deadline:
        if resume_file and resume_file.is_file():
            return {
                "status": "submitted_verified",
                "ok": True,
                "info_hash": info_hash,
                "executable": str(exe),
                "save_path": str(save_path) if save_path else None,
                "verification": "fastresume_created",
            }
        return_code = process.poll()
        if return_code not in (None, 0):
            raise SubmissionError(f"qBittorrent exited with code {return_code}.")
        time.sleep(0.2)

    return_code = process.poll()
    if return_code not in (None, 0):
        raise SubmissionError(f"qBittorrent exited with code {return_code}.")
    return {
        "status": "submitted",
        "ok": True,
        "info_hash": info_hash,
        "executable": str(exe),
        "save_path": str(save_path) if save_path else None,
        "verification": "native_cli_accepted",
        "handoff_process_running": return_code is None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("magnet")
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--save-path", type=Path, default=DEFAULT_SAVE_PATH)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--wait-seconds", type=float, default=8.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = submit_magnet(
            args.magnet,
            executable=args.exe,
            save_path=args.save_path,
            backup_dir=args.backup_dir,
            wait_seconds=args.wait_seconds,
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
