from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import find_anime_release as finder
import qbittorrent_submit as qbt


pytestmark = pytest.mark.live


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for the controlled live test")
    return value


def test_controlled_live_search_and_optional_qbittorrent_handoff() -> None:
    if os.environ.get("ANIME_TEST_LIVE") != "1":
        pytest.skip("set ANIME_TEST_LIVE=1 to enable controlled live integration")
    if os.environ.get("ANIME_TEST_LEGAL_OK") != "1":
        pytest.skip("set ANIME_TEST_LEGAL_OK=1 after confirming lawful access")

    title = _required("ANIME_TEST_TITLE")
    episode = int(_required("ANIME_TEST_EPISODE"))
    tier = os.environ.get("ANIME_TEST_TIER", "browse").strip() or "browse"

    with tempfile.TemporaryDirectory(prefix="anime-skill-live-") as directory:
        root = Path(directory)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = finder.main(
                [
                    title,
                    "--episode",
                    str(episode),
                    "--tier",
                    tier,
                    "--want-zh",
                    "--include-magnet",
                    "--include-page-link",
                    "--legal-ok",
                    "--no-state-update",
                    "--json",
                    "--state",
                    str(root / "state.json"),
                    "--cache",
                    str(root / "raw-cache.json"),
                    "--schedule-cache",
                    str(root / "schedule-cache.json"),
                ]
            )
        payload = json.loads(output.getvalue())
        assert code == 0, payload
        assert payload["status"] == "found", payload
        selected = payload["selected"]
        assert selected["magnet"].startswith("magnet:?xt=urn:btih:")
        assert selected["url"].startswith("https://nyaa.si/view/")
        assert not (root / "state.json").exists()

        if os.environ.get("ANIME_TEST_QBITTORRENT") != "1":
            return

        executable = Path(_required("ANIME_TEST_QBITTORRENT_EXE"))
        profile = Path(_required("ANIME_TEST_QBITTORRENT_PROFILE"))
        backup = Path(_required("ANIME_TEST_QBITTORRENT_BACKUP_DIR"))
        download = root / "downloads"
        try:
            report = qbt.submit_magnet(
                selected["magnet"],
                source_url=selected["url"],
                executable=executable,
                save_path=download,
                backup_dir=backup,
                profile_path=profile,
            )
            assert report["ok"] is True
            assert report["status"] in qbt.SUCCESS_STATUSES
        finally:
            subprocess.run(
                [str(executable), "--no-splash", f"--profile={profile}", "--exit"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
