from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import find_anime_release as finder
import qbittorrent_submit as qbt
import release_search_core as core


class CacheFaultTests(unittest.TestCase):
    def test_corrupt_raw_cache_is_disposable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            path.write_text("{truncated", encoding="utf-8")
            self.assertEqual({"version": core.RAW_CACHE_VERSION, "entries": {}, "recent_pages": {}}, core._load_raw_cache(path))
            self.assertEqual("{truncated", path.read_text(encoding="utf-8"))

    def test_corrupt_schedule_cache_is_disposable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(
                {"version": finder.SCHEDULE_CACHE_VERSION, "entries": {}},
                finder.load_schedule_cache(path),
            )

    def test_expired_malformed_cache_entry_is_removed_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            path.write_text(
                json.dumps(
                    {
                        "version": core.RAW_CACHE_VERSION,
                        "entries": {"bad": {"expires_at": "not-a-number", "items": []}},
                        "recent_pages": {},
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(core._read_cached_rss_items(path, "bad"))
            self.assertNotIn("bad", json.loads(path.read_text(encoding="utf-8"))["entries"])


class DeliveryFaultTests(unittest.TestCase):
    def test_torrent_url_rejects_non_nyaa_and_lookalike_hosts(self) -> None:
        for url in (
            "https://example.test/view/123",
            "https://nyaa.si.example.test/view/123",
            "file:///C:/secret/123.torrent",
        ):
            self.assertIsNone(qbt.nyaa_torrent_url(url))

    def test_oversized_torrent_is_rejected_before_hash_acceptance(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"x" * (qbt.MAX_TORRENT_BYTES + 1)
        with patch.object(qbt, "urlopen", return_value=response):
            with self.assertRaisesRegex(qbt.SubmissionError, "unexpectedly large"):
                qbt.download_torrent("https://nyaa.si/download/1.torrent", expected_info_hash=None)

    def test_hash_mismatch_never_becomes_success(self) -> None:
        info = b"d6:lengthi1e4:name7:fixturee"
        torrent = b"d4:info" + info + b"e"
        self.assertNotEqual("f" * 40, hashlib.sha1(info).hexdigest())
        response = MagicMock()
        response.__enter__.return_value.read.return_value = torrent
        with patch.object(qbt, "urlopen", return_value=response):
            with self.assertRaisesRegex(qbt.SubmissionError, "does not match"):
                qbt.download_torrent(
                    "https://nyaa.si/download/1.torrent",
                    expected_info_hash="f" * 40,
                )


class FailureClassificationTests(unittest.TestCase):
    def test_retryable_finder_failures_have_nonzero_stable_codes(self) -> None:
        statuses = (
            "no_nyaa_release_for_target",
            "output_incomplete",
            "download_enqueue_failed",
        )
        self.assertTrue(all((finder.status_return_code(status) or 0) > 0 for status in statuses))
        self.assertIsNone(finder.status_return_code("latest_unresolved"))

    def test_failure_reports_never_expose_selected_magnet(self) -> None:
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=2,
            status="release_unqualified",
            selected=[],
            choices=[],
            diagnostics={},
            failures=["network"],
            cache="miss",
        ).as_dict()
        self.assertEqual([], report["selected"])
        self.assertNotIn("magnet", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
