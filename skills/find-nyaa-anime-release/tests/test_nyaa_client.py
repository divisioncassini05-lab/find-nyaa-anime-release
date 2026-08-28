from __future__ import annotations

import os
import socket
import sys
import unittest
import urllib.error
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from nyaa_client import (  # noqa: E402
    NyaaClient,
    NyaaNetworkError,
    NyaaNotFoundError,
    NyaaParseError,
    NyaaRelease,
    NyaaSearchRequest,
    parse_rss,
)
import release_search_core as core  # noqa: E402
import search_nyaa_releases as nyaa  # noqa: E402


RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa"><channel><item>
  <title>[Group] Example S01E03 [1080p]</title>
  <link>https://nyaa.si/download/2003.torrent</link>
  <guid>https://nyaa.si/view/2003</guid>
  <pubDate>Fri, 10 Jul 2026 00:00:00 +0000</pubDate>
  <nyaa:size>1.5 GiB</nyaa:size><nyaa:seeders>21</nyaa:seeders>
  <nyaa:leechers>3</nyaa:leechers><nyaa:downloads>144</nyaa:downloads>
  <nyaa:category>Anime - English-translated</nyaa:category>
  <nyaa:infoHash>0000000000000000000000000000000000002003</nyaa:infoHash>
</item></channel></rss>"""

LISTING = """
<table class="torrent-list"><tbody><tr>
  <td><a href="/?c=1_3" title="Anime - Non-English-translated">Anime</a></td>
  <td><a href="/view/2003" title="[Group] Example S01E03 [1080p]">Example</a></td>
  <td><a href="magnet:?xt=urn:btih:0000000000000000000000000000000000002003">magnet</a></td>
  <td>1.5 GiB</td><td data-timestamp="1783641600">date</td>
  <td>21</td><td>3</td><td>144</td>
</tr></tbody></table>
"""

DETAIL = """
<div class="panel panel-default"><div class="panel-heading">
  <h3 class="panel-title">[Group] Example S01E03 [1080p]</h3>
</div><div class="panel-body">
  <div><div>Category:</div><div>Anime - Non-English-translated</div></div>
  <div><div>Date:</div><div data-timestamp="1783641600">2026-07-10</div></div>
  <div><div>Seeders:</div><div>21</div></div>
  <div><div>Leechers:</div><div>3</div></div>
  <div><div>File size:</div><div>1.5 GiB</div></div>
  <div><div>Completed:</div><div>144</div></div>
  <div><div>Info hash:</div><div><kbd>0000000000000000000000000000000000002003</kbd></div></div>
</div></div>
<div id="torrent-description">Subtitles: Chinese (Traditional)</div>
<div class="torrent-file-list"><ul><li>Example S01E03.mkv <span class="file-size">(1.5 GiB)</span></li></ul></div>
"""


class FakeResponse:
    def __init__(self, payload: bytes, encoding: str | None = None) -> None:
        self.payload = payload
        self.headers = {"Content-Encoding": encoding} if encoding else {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class NyaaClientTests(unittest.TestCase):
    def test_search_normalizes_rss_result(self) -> None:
        seen: list[str] = []

        def opener(request: object, timeout: float) -> FakeResponse:
            seen.append(getattr(request, "full_url"))
            self.assertEqual(timeout, 7)
            return FakeResponse(RSS)

        client = NyaaClient(opener=opener)
        releases = client.search(NyaaSearchRequest("Example", timeout=7))

        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].nyaa_id, "2003")
        self.assertEqual(releases[0].seeders, 21)
        self.assertEqual(releases[0].size_bytes, 1610612736)
        self.assertTrue(releases[0].magnet.startswith("magnet:?xt=urn:btih:"))
        self.assertIn("page=rss", seen[0])
        self.assertIn("q=Example", seen[0])

    def test_search_normalizes_size_sorted_listing(self) -> None:
        client = NyaaClient(opener=lambda *_args, **_kwargs: FakeResponse(LISTING.encode()))
        request = NyaaSearchRequest(
            "Example", page=2, sort="size", order="desc", source="listing"
        )
        releases = client.search(request)

        self.assertEqual(releases[0].nyaa_id, "2003")
        self.assertEqual(releases[0].published_at, 1783641600)
        self.assertEqual(releases[0].category, "Anime - Non-English-translated")

    def test_get_returns_typed_detail_and_files(self) -> None:
        client = NyaaClient(opener=lambda *_args, **_kwargs: FakeResponse(DETAIL.encode()))
        detail = client.get("2003", timeout=5)

        self.assertEqual(detail.release.nyaa_id, "2003")
        self.assertEqual(detail.release.info_hash, "0000000000000000000000000000000000002003")
        self.assertIn("Traditional", detail.description)
        self.assertEqual(detail.files[0].name, "Example S01E03.mkv")
        self.assertEqual(detail.files[0].size_bytes, 1610612736)

    def test_get_rejects_detail_without_title(self) -> None:
        client = NyaaClient(opener=lambda *_args, **_kwargs: FakeResponse(b"<html></html>"))
        with self.assertRaises(NyaaParseError):
            client.get("2003")

    def test_empty_search_and_missing_optional_fields_are_not_network_errors(self) -> None:
        empty = parse_rss(b'<rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa"><channel /></rss>')
        self.assertEqual(empty, [])
        with self.assertRaises(NyaaParseError):
            parse_rss(b"<rss><channel>")

        damaged = RSS.replace(
            b"<nyaa:size>1.5 GiB</nyaa:size>", b"<nyaa:size>unknown</nyaa:size>"
        ).replace(
            b"<nyaa:seeders>21</nyaa:seeders>", b"<nyaa:seeders>?</nyaa:seeders>"
        ).replace(
            b"<nyaa:infoHash>0000000000000000000000000000000000002003</nyaa:infoHash>",
            b"",
        )
        release = parse_rss(damaged)[0]
        self.assertIsNone(release.size_bytes)
        self.assertEqual(release.seeders, 0)
        self.assertIsNone(release.info_hash)
        self.assertIsNone(release.magnet)

    def test_search_core_accepts_an_injected_fake_client(self) -> None:
        class FakeClient(NyaaClient):
            def __init__(self) -> None:
                self.requests: list[NyaaSearchRequest] = []

            def search(self, request: NyaaSearchRequest) -> list[NyaaRelease]:
                self.requests.append(request)
                return [
                    NyaaRelease(
                        nyaa_id="2003",
                        title="[Group] Example S01E03 [1080p]",
                        category="Anime - English-translated",
                        size="1.5 GiB",
                        size_bytes=1610612736,
                        published="Fri, 10 Jul 2026 00:00:00 +0000",
                        published_at=1783641600,
                        seeders=21,
                        leechers=3,
                        downloads=144,
                        url="https://nyaa.si/view/2003",
                        info_hash="0000000000000000000000000000000000002003",
                        magnet="magnet:?xt=urn:btih:0000000000000000000000000000000000002003",
                    )
                ]

        args = nyaa.parse_args(["Example", "--want-zh"])
        fake = FakeClient()
        candidates, failures, cache = core.collect_raw_candidates(args, client=fake)
        self.assertEqual(failures, [])
        self.assertEqual(cache, "miss")
        self.assertEqual(candidates[0].title, "[Group] Example S01E03 [1080p]")
        self.assertEqual(fake.requests[0].source, "rss")

    def test_http_failures_have_stable_error_types(self) -> None:
        def missing(request: object, timeout: float) -> FakeResponse:
            raise urllib.error.HTTPError(getattr(request, "full_url"), 404, "missing", {}, None)

        with self.assertRaises(NyaaNotFoundError):
            NyaaClient(opener=missing).get("2003")

        def timed_out(_request: object, timeout: float) -> FakeResponse:
            del timeout
            raise urllib.error.URLError(socket.timeout("slow"))

        with self.assertRaises(NyaaNetworkError):
            NyaaClient(opener=timed_out).search(NyaaSearchRequest("Example"))

    @unittest.skipUnless(os.environ.get("NYAA_ONLINE_SMOKE") == "1", "opt-in network smoke test")
    def test_online_search_smoke(self) -> None:
        releases = NyaaClient().search(NyaaSearchRequest("Example", timeout=8))
        self.assertIsInstance(releases, list)


if __name__ == "__main__":
    unittest.main()
