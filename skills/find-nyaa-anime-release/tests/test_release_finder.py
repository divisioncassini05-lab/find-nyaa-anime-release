from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import find_anime_release as finder
import airing_watch_state as watch_state
import release_search_core as core
import search_nyaa_releases as nyaa
from release_identity import EpisodeKind, normalize_season_number, parse_release_identity


def candidate(title: str, size: str, seeders: int) -> nyaa.Candidate:
    return nyaa.Candidate(
        rank=0,
        score=float(seeders),
        title=title,
        group=None,
        resolution="1080p",
        codec="AVC",
        bit_depth=None,
        audio_signal="unknown",
        subtitle_signal="not confirmed",
        size=size,
        size_bytes=nyaa.parse_size(size),
        size_basis="fixture",
        bitrate_note="fixture",
        tier_fit="in-tier",
        seeders=seeders,
        leechers=0,
        downloads=0,
        published="2026-07-10",
        category="Anime",
        url=f"https://example.test/{seeders}",
        magnet=None,
        matched_queries=["fixture"],
        reasons=[],
    )


def search_args() -> argparse.Namespace:
    return argparse.Namespace(
        query="Re:ZERO",
        alias=[],
        category="1_0",
        filter="0",
        tier="browse",
        season="S04",
        episode=None,
        duration_min=22.0,
        episodes=None,
        want_zh=False,
        require_zh=False,
        airing_priority=False,
        resolution=None,
        prefer_group=[],
        avoid_group=[],
        include_magnets=False,
        timeout=1,
        min_gib_per_episode=1.0,
        max_gib_per_episode=None,
        size_policy_source="tier",
        limit=1,
        inspect_details=False,
        detail_limit=0,
    )


def rss_item(title: str, size: str, seeders: int) -> dict[str, str]:
    item = nyaa.ET.Element("item")
    nyaa.ET.SubElement(item, "title").text = title
    nyaa.ET.SubElement(item, "link").text = f"https://nyaa.si/view/{seeders}"
    nyaa.ET.SubElement(item, "guid").text = f"https://nyaa.si/view/{seeders}"
    nyaa.ET.SubElement(item, "pubDate").text = "Fri, 10 Jul 2026 00:00:00 +0000"
    values = {
        "size": size,
        "seeders": str(seeders),
        "leechers": "0",
        "downloads": "1",
        "category": "Anime - Raw",
        "infoHash": f"{seeders:040x}",
    }
    for name, value in values.items():
        nyaa.ET.SubElement(item, f"{nyaa.NYAA_NS}{name}").text = value
    return {"query": "Yani Neko", "xml": nyaa.ET.tostring(item, encoding="unicode")}


class ReleaseIdentityTests(unittest.TestCase):
    def test_ordinal_season_decimal_special(self) -> None:
        identity = parse_release_identity(
            "[shincaps] Re:ZERO 4th season 11.5 SP01/SP02 [1920x1080].ts"
        )
        self.assertEqual(identity.season, 4)
        self.assertEqual(str(identity.episode), "11.5")
        self.assertIs(identity.kind, EpisodeKind.SPECIAL)
        self.assertIn("sp", identity.special_markers)

    def test_season_number_is_not_episode_number(self) -> None:
        identity = parse_release_identity("[Group] Re:ZERO Season 4 - 12 [1080p]")
        self.assertEqual(identity.season, 4)
        self.assertEqual(str(identity.episode), "12")
        self.assertIs(identity.kind, EpisodeKind.REGULAR)
        self.assertFalse(nyaa.looks_batch("[Group] Re:ZERO Season 4 - 12 [1080p]"))

    def test_bit_depth_is_not_an_episode_and_season_only_release_is_a_batch(self) -> None:
        cases = (
            "[THM] From the New World Season 1 (BD Remux 1080p x264 8-bit PCM) [Dual Audio]",
            "[Group] Atlas Chronicle Season 2 [BD 1080p HEVC 10-bit FLAC]",
        )
        for title in cases:
            with self.subTest(title=title):
                identity = parse_release_identity(title)
                self.assertIsNone(identity.episode)
                self.assertIs(identity.kind, EpisodeKind.BATCH)

    def test_technical_numbers_without_a_season_are_not_episodes(self) -> None:
        identity = parse_release_identity(
            "[Group] Atlas Chronicle [BD 1080p HEVC 10-bit FLAC 2.0 24fps]"
        )
        self.assertIsNone(identity.episode)
        self.assertIs(identity.kind, EpisodeKind.UNKNOWN)

    def test_explicit_episode_still_wins_when_bit_depth_is_present(self) -> None:
        identity = parse_release_identity(
            "[Group] Atlas Chronicle Season 2 - 12 [BD 1080p HEVC 10-bit]"
        )
        self.assertEqual(str(identity.episode), "12")
        self.assertIs(identity.kind, EpisodeKind.REGULAR)

    def test_generic_batch_ranges_and_multi_season_forms(self) -> None:
        cases = {
            "[Group] Atlas S1 [01-12] Complete": ((1,), "1", "12"),
            "[Group] Beacon E01-E24 Batch": ((), "1", "24"),
            "[Group] Cipher S1+S2 Complete": ((1, 2), None, None),
            "[Group] Delta S1~3 BDRip": ((1, 2, 3), None, None),
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                identity = parse_release_identity(title)
                self.assertIs(identity.kind, EpisodeKind.BATCH)
                self.assertEqual(identity.covered_seasons, expected[0])
                self.assertEqual(
                    str(identity.episode_start) if identity.episode_start is not None else None,
                    expected[1],
                )
                self.assertEqual(
                    str(identity.episode_end) if identity.episode_end is not None else None,
                    expected[2],
                )

    def test_volume_range_is_not_mistaken_for_episode_batch(self) -> None:
        identity = parse_release_identity("[Group] Echo Vol.1-3 BDMV")
        self.assertIsNot(identity.kind, EpisodeKind.BATCH)

    def test_cjk_season_forms(self) -> None:
        self.assertEqual(normalize_season_number("\u7b2c\u56db\u5b63"), 4)
        self.assertEqual(normalize_season_number("\u7b2c4\u671f"), 4)
        self.assertEqual(normalize_season_number("\u7b2c\u5341\u4e00\u5b63"), 11)
        identity = parse_release_identity("[Group] \u7b2c\u56db\u5b63 - 12 [1080p]")
        self.assertEqual(identity.season, 4)
        self.assertEqual(str(identity.episode), "12")

    def test_common_season_labels(self) -> None:
        for label in ("S04", "Season 4", "4th season", "IV"):
            with self.subTest(label=label):
                self.assertEqual(normalize_season_number(label), 4)


class TitleSelectionTests(unittest.TestCase):
    def test_detects_multiple_tracked_titles_in_one_request(self) -> None:
        state = {
            "shows": [
                {"title": "\u63cf\u7ed8\u76f4\u81f3\u751f\u547d\u5c3d\u5934", "aliases": []},
                {"title": "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973", "aliases": []},
                {"title": "\u5411\u65e5\u8475\u9a6c\u620f\u56e2", "aliases": []},
            ]
        }
        mentions = finder.detect_tracked_titles(
            state,
            "\u63cf\u7ed8\u76f4\u81f3\u751f\u547d\u5c3d\u5934\uff0c\u7a79\u5e90\u4e0b\u7684\u9b54\u5973\u548c\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
        )
        self.assertEqual([item["title"] for item in mentions], [show["title"] for show in state["shows"]])

    def test_multi_work_alias_is_rejected_and_sanitized(self) -> None:
        combined = "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973\u548c\u5411\u65e5\u8475\u9a6c\u620f\u56e2"
        first = {"title": "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973", "aliases": [combined]}
        second = {"title": "\u5411\u65e5\u8475\u9a6c\u620f\u56e2", "aliases": []}
        state = {"version": 1, "shows": [first, second]}
        removed = finder.sanitize_state_aliases(state)
        self.assertEqual(removed, [{"title": first["title"], "alias": combined}])
        self.assertNotIn(combined, first["aliases"])
        finder.upsert_show(
            state,
            first["title"],
            [combined],
            "S01",
            None,
            4,
            "fixture",
            show_hint=first,
        )
        self.assertNotIn(combined, first["aliases"])

    def test_bangumi_v0_infobox_provides_release_titles(self) -> None:
        fixtures = [
            (
                "\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                {
                    "id": 570583,
                    "name": "\u30b0\u30ed\u30a6\u30a2\u30c3\u30d7\u30b7\u30e7\u30a6",
                    "name_cn": "Grow Up Show \uff5e\u5411\u65e5\u8475\u9a6c\u620f\u56e2\uff5e",
                    "date": "2026-07-04",
                    "platform": "TV",
                    "infobox": [
                        {"key": "\u522b\u540d", "value": [{"v": "Grow Up Show: Himawari no Circus-dan"}]}
                    ],
                },
                ["Grow Up Show: Himawari no Circus-dan"],
            ),
            (
                "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973",
                {
                    "id": 552533,
                    "name": "\u5929\u5e55\u306e\u30b8\u30e3\u30fc\u30c9\u30a5\u30fc\u30ac\u30eb",
                    "name_cn": "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973",
                    "date": "2026-07-04",
                    "platform": "TV",
                    "infobox": [
                        {
                            "key": "\u522b\u540d",
                            "value": [
                                {"v": "Tenmaku no Jaadugar"},
                                {"k": "\u82f1\u6587\u540d", "v": "Jaadugar: A Witch in Mongolia"},
                            ],
                        }
                    ],
                },
                ["Tenmaku no Jaadugar", "Jaadugar: A Witch in Mongolia"],
            ),
            (
                "\u63cf\u7ed8\u76f4\u81f3\u751f\u547d\u5c3d\u5934",
                {
                    "id": 545917,
                    "name": "\u3053\u308c\u63cf\u3044\u3066\u6b7b\u306d",
                    "name_cn": "\u63cf\u7ed8\u76f4\u81f3\u751f\u547d\u5c3d\u5934",
                    "date": "2026-07-03",
                    "platform": "TV",
                    "infobox": [
                        {
                            "key": "\u522b\u540d",
                            "value": [{"v": "Kore Kaite Shine"}, {"v": "Draw This, Then Die!"}],
                        }
                    ],
                },
                ["Kore Kaite Shine", "Draw This, Then Die!"],
            ),
        ]
        for query, item, expected in fixtures:
            with self.subTest(query=query):
                resolved, _ = finder.bangumi_item_to_resolved(query, item, finder.date(2026, 7, 12))
                self.assertEqual(resolved.search_titles, expected)
                self.assertEqual(resolved.bangumi_id, item["id"])

    def test_preferred_nyaa_title_beats_chinese_display_title(self) -> None:
        selected = finder.select_search_names(
            "描绘直至生命尽头",
            ["描绘直至生命尽头", "Kore wo Kaite Shine"],
            2,
            ["Kore wo Kaite Shine"],
        )
        self.assertEqual(selected[0], "Kore wo Kaite Shine")
        self.assertNotIn("描绘直至生命尽头", selected)

    def test_damaged_metadata_alias_is_rejected_and_broad_title_is_protected(self) -> None:
        malformed = "ushoku Tensei: Jobless Reincarnation Season 3"
        complete = "Mushoku Tensei III: Isekai Ittara Honki Dasu"
        selected = finder.select_search_names(
            malformed,
            [complete],
            2,
            [malformed, complete],
        )
        self.assertNotIn(malformed, selected)
        self.assertIn(complete, selected)
        self.assertIn("Mushoku Tensei", selected)

    def test_successful_query_is_learned_as_preferred_nyaa_title(self) -> None:
        promoted = finder.promote_search_titles(
            ["Jaadugar: A Witch in Mongolia", "Tenmaku no Jaadugar"],
            ["Tenmaku no Jaadugar"],
        )
        self.assertEqual(promoted[0], "Tenmaku no Jaadugar")

    def test_strict_zh_queries_are_conditional_and_use_group_anchor(self) -> None:
        ordinary = finder.select_search_names(
            "穹庐下的魔女",
            ["穹庐下的魔女", "Tenmaku no Jaadugar"],
            2,
        )
        strict = finder.strict_zh_search_names(
            ordinary,
            "穹庐下的魔女",
            3,
            ["FixtureGroup"],
            ["穹廬下的魔女"],
        )
        self.assertEqual(ordinary, ["Tenmaku no Jaadugar"])
        self.assertIn("穹庐下的魔女", strict)
        self.assertIn("穹廬下的魔女", strict)
        self.assertIn("FixtureGroup Tenmaku 03", strict)
        self.assertIn("Tenmaku 03", strict)

    def test_flexible_strict_match_handles_macron_and_doubled_vowels(self) -> None:
        release = "[FixtureGroup] Tenmaku no Jādūgar - 03 [CHT]"
        self.assertFalse(core._contains_title(release, "Tenmaku no Jaadugar"))
        self.assertTrue(core._contains_title(release, "Tenmaku no Jaadugar", flexible=True))

    def test_state_keeps_display_aliases_separate_from_search_titles(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Grow Up Show: Sunflower Circus",
            aliases=["成长秀～向日葵马戏团～"],
            search_titles=["Grow Up Show Sunflower Circus"],
            trackable=True,
        )
        state = {"version": 1, "shows": []}
        show = finder.upsert_show(state, resolved.title, resolved.aliases, "S01", 1, 2, "fixture", resolved)
        restored = finder.resolved_from_state(show, "成长秀～向日葵马戏团～")
        self.assertEqual(restored.search_titles, ["Grow Up Show Sunflower Circus"])

    def test_romaji_alias_beats_mixed_cjk_alias(self) -> None:
        title = "Re:ZERO -Starting Life in Another World- Season 4"
        selected = finder.select_search_names(
            title,
            [
                "Re:Zero kara Hajimeru Isekai Seikatsu 4th Season",
                "Re:\u30bc\u30ed\u304b\u3089\u59cb\u3081\u308b\u7570\u4e16\u754c\u751f\u6d3b 4th season",
            ],
            2,
        )
        self.assertIn("Re:Zero kara Hajimeru Isekai Seikatsu 4th Season", selected)
        self.assertNotIn("Re:\u30bc\u30ed\u304b\u3089\u59cb\u3081\u308b\u7570\u4e16\u754c\u751f\u6d3b 4th season", selected)

    def test_infer_season_reuses_release_identity(self) -> None:
        self.assertEqual(finder.infer_season(["Example \u7b2c\u56db\u5b63"]), "S04")

    def test_curated_nickname_resolves_to_canonical_work(self) -> None:
        entry = finder.lookup_nickname_alias("\u5c3c\u53e4\u55b5\u55b5")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["canonical_title"], "Yani Neko")
        love_live_entry = finder.lookup_nickname_alias("\u59ae\u53ef\u59ae\u53ef\u59ae")
        self.assertEqual(love_live_entry["canonical_title"], "Love Live! School Idol Project")

    def test_side_story_does_not_turn_single_mainline_into_multiple_seasons(self) -> None:
        media = {
            "format": "TV",
            "relations": {
                "edges": [
                    {
                        "relationType": "ADAPTATION",
                        "node": {"type": "MANGA", "format": "MANGA"},
                    },
                    {
                        "relationType": "SIDE_STORY",
                        "node": {
                            "type": "ANIME",
                            "format": "ONA",
                            "title": {"romaji": "Yani Neko Mini"},
                            "synonyms": [],
                        },
                    },
                ]
            },
        }
        self.assertEqual(finder.mainline_scope_from_media(media), "single")
        self.assertIn("Yani Neko Mini", finder.related_anime_titles(media))

    def test_mainline_prequel_or_sequel_marks_multiple_seasons(self) -> None:
        media = {
            "format": "TV",
            "relations": {
                "edges": [
                    {
                        "relationType": "PREQUEL",
                        "node": {"type": "ANIME", "format": "TV"},
                    }
                ]
            },
        }
        self.assertEqual(finder.mainline_scope_from_media(media), "multi")

    def test_user_query_does_not_make_side_story_an_exact_title_match(self) -> None:
        main_media = {
            "id": 207141,
            "format": "TV",
            "status": "RELEASING",
            "title": {"english": "Chainsmoker Cat", "romaji": "Yani Neko", "native": "ヤニねこ"},
            "synonyms": [],
            "relations": {"edges": []},
        }
        mini_media = {
            "id": 208105,
            "format": "ONA",
            "status": "RELEASING",
            "title": {"english": None, "romaji": "Yani Neko Mini", "native": "ヤニねこ ミニ"},
            "synonyms": [],
            "relations": {"edges": []},
        }
        main, main_score = finder.media_to_resolved("Yani Neko", main_media, finder.date.today())
        mini, mini_score = finder.media_to_resolved("Yani Neko", mini_media, finder.date.today())
        self.assertGreater(main_score, mini_score + 6)
        self.assertEqual(main.mainline_scope, "single")
        self.assertEqual(main.season, "S01")
        self.assertEqual(mini.title, "Yani Neko Mini")


class SubtitleDetailTests(unittest.TestCase):
    def test_nested_nyaa_file_list_retains_directory_and_size(self) -> None:
        page = """
        <div class="torrent-file-list panel-body"><ul>
          <li><i class="fa fa-folder"></i> Atlas S01<ul>
            <li><i class="fa fa-file-o"></i> Atlas - 01.mkv <span class="file-size">(1.5 GiB)</span></li>
          </ul></li>
        </ul></div>
        """
        entries = nyaa.extract_nyaa_file_entries(page)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "Atlas S01/Atlas - 01.mkv")
        self.assertEqual(entries[0].size_bytes, nyaa.parse_size("1.5 GiB"))

    def test_cht_hardsub_is_verified_from_detail_page(self) -> None:
        page = """
        <h3 class="panel-title">[FixtureGroup] Tenmaku no Jādūgar - 03 [CHT][MP4]</h3>
        <div id="torrent-description">Torrent Info&#10;Subtitle:&#10;HardSub</div>
        <div class="torrent-file-list panel-body"><ul><li>[FixtureGroup] 穹廬下的魔女 - 03 [CHT].mp4</li></ul></div>
        """
        detail = nyaa.extract_nyaa_description(page)
        confirmed, signal = nyaa.detect_chinese_in_detail(detail)
        self.assertTrue(confirmed)
        self.assertIn("CHT", signal)

    def test_cht_hardsub_evidence_can_be_separated_across_the_detail_page(self) -> None:
        page = """
        <h3 class="panel-title">[FixtureGroup] Atlas Chronicle - 04 [CHT][MP4]</h3>
        <div id="torrent-description">
          Torrent Info<br>Source: Baha<br>Video: AVC<br>Audio: AAC<br>
          Container: MP4<br>Generated automatically<br>Subtitle:<br>HardSub
        </div>
        <div class="torrent-file-list panel-body"><ul>
          <li>[FixtureGroup] Atlas Chronicle - 04 [1080P][CHT].mp4</li>
        </ul></div>
        """
        confirmed, signal = nyaa.detect_chinese_in_detail(nyaa.extract_nyaa_description(page))
        self.assertTrue(confirmed)
        self.assertIn("CHT", signal)

    def test_generic_chinese_title_does_not_pair_with_page_level_hardsub(self) -> None:
        page = """
        <h3 class="panel-title">Chinese Example - 04</h3>
        <div id="torrent-description">Subtitle:<br>HardSub</div>
        <div class="torrent-file-list panel-body"><ul><li>Chinese Example - 04.mp4</li></ul></div>
        """
        confirmed, _ = nyaa.detect_chinese_in_detail(nyaa.extract_nyaa_description(page))
        self.assertFalse(confirmed)

    def test_cht_title_without_matching_subtitle_context_is_not_proof(self) -> None:
        page = """
        <h3 class="panel-title">Example - 03 [CHT]</h3>
        <div id="torrent-description">Subtitle: English</div>
        <div class="torrent-file-list panel-body"><ul><li>Example - 03.mkv</li></ul></div>
        """
        confirmed, _ = nyaa.detect_chinese_in_detail(nyaa.extract_nyaa_description(page))
        self.assertFalse(confirmed)

    def test_multisub_without_chinese_and_explicit_negation_fail(self) -> None:
        self.assertFalse(
            nyaa.detect_chinese_in_detail("Subtitle languages: English, German, Russian\nMultiSub")[0]
        )
        self.assertFalse(
            nyaa.detect_chinese_in_detail("Subtitle languages: English; no Chinese subtitles")[0]
        )

    def test_simplified_and_traditional_are_equally_accepted(self) -> None:
        simplified = nyaa.detect_chinese_in_detail("Subtitle languages: Simplified Chinese")[0]
        traditional = nyaa.detect_chinese_in_detail("Subtitle languages: Traditional Chinese")[0]
        self.assertTrue(simplified)
        self.assertTrue(traditional)

    def test_audio_language_and_explicit_none_are_not_chinese_subtitle_evidence(self) -> None:
        self.assertFalse(
            nyaa.detect_chinese_in_detail(
                "Audio language: Chinese\nSubtitle languages: English"
            )[0]
        )
        self.assertFalse(nyaa.detect_chinese_in_detail("Chinese subtitles: None")[0])

    def test_chinese_subtitle_file_and_mediainfo_text_track_are_evidence(self) -> None:
        self.assertTrue(nyaa.detect_chinese_in_detail("Subs/Example.zh-CN.ass")[0])
        self.assertTrue(nyaa.detect_chinese_in_detail("Text #1\nLanguage : Chinese")[0])
        self.assertFalse(nyaa.detect_chinese_in_detail("Audio #1\nLanguage : Chinese")[0])


class QualityTierTests(unittest.TestCase):
    def test_low_level_cli_defaults_to_browse(self) -> None:
        args = nyaa.parse_args(["Example"])
        self.assertEqual(args.tier, "browse")

    def test_tier_size_uses_actual_file_size_not_runtime(self) -> None:
        short_size = nyaa.parse_size("514.4 MiB")
        _, _, _, watch_fit = nyaa.bitrate_size_score(short_size, "watch", 12.0, None, False)
        _, _, _, browse_fit = nyaa.bitrate_size_score(short_size, "browse", 12.0, None, False)
        _, _, _, browse_good = nyaa.bitrate_size_score(nyaa.parse_size("1.5 GiB"), "browse", 12.0, None, False)
        _, _, _, watch_good = nyaa.bitrate_size_score(nyaa.parse_size("2.5 GiB"), "watch", 12.0, None, False)
        self.assertEqual(watch_fit, "below")
        self.assertEqual(browse_fit, "below")
        self.assertEqual(browse_good, "in-tier")
        self.assertEqual(watch_good, "in-tier")


class FailureReplyTests(unittest.TestCase):
    def test_single_episode_reports_an_above_range_release_without_details(self) -> None:
        reply = finder.render_failure_reply(
            "release_unqualified",
            "Yani Neko",
            "S01",
            core.SearchIntent.SPECIFIC_EPISODE,
            "browse",
            {
                "above_max_count": 1,
                "below_min_count": 1,
                "size_policy": {"source": "tier", "hard_min_gib": 1.0, "hard_max_gib": 2.0},
            },
        )
        self.assertEqual(reply, "《Yani Neko》当前区间内没有合格资源，但有高于该区间的资源可选。")
        self.assertNotIn("4.1 GiB", reply)
        self.assertNotIn("magnet:?", reply)

    def test_explicit_bounded_range_uses_the_same_above_range_message(self) -> None:
        reply = finder.render_failure_reply(
            "release_unqualified",
            "Example",
            "S01",
            core.SearchIntent.SPECIFIC_EPISODE,
            "browse",
            {
                "above_max_count": 2,
                "size_policy": {"source": "explicit", "hard_min_gib": 1.0, "hard_max_gib": 2.0},
            },
        )
        self.assertEqual(reply, "《Example》当前区间内没有合格资源，但有高于该区间的资源可选。")

    def test_below_only_or_unbounded_search_keeps_the_generic_message(self) -> None:
        diagnostics = (
            {"above_max_count": 0, "size_policy": {"hard_max_gib": 2.0}},
            {"above_max_count": 1, "size_policy": {"hard_max_gib": None}},
        )
        for diagnostic in diagnostics:
            with self.subTest(diagnostic=diagnostic):
                reply = finder.render_failure_reply(
                    "release_unqualified",
                    "Example",
                    "S01",
                    core.SearchIntent.SPECIFIC_EPISODE,
                    "browse",
                    diagnostic,
                )
                self.assertEqual(reply, "《Example》存在对应发布，但没有资源满足轻量观看档位。")

    def test_season_batch_does_not_use_the_above_range_message(self) -> None:
        reply = finder.render_failure_reply(
            "release_unqualified",
            "Example",
            "S01",
            core.SearchIntent.SEASON_BATCH,
            "browse",
            {"above_max_count": 1, "size_policy": {"hard_max_gib": 2.0}},
        )
        self.assertNotIn("有高于该区间的资源可选", reply)
        self.assertIn("正篇平均体积", reply)


class SearchReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.args = search_args()
        self.real_collect = core.collect_raw_candidates
        self.patcher = patch.object(core, "collect_raw_candidates")
        self.mock_collect = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_latest_target_beats_more_seeded_previous_episode(self) -> None:
        self.mock_collect.return_value = (
            [
                candidate("[A] Re:ZERO 4th season - 11 [1080p]", "1.4 GiB", 500),
                candidate("[B] Re:ZERO Season 4 - 12 [1080p]", "1.2 GiB", 1),
            ],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args, core.SearchIntent.LATEST_REGULAR, requested_episode=12
        )
        self.assertEqual(report.status, "found")
        self.assertIn("12", report.selected[0].candidate.title)

    def test_strict_zh_prefers_detail_verified_cht_over_unverified_multisub(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        self.args.detail_limit = 5
        erai = candidate("[Erai-raws] Re:ZERO S04E12 [MultiSub]", "1.5 GiB", 500)
        fixture_group = candidate("[FixtureGroup] Re:ZERO S04E12 [CHT]", "1.5 GiB", 10)
        self.mock_collect.return_value = ([erai, fixture_group], [], "miss")

        def detail_for(url: str, _timeout: int) -> str:
            if url.endswith("/10"):
                return "[FixtureGroup] Re:ZERO S04E12 [CHT]\nSubtitle:\nHardSub\n[CHT].mp4"
            return "[Erai-raws] Re:ZERO S04E12 [MultiSub]\nSubtitle languages: English, German"

        with patch.object(nyaa, "fetch_nyaa_detail_text", side_effect=detail_for):
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "found")
        self.assertIn("[FixtureGroup]", report.selected[0].candidate.title)
        self.assertTrue(report.selected[0].candidate.detail_chinese_confirmed)

    def test_strict_zh_failure_returns_no_candidate_or_magnet(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        self.args.detail_limit = 5
        release = candidate("[Erai-raws] Re:ZERO S04E12 [MultiSub]", "1.5 GiB", 500)
        release.magnet = "magnet:?xt=urn:btih:not-qualified"
        self.mock_collect.return_value = ([release], [], "miss")
        with patch.object(
            nyaa,
            "fetch_nyaa_detail_text",
            return_value="Subtitle languages: English, German, Russian",
        ):
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "subtitle_unqualified")
        self.assertEqual(report.selected, [])
        self.assertEqual(report.choices, [])

    def test_strict_zh_continues_beyond_first_detail_batch(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        self.args.detail_limit = 5
        releases = [
            candidate(f"[G] Re:ZERO S04E12 [1080p] v{index}", "1.5 GiB", 100 - index)
            for index in range(6)
        ]
        chinese_url = releases[-1].url
        self.mock_collect.return_value = (releases, [], "miss")

        def detail_for(url: str, _timeout: float) -> str:
            if url == chinese_url:
                return "Subtitle languages: Simplified Chinese"
            return "Subtitle languages: English"

        with patch.object(nyaa, "fetch_nyaa_detail_text", side_effect=detail_for):
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.url, chinese_url)
        self.assertEqual(report.diagnostics["detail_checked_count"], 6)
        self.assertEqual(report.diagnostics["subtitle_rejected_count"], 5)

    def test_strict_zh_budget_or_fetch_failure_is_incomplete_not_unqualified(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        self.args.detail_limit = 5
        self.args.detail_budget_seconds = 0
        release = candidate("[G] Re:ZERO S04E12 [1080p]", "1.5 GiB", 10)
        self.mock_collect.return_value = ([release], [], "miss")
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "subtitle_check_incomplete")
        self.assertTrue(report.diagnostics["detail_budget_exhausted"])
        self.assertEqual(report.diagnostics["detail_unchecked_count"], 1)

        self.args.detail_budget_seconds = 30
        with patch.object(nyaa, "fetch_nyaa_detail_text", side_effect=TimeoutError("slow")):
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "subtitle_check_incomplete")
        self.assertEqual(report.diagnostics["detail_failed_count"], 1)

    def test_strict_zh_query_failure_is_incomplete_not_unqualified(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        release = candidate("[G] Re:ZERO S04E12 [1080p]", "1.5 GiB", 10)
        self.mock_collect.return_value = ([release], ["alias query timed out"], "miss-partial")
        with patch.object(nyaa, "fetch_nyaa_detail_text", return_value="Subtitle: English"):
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "subtitle_check_incomplete")
        self.assertEqual(report.diagnostics["rss_failure_count"], 1)

    def test_strict_zh_cached_negative_refreshes_before_concluding(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        plain = candidate("[G] Re:ZERO S04E12 [1080p]", "1.5 GiB", 500)
        chinese = candidate("[ZH] Re:ZERO S04E12 [CHT]", "1.5 GiB", 10)
        chinese.subtitle_signal = "CHT"
        self.mock_collect.side_effect = [
            ([plain], [], "hit"),
            ([plain, chinese], [], "refresh"),
        ]

        def detail_for(url: str, _timeout: float) -> str:
            if url == chinese.url:
                return "[CHT]\nSubtitle:\nHardSub\nEpisode [CHT].mp4"
            return "Subtitle: English"

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(nyaa, "fetch_nyaa_detail_text", side_effect=detail_for),
        ):
            report = core.search_release_report(
                self.args,
                core.SearchIntent.SPECIFIC_EPISODE,
                requested_episode=12,
                cache_path=Path(temp_dir) / "raw.json",
            )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.url, chinese.url)
        self.assertTrue(report.diagnostics["strict_cache_refresh_used"])
        self.assertEqual(self.mock_collect.call_count, 2)

    def test_strict_zh_never_auto_selects_unknown_work_from_broad_query(self) -> None:
        self.args.require_zh = True
        self.args.want_zh = True
        self.args.inspect_details = True
        self.args.season = "S01"
        wrong = candidate("[G] Tenmaku Warriors S01E03 [CHT]", "1.5 GiB", 100)
        self.mock_collect.return_value = ([wrong], [], "miss")
        context = core.SearchContext(
            canonical_title="穹庐下的魔女",
            aliases=("穹廬下的魔女",),
            search_titles=("Tenmaku no Jaadugar",),
            mainline_scope="single",
            resolved_season=1,
            flexible_title_match=True,
        )
        with patch.object(nyaa, "fetch_nyaa_detail_text") as detail_fetch:
            report = core.search_release_report(
                self.args,
                core.SearchIntent.SPECIFIC_EPISODE,
                requested_episode=3,
                context=context,
            )
        self.assertEqual(report.status, "needs_confirmation")
        self.assertEqual(report.selected, [])
        self.assertEqual(report.diagnostics["work_unconfirmed_count"], 1)
        detail_fetch.assert_not_called()

    def test_soft_zh_preference_keeps_fast_path_without_detail_fetch(self) -> None:
        self.args.want_zh = True
        release = candidate("[Erai-raws] Re:ZERO S04E12 [MultiSub]", "1.5 GiB", 500)
        self.mock_collect.return_value = ([release], [], "miss")
        with patch.object(nyaa, "fetch_nyaa_detail_text") as detail_fetch:
            report = core.search_release_report(
                self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
            )
        self.assertEqual(report.status, "found")
        detail_fetch.assert_not_called()

    def test_special_conflict_requires_confirmation(self) -> None:
        self.mock_collect.return_value = (
            [
                candidate("[A] Re:ZERO 4th season - 11.5 SP01 [1080p]", "1.4 GiB", 500),
                candidate("[B] Re:ZERO Season 4 - 12 [1080p]", "1.2 GiB", 1),
            ],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args, core.SearchIntent.LATEST_REGULAR, requested_episode=12
        )
        self.assertEqual(report.status, "needs_confirmation")
        self.assertEqual(len(report.choices), 2)
        self.assertEqual(report.selected, [])

    def test_existing_but_small_release_is_not_missing(self) -> None:
        self.mock_collect.return_value = (
            [candidate("[B] Re:ZERO Season 4 - 12 [1080p]", "500 MiB", 1)],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.diagnostics["raw_count"], 1)

    def test_explicit_floor_overrides_named_tier_bounds(self) -> None:
        self.args.tier = "watch"
        self.args.min_gib_per_episode = 1.0
        self.args.size_policy_source = "explicit"
        low_tier = candidate("[B] Re:ZERO Season 4 - 12 [1080p]", "1.4 GiB", 1)
        low_tier.tier_fit = "below"
        self.mock_collect.return_value = ([low_tier], [], "miss")
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "found")
        self.assertEqual(len(report.selected), 1)

    def test_explicit_upper_bound_is_enforced(self) -> None:
        self.args.tier = "watch"
        self.args.min_gib_per_episode = 1.0
        self.args.max_gib_per_episode = 2.0
        self.args.size_policy_source = "explicit"
        self.mock_collect.return_value = (
            [candidate("[B] Re:ZERO Season 4 - 12 [1080p]", "4.1 GiB", 1)],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.diagnostics["above_max_count"], 1)

    def test_single_mainline_inherits_missing_season_and_excludes_related_work(self) -> None:
        self.args.query = "Yani Neko"
        self.args.season = "S01"
        self.args.tier = "watch"
        self.args.min_gib_per_episode = 1.0
        self.args.size_policy_source = "explicit"
        self.mock_collect.return_value = (
            [
                candidate("[DKB] Yani Neko - S01E02 [1080p]", "514.4 MiB", 262),
                candidate("[ToonsHub] Chainsmoker Cat S01E02 [1080p]", "866.1 MiB", 1192),
                candidate("[shincaps] Yani Neko - 02 (BS11 1920x1080 MPEG2 AAC).ts", "4.1 GiB", 9),
                candidate("[Group] Yani Neko Mini - 02 [1080p]", "5.0 GiB", 500),
            ],
            [],
            "miss",
        )
        context = core.SearchContext(
            canonical_title="Yani Neko",
            aliases=("Chainsmoker Cat", "ヤニねこ"),
            related_titles=("Yani Neko Mini",),
            mainline_scope="single",
            resolved_season=1,
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.SPECIFIC_EPISODE,
            requested_episode=2,
            context=context,
        )
        self.assertEqual(report.status, "found")
        self.assertIn("shincaps", report.selected[0].candidate.title)
        self.assertEqual(report.selected[0].effective_season, 1)
        self.assertEqual(report.selected[0].season_source, "single_mainline")
        self.assertEqual(report.diagnostics["related_work_count"], 1)
        self.assertEqual(report.diagnostics["observed_target_max_gib"], 4.1)

    def test_specific_current_title_beats_shared_related_short_title(self) -> None:
        self.args.query = "THE GHOST IN THE SHELL 2026"
        self.args.season = "S01"
        self.mock_collect.return_value = (
            [
                candidate(
                    "[Commie] The Ghost in the Shell - 02 [1080p]",
                    "1.7 GiB",
                    312,
                )
            ],
            [],
            "miss",
        )
        context = core.SearchContext(
            canonical_title="THE GHOST IN THE SHELL 2026",
            aliases=("The Ghost in the Shell",),
            search_titles=(
                "THE GHOST IN THE SHELL 2026",
                "THE GHOST IN THE SHELL",
            ),
            related_titles=(
                "Ghost in the Shell",
                "Ghost in the Shell: Stand Alone Complex",
            ),
            mainline_scope="single",
            resolved_season=1,
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.NEXT_TRACKED,
            requested_episode=2,
            context=context,
        )
        self.assertEqual(report.status, "found")
        selected = report.selected[0]
        self.assertEqual(selected.work_match, "alias")
        self.assertEqual(selected.work_match_evidence.decision, "positive_more_specific")
        self.assertEqual(report.diagnostics["related_work_count"], 0)
        self.assertEqual(report.diagnostics["wrong_season_count"], 0)
        self.assertNotIn("work_match_evidence", report.as_dict()["selected"][0])
        self.assertIn("work_match_evidence", report.as_dict(explain=True)["selected"][0])

    def test_more_specific_related_title_still_excludes_side_story(self) -> None:
        self.args.query = "Atlas Chronicle"
        self.args.season = "S01"
        self.mock_collect.return_value = (
            [
                candidate("[Group] Atlas Chronicle - 02 [1080p]", "1.5 GiB", 10),
                candidate("[Group] Atlas Chronicle Mini - 02 [1080p]", "1.5 GiB", 500),
            ],
            [],
            "miss",
        )
        context = core.SearchContext(
            canonical_title="Atlas Chronicle",
            related_titles=("Atlas Chronicle Mini",),
            mainline_scope="single",
            resolved_season=1,
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.SPECIFIC_EPISODE,
            requested_episode=2,
            context=context,
        )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.seeders, 10)
        self.assertEqual(report.diagnostics["related_work_count"], 1)
        self.assertEqual(report.diagnostics["wrong_season_count"], 0)

    def test_specific_legacy_title_beats_shared_current_alias(self) -> None:
        release = candidate(
            "[Group] Harbor Signal: Legacy Fleet S01E02 [1080p]",
            "1.5 GiB",
            100,
        )
        context = core.SearchContext(
            canonical_title="Harbor Signal 2026",
            aliases=("Harbor Signal",),
            related_titles=("Harbor Signal: Legacy Fleet",),
            mainline_scope="single",
            resolved_season=1,
        )
        evidence = core._work_match_evidence(release, context)
        self.assertEqual(evidence.outcome, "related_work")
        self.assertEqual(evidence.decision, "related_more_specific")

    def test_equal_positive_and_related_title_favors_current_target(self) -> None:
        release = candidate("[Group] Shared Chronicle S01E02 [1080p]", "1.5 GiB", 20)
        context = core.SearchContext(
            canonical_title="Shared Chronicle",
            related_titles=("Shared Chronicle",),
            resolved_season=1,
        )
        evidence = core._work_match_evidence(release, context)
        self.assertEqual(evidence.outcome, "canonical")
        self.assertEqual(evidence.decision, "positive_tie")

    def test_wrong_season_count_excludes_related_work(self) -> None:
        self.args.query = "Atlas Chronicle"
        self.args.season = "S01"
        self.mock_collect.return_value = (
            [
                candidate("[Group] Atlas Chronicle S02E02 [1080p]", "1.5 GiB", 10),
                candidate("[Group] Atlas Chronicle Mini S01E02 [1080p]", "1.5 GiB", 20),
            ],
            [],
            "miss",
        )
        context = core.SearchContext(
            canonical_title="Atlas Chronicle",
            related_titles=("Atlas Chronicle Mini",),
            resolved_season=1,
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.SPECIFIC_EPISODE,
            requested_episode=2,
            context=context,
        )
        self.assertEqual(report.status, "no_nyaa_release_for_target")
        self.assertEqual(report.diagnostics["related_work_count"], 1)
        self.assertEqual(report.diagnostics["wrong_season_count"], 1)

    def test_multi_mainline_does_not_infer_missing_season(self) -> None:
        self.args.query = "Example"
        self.args.season = "S02"
        self.mock_collect.return_value = (
            [candidate("[Group] Example - 02 [1080p]", "1.4 GiB", 10)],
            [],
            "miss",
        )
        context = core.SearchContext(
            canonical_title="Example",
            mainline_scope="multi",
            resolved_season=2,
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.SPECIFIC_EPISODE,
            requested_episode=2,
            context=context,
        )
        self.assertEqual(report.status, "needs_confirmation")
        self.assertEqual(report.selected, [])

    def test_watch_upper_bound_keeps_oversized_target_visible(self) -> None:
        self.args.query = "Yani Neko"
        self.args.season = "S01"
        self.args.tier = "watch"
        self.args.min_gib_per_episode = 2.0
        self.args.size_policy_source = "tier"
        self.mock_collect.return_value = (
            [candidate("[shincaps] Yani Neko - 02 [1920x1080].ts", "4.1 GiB", 9)],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args,
            core.SearchIntent.SPECIFIC_EPISODE,
            requested_episode=2,
            context=core.SearchContext(
                canonical_title="Yani Neko",
                mainline_scope="single",
                resolved_season=1,
            ),
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertIn("4.1 GiB", report.choices[0].candidate.size)
        self.assertEqual(report.diagnostics["above_max_count"], 1)
        self.assertEqual(report.diagnostics["observed_target_max_gib"], 4.1)

    def test_uncertain_candidates_get_one_targeted_fallback(self) -> None:
        self.mock_collect.side_effect = [
            ([candidate("[A] Re:ZERO 4th season complete [1080p]", "9.0 GiB", 30)], [], "miss"),
            ([candidate("[B] Re:ZERO S04E12 [1080p]", "1.2 GiB", 10)], [], "miss"),
        ]
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "found")
        self.assertTrue(report.diagnostics["fallback_query_used"])
        self.assertEqual(self.mock_collect.call_count, 2)

    def test_specific_target_never_falls_back_to_previous_regular_episode(self) -> None:
        self.mock_collect.return_value = (
            [candidate("[A] Re:ZERO Season 4 - 11 [1080p]", "1.4 GiB", 500)],
            [],
            "miss",
        )
        report = core.search_release_report(
            self.args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12
        )
        self.assertEqual(report.status, "no_nyaa_release_for_target")
        self.assertEqual(report.selected, [])

    def test_raw_cache_reuses_candidates(self) -> None:
        raw = [rss_item("[B] Re:ZERO Season 4 - 12 [1080p]", "1.2 GiB", 1)]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "raw.json"
            with patch.object(core.time, "time", return_value=1_000_000):
                core._write_cached_rss_items(cache, "fixture", raw)
                restored = core._read_cached_rss_items(cache, "fixture")
        self.assertIsNotNone(restored)
        self.assertEqual(restored[0]["xml"], raw[0]["xml"])

    def test_raw_cache_hit_skips_rss_fetch(self) -> None:
        raw = [rss_item("[B] Re:ZERO Season 4 - 12 [1080p]", "1.2 GiB", 1)]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "raw.json"
            with patch.object(core.time, "time", return_value=1_000_000):
                core._write_cached_rss_items(cache, core._raw_cache_key(self.args), raw)
                with patch.object(nyaa, "fetch_rss") as fetch:
                    restored, failures, cache_state = self.real_collect(self.args, cache)
        self.assertEqual(cache_state, "hit")
        self.assertEqual(failures, [])
        self.assertIn("Re:ZERO Season 4 - 12", restored[0].title)
        fetch.assert_not_called()

    def test_raw_cache_is_rescored_for_a_different_tier(self) -> None:
        raw = [rss_item("[B] Example S01E01 [1080p]", "1.5 GiB", 10)]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "raw.json"
            self.args.query = "Example"
            self.args.alias = []
            key = core._raw_cache_key(self.args)
            with patch.object(core.time, "time", return_value=1_000_000):
                core._write_cached_rss_items(cache, key, raw)
                browse, _, browse_cache = self.real_collect(self.args, cache)
                self.args.tier = "watch"
                watch, _, watch_cache = self.real_collect(self.args, cache)
        self.assertEqual((browse_cache, watch_cache), ("hit", "hit"))
        self.assertEqual(browse[0].tier_fit, "in-tier")
        self.assertEqual(watch[0].tier_fit, "below")

    def test_partial_multi_query_result_is_not_cached(self) -> None:
        item = rss_item("[B] Example S01E01 [1080p]", "1.5 GiB", 10)
        feed = f"<rss><channel>{item['xml']}</channel></rss>"
        self.args.query = "Example"
        self.args.alias = ["Example Alias"]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "raw.json"
            with patch.object(nyaa, "fetch_rss", side_effect=[feed, TimeoutError("slow")]):
                _, failures, cache_state = self.real_collect(self.args, cache)
            cached = core._read_cached_rss_items(cache, core._raw_cache_key(self.args))
        self.assertEqual(len(failures), 1)
        self.assertEqual(cache_state, "miss-partial")
        self.assertIsNone(cached)


class HybridWorkflowTests(unittest.TestCase):
    @staticmethod
    def nyaa_candidate(
        title: str,
        size: str,
        nyaa_id: int,
        seeders: int | None = None,
    ) -> nyaa.Candidate:
        release = candidate(title, size, seeders if seeders is not None else nyaa_id)
        release.url = f"https://nyaa.si/view/{nyaa_id}"
        release.magnet = f"magnet:?xt=urn:btih:{nyaa_id:040x}"
        return release

    def test_discovery_keeps_low_size_and_unverified_candidates_compact(self) -> None:
        args = search_args()
        args.query = "Example"
        args.alias = ["示例动画"]
        args.discover = True
        args.min_gib_per_episode = 1.0
        low = self.nyaa_candidate("[A] Example S01E04 [1080p]", "0.5 GiB", 101)
        unverified = self.nyaa_candidate(
            "[B] Example S01E04 [1080p][MultiSub]", "1.5 GiB", 102
        )
        with patch.object(
            core,
            "collect_raw_candidates",
            return_value=([low, unverified], [], "fixture"),
        ):
            report = core.discover_release_candidates(args)
        self.assertEqual(report["status"], "found")
        self.assertEqual(report["query_coverage"], "includes_latin_alias")
        self.assertEqual(report["ordering"], "published_desc_only_not_quality_rank")
        self.assertEqual(report["queries"], ["Example", "示例动画"])
        self.assertEqual({item["nyaa_id"] for item in report["candidates"]}, {"101", "102"})
        self.assertEqual(
            set(report["candidates"][0]),
            {
                "nyaa_id",
                "title",
                "identity",
                "size_gib",
                "seeders",
                "published",
                "matched_queries",
                "url",
            },
        )
        self.assertIn(0.5, [item["size_gib"] for item in report["candidates"]])
        self.assertNotIn("magnet", json.dumps(report, ensure_ascii=False))

    def test_read_only_probe_returns_tracked_next_episode_without_writing(self) -> None:
        state = {
            "version": 1,
            "shows": [
                {
                    "title": "二十世纪电气目录",
                    "aliases": ["Sparks of Tomorrow"],
                    "season": "S01",
                    "latest_known_episode": 3,
                    "next_episode": 4,
                    "airing": True,
                    "status": "airing",
                    "search_titles": ["20th Century Electricity Catalogue"],
                    "verified_search_titles": ["Sparks of Tomorrow"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "airing.json"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False),
                encoding="utf-8",
            )
            before = state_path.read_bytes()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                return_code = watch_state.main(
                    ["--state", str(state_path), "probe", "二十世纪电气目录"]
                )
            after = state_path.read_bytes()
        payload = json.loads(output.getvalue())
        self.assertEqual(return_code, 0)
        self.assertTrue(payload["tracked"])
        self.assertEqual(payload["latest_known_episode"], 3)
        self.assertEqual(payload["next_episode"], 4)
        self.assertEqual(payload["verified_search_titles"], ["Sparks of Tomorrow"])
        self.assertEqual(before, after)

    def test_default_one_gib_floor_rejects_sub_one_gib_release(self) -> None:
        args = search_args()
        args.query = "Sparks of Tomorrow"
        args.season = "S01"
        args.episode = 3
        args.size_policy_source = "explicit"
        args.min_gib_per_episode = 1.0
        too_small = self.nyaa_candidate(
            "[Group] Sparks of Tomorrow S01E03 [1080p][CHS]",
            "677.8 MiB",
            3001,
            seeders=142,
        )
        with patch.object(
            core,
            "collect_raw_candidates",
            return_value=([too_small], [], "fixture"),
        ):
            report = core.search_release_report(
                args,
                core.SearchIntent.SPECIFIC_EPISODE,
                requested_episode=3,
            )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.selected, [])
        self.assertEqual(report.diagnostics["below_min_count"], 1)

    def test_cli_rejects_sub_one_gib_floor_without_explicit_override(self) -> None:
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            return_code = nyaa.main(
                ["Example", "--min-gib-per-episode", "0", "--report"]
            )
        self.assertEqual(return_code, 2)
        self.assertIn("--allow-sub-1g", errors.getvalue())

    def test_cjk_only_discovery_is_explicitly_provisional(self) -> None:
        args = search_args()
        args.query = "向日葵马戏团"
        args.alias = []
        args.discover = True
        episode_one = self.nyaa_candidate(
            "[Group] Grow Up Show - Himawari no Circus-dan - 01 [简体]",
            "0.6 GiB",
            2130661,
            seeders=34,
        )
        with patch.object(
            core,
            "collect_raw_candidates",
            return_value=([episode_one], [], "fixture"),
        ):
            report = core.discover_release_candidates(args)
        self.assertEqual(report["status"], "found")
        self.assertEqual(report["query_coverage"], "cjk_only_provisional")
        self.assertEqual(report["candidates"][0]["identity"]["episode"], "1")

    def test_mushoku_broad_discovery_verifies_2135067_from_shared_cache(self) -> None:
        malformed = "ushoku Tensei: Jobless Reincarnation Season 3"
        complete = "Mushoku Tensei III: Isekai Ittara Honki Dasu"
        queries = finder.select_search_names(
            malformed,
            [complete],
            2,
            [malformed, complete],
        )
        self.assertIn("Mushoku Tensei", queries)
        item = rss_item(
            "[Feibanyama] Mushoku Tensei Jobless Reincarnation S03E04 "
            "[IQIYI WebRip 2160p NVENC AAC Multi-Subs]",
            "1.9 GiB",
            2135067,
        )
        populated_feed = f"<rss><channel>{item['xml']}</channel></rss>"
        empty_feed = "<rss><channel /></rss>"

        def feed_for(query: str, *_args: object) -> str:
            return populated_feed if query == "Mushoku Tensei" else empty_feed

        args = search_args()
        args.query = queries[0]
        args.alias = queries[1:]
        args.season = "S03"
        args.episode = 4
        args.discover = True
        args.size_policy_source = "explicit"
        args.min_gib_per_episode = 1.0
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "rss.json"
            with patch.object(nyaa, "fetch_rss", side_effect=feed_for) as fetch:
                discovery = core.discover_release_candidates(args, cache_path=cache_path)
                self.assertIn(
                    "2135067", {entry["nyaa_id"] for entry in discovery["candidates"]}
                )
                fetch.reset_mock()
                args.discover = False
                args.candidate_id = ["2135067"]
                args.require_zh = True
                args.want_zh = True
                args.inspect_details = True
                args.detail_limit = 5
                args.include_magnets = True
                with patch.object(
                    nyaa,
                    "fetch_nyaa_detail_text",
                    return_value=(
                        "Subtitle languages: Simplified Chinese, Traditional Chinese"
                    ),
                ):
                    verified = core.search_release_report(
                        args,
                        core.SearchIntent.SPECIFIC_EPISODE,
                        requested_episode=4,
                        cache_path=cache_path,
                    )
                fetch.assert_not_called()
        self.assertEqual(verified.status, "found")
        payload = verified.as_dict(explain=True)
        self.assertEqual(payload["selected"][0]["nyaa_id"], "2135067")
        self.assertTrue(payload["selected"][0]["detail_chinese_confirmed"])
        self.assertTrue(payload["selected"][0]["magnet"].startswith("magnet:?"))

    def test_representative_shortlist_beats_newest_small_release(self) -> None:
        args = search_args()
        args.query = "Grow Up Show"
        args.alias = ["Grow Up Show: Sunflower Circus"]
        args.season = "S01"
        args.episode = 3
        args.discover = True
        args.size_policy_source = "explicit"
        args.min_gib_per_episode = 0.0
        args.require_zh = True
        args.want_zh = True
        args.inspect_details = True
        args.detail_limit = 5
        args.include_magnets = True
        small_newest = self.nyaa_candidate(
            "[Gecko] Grow Up Show S01E03 [1080p][M-SUB]",
            "707 MiB",
            2135586,
            seeders=5,
        )
        small_newest.published = "2026-07-21"
        balanced_older = self.nyaa_candidate(
            "[VARYG] Grow Up Show S01E03 [1080p][Multi-Subs]",
            "1.4 GiB",
            2134348,
            seeders=41,
        )
        balanced_older.published = "2026-07-18"
        releases = [small_newest, balanced_older]

        with patch.object(
            core,
            "collect_raw_candidates",
            return_value=(releases, [], "fixture"),
        ):
            discovery = core.discover_release_candidates(args)
        self.assertEqual(discovery["candidates"][0]["nyaa_id"], "2135586")
        self.assertEqual(discovery["ordering"], "published_desc_only_not_quality_rank")

        args.discover = False
        args.candidate_id = ["2135586", "2134348"]
        with (
            patch.object(
                core,
                "collect_raw_candidates",
                return_value=(releases, [], "fixture"),
            ),
            patch.object(
                nyaa,
                "fetch_nyaa_detail_text",
                return_value="Subtitle languages: Simplified Chinese",
            ) as details,
        ):
            report = core.search_release_report(
                args,
                core.SearchIntent.SPECIFIC_EPISODE,
                requested_episode=3,
            )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.url, balanced_older.url)
        details.assert_called_once_with(balanced_older.url, args.timeout)

    def test_skill_forbids_first_row_only_selection_when_alternatives_exist(self) -> None:
        skill_text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "Never select the first row merely because it is first.",
            skill_text,
        )
        self.assertIn(
            "Verify only one ID only when it is the sole plausible release.",
            skill_text,
        )
        self.assertIn(
            "Never declare a latest episode from a CJK-only discovery.",
            skill_text,
        )
        self.assertIn(
            "Always run a read-only local-state probe",
            skill_text,
        )
        self.assertIn(
            "The default hard floor is 1 GiB",
            skill_text,
        )
        self.assertNotIn("--min-gib-per-episode 0", skill_text)

    def test_candidate_id_rejects_multisub_only_and_hides_magnet(self) -> None:
        args = search_args()
        args.query = "Mushoku Tensei"
        args.season = "S03"
        args.episode = 4
        args.candidate_id = ["2135076"]
        args.require_zh = True
        args.want_zh = True
        args.inspect_details = True
        args.detail_limit = 5
        args.include_magnets = True
        release = self.nyaa_candidate(
            "[Erai-raws] Mushoku Tensei III S03E04 [1080p][MultiSub]",
            "1.4 GiB",
            2135076,
        )
        with (
            patch.object(
                core,
                "collect_raw_candidates",
                return_value=([release], [], "fixture"),
            ),
            patch.object(
                nyaa,
                "fetch_nyaa_detail_text",
                return_value="Subtitle languages: English, German, Russian; MultiSub",
            ),
        ):
            report = core.search_release_report(
                args,
                core.SearchIntent.SPECIFIC_EPISODE,
                requested_episode=4,
            )
        self.assertEqual(report.status, "subtitle_unqualified")
        self.assertNotIn("magnet:?", json.dumps(report.as_dict(explain=True)))

    def test_ghost_in_the_shell_2026_is_not_mixed_with_sac_or_movie(self) -> None:
        args = search_args()
        args.query = "Ghost in the Shell"
        args.season = "S01"
        current = self.nyaa_candidate(
            "[A] Ghost in the Shell 2026 S01E04 [1080p]", "1.5 GiB", 201
        )
        sac = self.nyaa_candidate(
            "[B] Ghost in the Shell Stand Alone Complex S02E26 [1080p]",
            "1.5 GiB",
            202,
        )
        movie = self.nyaa_candidate(
            "[C] Ghost in the Shell 1995 Movie [1080p]", "8.0 GiB", 203
        )
        context = core.SearchContext(
            canonical_title="Ghost in the Shell 2026",
            aliases=("The Ghost in the Shell 2026",),
            related_titles=(
                "Ghost in the Shell Stand Alone Complex",
                "Ghost in the Shell 1995 Movie",
            ),
            resolved_season=1,
        )
        with patch.object(
            core,
            "collect_raw_candidates",
            return_value=([current, sac, movie], [], "fixture"),
        ):
            report = core.search_release_report(
                args,
                core.SearchIntent.LATEST_REGULAR,
                context=context,
            )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.url, current.url)
        self.assertEqual(report.diagnostics["related_work_count"], 2)

    def test_low_level_discovery_does_not_call_metadata_or_tracking_state(self) -> None:
        payload = {
            "status": "no_rss_candidates",
            "queries": ["Example"],
            "candidates": [],
            "failures": [],
            "cache": "fixture",
        }
        output = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.object(core, "discover_release_candidates", return_value=payload),
            patch.object(finder, "resolve_work_identity") as metadata,
            patch.object(finder, "save_state") as save_state,
            contextlib.redirect_stdout(output),
        ):
            return_code = nyaa.main(
                ["Example", "--discover", "--cache", str(Path(temp_dir) / "rss.json")]
            )
        self.assertEqual(return_code, 4)
        self.assertEqual(json.loads(output.getvalue())["queries"], ["Example"])
        metadata.assert_not_called()
        save_state.assert_not_called()


class HighLevelStateTests(unittest.TestCase):
    def test_main_reports_above_range_availability_without_candidate_details(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example",
            search_titles=["Example"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            status="FINISHED",
        )
        oversized = candidate("[Group] Example S01E01 Oversized", "4.1 GiB", 9)
        oversized.magnet = "magnet:?xt=urn:btih:oversized"
        oversized_item = core.ClassifiedCandidate(
            oversized,
            parse_release_identity(oversized.title),
            "match",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="release_unqualified",
            selected=[],
            choices=[oversized_item],
            diagnostics={
                "above_max_count": 1,
                "below_min_count": 1,
                "size_policy": {
                    "source": "explicit",
                    "hard_min_gib": 1.0,
                    "hard_max_gib": 2.0,
                },
            },
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=report),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example",
                        "--season",
                        "S01",
                        "--episode",
                        "1",
                        "--min-gib-per-episode",
                        "1",
                        "--max-gib-per-episode",
                        "2",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["reply_text"],
            "《Example》当前区间内没有合格资源，但有高于该区间的资源可选。",
        )
        self.assertNotIn("Oversized", payload["reply_text"])
        self.assertNotIn("4.1 GiB", payload["reply_text"])
        self.assertNotIn("magnet:?", payload["reply_text"])

    def test_unique_tracked_title_uses_state_before_identity_resolvers(self) -> None:
        no_release = core.ReleaseSearchReport(
            intent=core.SearchIntent.NEXT_TRACKED,
            requested_season=1,
            requested_episode=2,
            status="no_nyaa_release_for_target",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "\u653b\u58f3\u673a\u52a8\u961f",
                            "aliases": ["The Ghost in the Shell"],
                            "search_titles": [
                                "THE GHOST IN THE SHELL 2026",
                                "THE GHOST IN THE SHELL",
                            ],
                            "season": "S01",
                            "latest_known_episode": 1,
                            "next_episode": 2,
                            "airing": True,
                            "format": "TV",
                            "anilist_id": 177699,
                            "mainline_scope": "single",
                        }
                    ],
                },
            )
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_bangumi_title") as bangumi,
                patch.object(finder, "resolve_title") as anilist,
                patch.object(
                    finder,
                    "hydrate_airing_metadata",
                    side_effect=lambda resolved, *_: (resolved, "fixture"),
                ),
                patch.object(finder, "search_release_report", return_value=no_release) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u653b\u58f3\u673a\u52a8\u961f",
                        "--json",
                        "--no-state-update",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                        "--schedule-cache",
                        str(root / "schedule.json"),
                    ]
                )
            payload = json.loads(output.getvalue())

        self.assertEqual(payload["identity_status"], "resolved")
        self.assertEqual(payload["resolver"], "state_hit")
        self.assertEqual(payload["target_episode"], 2)
        self.assertEqual(search.call_args.kwargs["intent"], core.SearchIntent.NEXT_TRACKED)
        self.assertEqual(search.call_args.kwargs["requested_episode"], 2)
        context = search.call_args.kwargs["context"]
        self.assertEqual(context.search_titles[0], "THE GHOST IN THE SHELL 2026")
        bangumi.assert_not_called()
        anilist.assert_not_called()

    def test_auto_batch_returns_each_title_with_complete_magnet_reply(self) -> None:
        def found_report(title: str, episode: int, magnet: str) -> core.ReleaseSearchReport:
            release = candidate(f"[Group] {title} S01E{episode:02d} [1080p]", "1.4 GiB", 20)
            release.magnet = magnet
            release.matched_queries = [title]
            item = core.ClassifiedCandidate(
                release,
                parse_release_identity(release.title),
                "match",
                effective_season=1,
                season_source="title",
            )
            return core.ReleaseSearchReport(
                intent=core.SearchIntent.NEXT_TRACKED,
                requested_season=1,
                requested_episode=episode,
                status="found",
                selected=[item],
                choices=[],
                diagnostics={"raw_count": 1, "size_policy": {}},
                failures=[],
                cache="miss",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973",
                            "aliases": [],
                            "search_titles": ["Tenmaku no Jaadugar"],
                            "verified_search_titles": ["Tenmaku no Jaadugar"],
                            "season": "S01",
                            "next_episode": 3,
                            "airing": True,
                        },
                        {
                            "title": "\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                            "aliases": [],
                            "search_titles": ["Grow Up Show"],
                            "verified_search_titles": ["Grow Up Show"],
                            "season": "S01",
                            "next_episode": 2,
                            "airing": True,
                        },
                    ],
                },
            )
            output = io.StringIO()
            reports = [
                found_report("Tenmaku no Jaadugar", 3, "magnet:?xt=urn:btih:witch"),
                found_report("Grow Up Show", 2, "magnet:?xt=urn:btih:sunflower"),
            ]
            with (
                patch.object(finder, "search_release_report", side_effect=reports) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u7a79\u5e90\u4e0b\u7684\u9b54\u5973\u548c\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-web-resolve",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "batch")
        self.assertEqual(len(payload["results"]), 2)
        self.assertIn("magnet:?xt=urn:btih:witch", payload["reply_text"])
        self.assertIn("magnet:?xt=urn:btih:sunflower", payload["reply_text"])
        self.assertTrue(payload["output_contract"]["ready"])
        self.assertEqual([call.args[0].query for call in search.call_args_list], ["Tenmaku no Jaadugar", "Grow Up Show"])

    def test_missing_requested_magnet_is_output_incomplete(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example Anime",
            search_titles=["Example Anime"],
            season="S01",
            source="anilist",
        )
        release = candidate("[Group] Example Anime S01E01 [1080p]", "1.4 GiB", 10)
        item = core.ClassifiedCandidate(
            release,
            parse_release_identity(release.title),
            "match",
            effective_season=1,
            season_source="title",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={"raw_count": 1, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=report),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example Anime",
                        "--episode",
                        "1",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "output_incomplete")
        self.assertEqual(payload["output_contract"]["missing_fields"], ["magnet"])
        self.assertIn("缺少必要字段", payload["reply_text"])

    def test_strict_zh_failure_does_not_advance_tracked_progress(self) -> None:
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=3,
            status="subtitle_unqualified",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 2, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "穹庐下的魔女",
                            "aliases": ["Tenmaku no Jaadugar"],
                            "search_titles": ["Tenmaku no Jaadugar"],
                            "season": "S01",
                            "latest_known_episode": 2,
                            "next_episode": 3,
                            "airing": True,
                        }
                    ],
                },
            )
            output = io.StringIO()
            with (
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "穹庐下的魔女",
                        "--episode",
                        "3",
                        "--require-zh",
                        "--release-group-hint",
                        "FixtureGroup",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-web-resolve",
                        "--json",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
            saved = finder.load_state(state_path)["shows"][0]
        payload = json.loads(output.getvalue())
        search_args_value = search.call_args.args[0]
        self.assertEqual(payload["status"], "subtitle_unqualified")
        self.assertIn("未确认带有中文字幕", payload["reply_text"])
        self.assertEqual(payload["state_update"], "tracked_waiting")
        self.assertEqual((saved["latest_known_episode"], saved["next_episode"]), (2, 3))
        self.assertTrue(search_args_value.require_zh)
        self.assertTrue(search_args_value.inspect_details)
        self.assertEqual(search_args_value.prefer_group, ["FixtureGroup"])

    def test_chinese_state_without_search_titles_is_enriched_before_nyaa(self) -> None:
        bangumi = finder.ResolvedAnime(
            title="Grow Up Show: Himawari no Circus-dan",
            aliases=["\u5411\u65e5\u8475\u9a6c\u620f\u56e2"],
            search_titles=["Grow Up Show: Himawari no Circus-dan", "Grow Up Show Sunflower Circus"],
            season="S01",
            current=True,
            trackable=True,
            source="bangumi",
            format="TV",
            status="RELEASING",
            bangumi_id=570583,
            anilist_id=999,
        )
        selected_candidate = candidate(
            "[Erai-raws] Grow Up Show: Himawari no Circus-dan - 02 [1080p]",
            "1.4 GiB",
            20,
        )
        selected_candidate.matched_queries = ["Grow Up Show Sunflower Circus"]
        item = core.ClassifiedCandidate(
            selected_candidate,
            parse_release_identity(selected_candidate.title),
            "match",
            effective_season=1,
            season_source="single_mainline",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.NEXT_TRACKED,
            requested_season=1,
            requested_episode=2,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={"raw_count": 1, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                            "aliases": [],
                            "season": "S01",
                            "next_episode": 2,
                            "airing": True,
                        },
                        {
                            "title": "Grow Up Show: Himawari no Circus-dan",
                            "aliases": [],
                            "season": "S01",
                            "next_episode": 2,
                            "airing": True,
                            "anilist_id": 999,
                        },
                    ],
                },
            )
            output = io.StringIO()
            failed_anilist = finder.ResolvedAnime(title="fixture", source="anilist unavailable")
            with (
                patch.object(finder, "resolve_bangumi_title", return_value=("resolved", bangumi)),
                patch.object(finder, "resolve_title", return_value=("resolver_failed", failed_anilist)),
                patch.object(finder, "hydrate_airing_metadata", return_value=(bangumi, "unavailable")),
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                        "--json",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
            payload = json.loads(output.getvalue())
            saved_state = finder.load_state(state_path)
            saved = saved_state["shows"][0]
        search_args = search.call_args.args[0]
        self.assertEqual(search_args.query, "Grow Up Show: Himawari no Circus-dan")
        self.assertNotIn("\u5411\u65e5\u8475\u9a6c\u620f\u56e2", [search_args.query, *search_args.alias])
        self.assertEqual(saved["search_titles"][0], "Grow Up Show Sunflower Circus")
        self.assertEqual(saved["verified_search_titles"], ["Grow Up Show Sunflower Circus"])
        self.assertEqual(saved["bangumi_id"], 570583)
        self.assertEqual(len(saved_state["shows"]), 1)
        self.assertIn("Grow Up Show: Himawari no Circus-dan", saved["aliases"])
        self.assertEqual(payload["identity_sources"][:2], ["state", "bangumi"])

    def test_authoritative_failure_requests_web_without_searching_chinese_nyaa(self) -> None:
        failed = finder.ResolvedAnime(title="\u672a\u77e5\u4e2d\u6587\u756a", source="no result")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_bangumi_title", return_value=("resolver_failed", failed)),
                patch.object(finder, "resolve_title", return_value=("resolver_failed", failed)),
                patch.object(finder, "search_release_report") as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u672a\u77e5\u4e2d\u6587\u756a",
                        "--json",
                        "--no-state-update",
                        "--state",
                        str(root / "state.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "needs_web_resolution")
        self.assertEqual(payload["search_titles"], [])
        search.assert_not_called()

    def test_search_title_web_override_bypasses_incomplete_chinese_identity(self) -> None:
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=2,
            status="no_nyaa_release_for_target",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_bangumi_title") as bangumi,
                patch.object(finder, "resolve_title") as anilist,
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u5411\u65e5\u8475\u9a6c\u620f\u56e2",
                        "--episode",
                        "2",
                        "--search-title",
                        "Grow Up Show: Himawari no Circus-dan",
                        "--no-web-resolve",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(search.call_args.args[0].query, "Grow Up Show: Himawari no Circus-dan")
        self.assertEqual(payload["status"], "no_nyaa_release_for_target")
        self.assertIn("web", payload["identity_sources"])
        bangumi.assert_not_called()
        anilist.assert_not_called()

    def test_unverified_no_rss_requests_one_web_title_retry(self) -> None:
        no_rss = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=2,
            status="no_rss_candidates",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0},
            failures=[],
            cache="miss",
        )
        resolved = finder.ResolvedAnime(
            title="Example Anime",
            search_titles=["Example Anime"],
            season="S01",
            source="anilist",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=no_rss),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example Anime",
                        "--episode",
                        "2",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "needs_web_resolution")
        self.assertEqual(payload["diagnostic"]["provisional_status"], "no_rss_candidates")

    def test_verified_search_title_does_not_repeat_web_resolution(self) -> None:
        no_rss = core.ReleaseSearchReport(
            intent=core.SearchIntent.NEXT_TRACKED,
            requested_season=1,
            requested_episode=3,
            status="no_rss_candidates",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "Example Anime",
                            "aliases": [],
                            "search_titles": ["Example Anime"],
                            "verified_search_titles": ["Example Anime"],
                            "season": "S01",
                            "next_episode": 3,
                            "airing": True,
                        }
                    ],
                },
            )
            output = io.StringIO()
            with (
                patch.object(finder, "hydrate_airing_metadata", side_effect=lambda resolved, *_: (resolved, "hit")),
                patch.object(finder, "search_release_report", return_value=no_rss),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example Anime",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(state_path),
                    ]
                )
        self.assertEqual(json.loads(output.getvalue())["status"], "no_rss_candidates")

    def test_single_mainline_result_advances_progress_and_persists_context(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Chainsmoker Cat",
            aliases=["Yani Neko", "ヤニねこ"],
            season="S01",
            current=True,
            trackable=True,
            source="fixture",
            format="TV",
            status="RELEASING",
            anilist_id=207141,
            mainline_scope="single",
            related_titles=["Yani Neko Mini"],
        )
        item = core.ClassifiedCandidate(
            candidate("[shincaps] Yani Neko - 02 [1920x1080].ts", "4.1 GiB", 9),
            parse_release_identity("[shincaps] Yani Neko - 02 [1920x1080].ts"),
            "match",
            effective_season=1,
            season_source="single_mainline",
            work_match="alias",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=2,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={
                "raw_count": 1,
                "size_policy": {
                    "source": "explicit",
                    "hard_min_gib": 1.0,
                    "hard_max_gib": None,
                },
            },
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Yani Neko",
                        "--season",
                        "S01",
                        "--episode",
                        "2",
                        "--tier",
                        "watch",
                        "--min-gib-per-episode",
                        "1",
                        "--json",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                        "--schedule-cache",
                        str(root / "schedule.json"),
                    ]
                )
            payload = json.loads(output.getvalue())
            saved = finder.load_state(state_path)["shows"][0]
        context = search.call_args.kwargs["context"]
        self.assertEqual(payload["selected"]["season_source"], "single_mainline")
        self.assertEqual(saved["latest_known_episode"], 2)
        self.assertEqual(saved["next_episode"], 3)
        self.assertEqual(saved["mainline_scope"], "single")
        self.assertIn("Yani Neko Mini", saved["related_titles"])
        self.assertEqual(context.mainline_scope, "single")

    def test_watch_falls_back_to_browse_when_no_custom_floor_was_given(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example",
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            status="FINISHED",
        )
        primary = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="release_unqualified",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 1},
            failures=[],
            cache="miss",
        )
        fallback_item = core.ClassifiedCandidate(
            candidate("[Group] Example S01E01 [1080p]", "1.4 GiB", 10),
            parse_release_identity("[Group] Example S01E01 [1080p]"),
            "match",
        )
        fallback = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="found",
            selected=[fallback_item],
            choices=[],
            diagnostics={"raw_count": 1},
            failures=[],
            cache="hit",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", side_effect=[primary, fallback]) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example",
                        "--season",
                        "S01",
                        "--episode",
                        "1",
                        "--tier",
                        "watch",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        first_args = search.call_args_list[0].args[0]
        second_args = search.call_args_list[1].args[0]
        self.assertEqual(search.call_count, 2)
        self.assertEqual((first_args.tier, first_args.min_gib_per_episode), ("watch", 2.0))
        self.assertEqual((second_args.tier, second_args.min_gib_per_episode), ("browse", 1.0))
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["quality"]["fallback"], {"from": "watch", "to": "browse", "status": "found"})

    def test_soft_chinese_preference_never_downgrades_a_valid_watch_release(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example",
            search_titles=["Example"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            status="FINISHED",
        )
        watch_candidate = candidate("[Group] Example S01E01 [1080p]", "2.5 GiB", 10)
        watch_candidate.subtitle_signal = "not confirmed"
        watch_item = core.ClassifiedCandidate(
            watch_candidate,
            parse_release_identity(watch_candidate.title),
            "match",
            effective_season=1,
            season_source="title",
            work_match="search_title",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="found",
            selected=[watch_item],
            choices=[],
            diagnostics={"raw_count": 1, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example",
                        "--season",
                        "S01",
                        "--episode",
                        "1",
                        "--tier",
                        "watch",
                        "--want-zh",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        search_args_value = search.call_args.args[0]
        self.assertEqual(search.call_count, 1)
        self.assertTrue(search_args_value.want_zh)
        self.assertFalse(search_args_value.require_zh)
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["selected"]["size"], "2.5 GiB")
        self.assertIsNone(payload["quality"]["fallback"])

    def test_strict_zh_watch_fallback_requires_user_confirmation(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example",
            search_titles=["Example"],
            season="S01",
            current=True,
            trackable=True,
            source="fixture",
            status="RELEASING",
        )
        primary = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="subtitle_unqualified",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 1, "size_policy": {}},
            failures=[],
            cache="miss",
        )
        fallback_candidate = candidate("[G] Example S01E01 [CHT]", "1.4 GiB", 20)
        fallback_candidate.detail_checked = True
        fallback_candidate.detail_chinese_confirmed = True
        fallback_candidate.detail_subtitle_signal = "detail-page: CHT"
        fallback_candidate.subtitle_signal = "CHT; detail-page: CHT"
        fallback_item = core.ClassifiedCandidate(
            fallback_candidate,
            parse_release_identity(fallback_candidate.title),
            "match",
            effective_season=1,
            season_source="title",
            work_match="search_title",
        )
        fallback = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="found",
            selected=[fallback_item],
            choices=[],
            diagnostics={"raw_count": 1, "size_policy": {}},
            failures=[],
            cache="hit",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", side_effect=[primary, fallback]),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example",
                        "--season",
                        "S01",
                        "--episode",
                        "1",
                        "--tier",
                        "watch",
                        "--require-zh",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "needs_quality_fallback_confirmation")
        self.assertIsNone(payload["selected"])
        self.assertNotIn("magnet", payload["quality"]["fallback_candidate"])
        self.assertTrue(payload["output_contract"]["magnet_deferred_until_confirmation"])
        self.assertIn("是否降级到轻量观看", payload["reply_text"])

    def test_nickname_uses_canonical_title_before_web_resolution(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Yani Neko",
            season="S01",
            current=True,
            trackable=True,
            source="fixture",
            status="RELEASING",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BROWSE,
            requested_season=1,
            requested_episode=None,
            status="no_nyaa_release_for_target",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)) as resolve,
                patch.object(finder, "search_release_report", return_value=report),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "\u5c3c\u53e4\u55b5\u55b5",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        self.assertEqual(resolve.call_args.args[0], "Yani Neko")
        self.assertEqual(json.loads(output.getvalue())["resolved_title"], "Yani Neko")

    def test_old_show_does_not_create_tracking_state(self) -> None:
        old_resolved = finder.ResolvedAnime(
            title="Old Example",
            aliases=["Old Example Alias"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            status="FINISHED",
            episodes=12,
            duration_min=24,
        )
        item = core.ClassifiedCandidate(
            candidate("[Group] Old Example Season 1 - 01 [1080p]", "1.2 GiB", 10),
            parse_release_identity("[Group] Old Example Season 1 - 01 [1080p]"),
            "match",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.SPECIFIC_EPISODE,
            requested_season=1,
            requested_episode=1,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={"raw_count": 1},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", old_resolved)),
                patch.object(finder, "search_release_report", return_value=report),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Old Example",
                        "--season",
                        "S01",
                        "--episode",
                        "1",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
            self.assertFalse((root / "state.json").exists())
            self.assertEqual(json.loads(output.getvalue())["status"], "found")

    def test_latest_uses_schedule_target(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Example Season 4",
            aliases=["Example 4th season"],
            season="S04",
            current=True,
            trackable=True,
            source="fixture",
            status="RELEASING",
            episodes=24,
            duration_min=24,
            anilist_id=123,
            next_airing_episode=13,
            next_airing_at=int(time.time()) + 3600,
        )
        item = core.ClassifiedCandidate(
            candidate("[Group] Example Season 4 - 12 [1080p]", "1.2 GiB", 10),
            parse_release_identity("[Group] Example Season 4 - 12 [1080p]"),
            "match",
        )
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.LATEST_REGULAR,
            requested_season=4,
            requested_episode=12,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={"raw_count": 1},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", return_value=report),
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Example",
                        "--latest",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                        "--schedule-cache",
                        str(root / "schedule.json"),
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["status"], "found")
            self.assertEqual(payload["target_episode"], 12)
            self.assertTrue(payload["availability"]["official_target"])

    def test_schedule_cache_survives_state_without_anilist_id(self) -> None:
        base = finder.ResolvedAnime(title="Example Season 4", source="state")
        fresh = finder.ResolvedAnime(
            title="Example Season 4",
            season="S04",
            current=True,
            trackable=True,
            source="anilist",
            status="RELEASING",
            anilist_id=123,
            next_airing_episode=13,
            next_airing_at=int(time.time()) + 3600,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir) / "schedule.json"
            with patch.object(finder, "resolve_title", return_value=("resolved", fresh)) as resolve:
                _, first_status = finder.hydrate_airing_metadata(base, 1, cache, False, finder.date.today())
                _, second_status = finder.hydrate_airing_metadata(base, 1, cache, False, finder.date.today())
        self.assertEqual(first_status, "miss")
        self.assertEqual(second_status, "hit")
        self.assertEqual(resolve.call_count, 1)

    def test_short_term_authoritative_cache_preserves_single_season_metadata(self) -> None:
        cached = finder.ResolvedAnime(
            title="Cached Harbor Signals",
            aliases=["Harbor Signals"],
            search_titles=["Cached Harbor Signals"],
            verified_search_titles=["Cached Harbor Signals"],
            season="S01",
            format="TV",
            status="FINISHED",
            episodes=12,
            mainline_scope="single",
            source="anilist",
            anilist_id=9876,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schedule_cache = root / "schedule.json"
            finder.write_schedule_snapshot(
                schedule_cache,
                f"title:{finder.norm('Harbor Signals')}",
                cached,
            )
            args = finder.build_parser().parse_args(
                [
                    "Harbor Signals",
                    "--schedule-cache",
                    str(schedule_cache),
                    "--state",
                    str(root / "state.json"),
                ]
            )
            with patch.object(finder, "resolve_title", return_value=("unresolved", None)):
                identity = finder.resolve_work_identity(args, {"version": 1, "shows": []}, finder.date.today())
        self.assertEqual(identity.status, "resolved")
        self.assertIn("metadata_cache", identity.sources)
        self.assertEqual(identity.resolved.season, "S01")
        self.assertEqual(identity.resolved.mainline_scope, "single")

    def test_latest_before_first_episode_skips_rss(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Future Example",
            season="S01",
            current=True,
            trackable=True,
            source="fixture",
            status="RELEASING",
            anilist_id=456,
            next_airing_episode=1,
            next_airing_at=int(time.time()) + 3600,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report") as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Future Example",
                        "--latest",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                        "--schedule-cache",
                        str(root / "schedule.json"),
                    ]
                )
        self.assertEqual(json.loads(output.getvalue())["status"], "not_aired_yet")
        search.assert_not_called()

    def test_season_switch_preserves_tracked_next_episode(self) -> None:
        report = core.ReleaseSearchReport(
            intent=core.SearchIntent.NEXT_TRACKED,
            requested_season=3,
            requested_episode=3,
            status="no_nyaa_release_for_target",
            selected=[],
            choices=[],
            diagnostics={"raw_count": 0},
            failures=[],
            cache="miss",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            finder.save_state(
                state_path,
                {
                    "version": 1,
                    "shows": [
                        {
                            "title": "Tracked Example",
                            "season": "1",
                            "next_episode": 3,
                            "airing": True,
                        }
                    ],
                },
            )
            output = io.StringIO()
            with (
                patch.object(finder, "search_release_report", return_value=report) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Tracked Example",
                        "--season",
                        "3",
                        "--no-web-resolve",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(state_path),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        search_args = search.call_args.args[0]
        self.assertEqual(payload["season"], "S03")
        self.assertEqual(payload["target_episode"], 3)
        self.assertEqual(search_args.season, "S03")
        self.assertEqual(search.call_args.kwargs["intent"], core.SearchIntent.NEXT_TRACKED)
        self.assertEqual(search.call_args.kwargs["requested_episode"], 3)


class SeasonBatchSelectionTests(unittest.TestCase):
    @staticmethod
    def detail_page(work: str, seasons: dict[int, list[float]], extras: bool = False) -> str:
        directories = []
        for season, sizes in seasons.items():
            files = "".join(
                f'<li>{work} S{season:02d}E{episode:02d}.mkv '
                f'<span class="file-size">({size} GiB)</span></li>'
                for episode, size in enumerate(sizes, start=1)
            )
            directories.append(f"<li>{work} S{season:02d}<ul>{files}</ul></li>")
        if extras:
            directories.append(
                f'<li>Extras<ul><li>{work} NCOP.mkv '
                '<span class="file-size">(3.0 GiB)</span></li></ul></li>'
            )
        return '<div class="torrent-file-list panel-body"><ul>' + "".join(directories) + "</ul></div>"

    @staticmethod
    def context(work: str = "Atlas Chronicle") -> core.SearchContext:
        return core.SearchContext(
            canonical_title=work,
            search_titles=(work,),
            mainline_scope="multi",
            resolved_season=1,
            expected_episodes=12,
        )

    @staticmethod
    def args(tier: str = "browse") -> argparse.Namespace:
        args = search_args()
        args.query = "Atlas Chronicle"
        args.season = "S01"
        args.episodes = 12
        args.tier = tier
        args.min_gib_per_episode = {"browse": 1.0, "watch": 2.0, "premium": 6.0}[tier]
        args.max_gib_per_episode = None
        return args

    def run_report(
        self,
        candidates: list[nyaa.Candidate],
        pages: dict[str, str],
        *,
        args: argparse.Namespace | None = None,
        context: core.SearchContext | None = None,
    ) -> core.ReleaseSearchReport:
        actual_args = args or self.args()
        with (
            patch.object(core, "collect_raw_candidates", return_value=(candidates, [], "fixture")),
            patch.object(
                nyaa,
                "fetch_nyaa_detail_page",
                side_effect=lambda url, _timeout: pages[url],
            ),
        ):
            return core.search_release_report(
                actual_args,
                intent=core.SearchIntent.SEASON_BATCH,
                context=context or self.context(),
            )

    def test_random_single_and_related_side_story_never_become_whole_season(self) -> None:
        regular = candidate("[G] Atlas Chronicle S01E04 [1080p]", "1.5 GiB", 10)
        side_story = candidate("[G] Atlas Chronicle Side Story S1 [01-04]", "8 GiB", 20)
        context = self.context()
        context = core.SearchContext(
            **{**context.__dict__, "related_titles": ("Atlas Chronicle Side Story",)}
        )
        report = self.run_report([regular, side_story], {}, context=context)
        self.assertEqual(report.status, "no_complete_season_release")
        self.assertEqual(report.choices, [])

    def test_aggregate_below_one_gib_per_episode_is_hidden_without_detail_fetch(self) -> None:
        low = candidate("[G] Atlas Chronicle S1 [01-12] Complete", "6.5 GiB", 99)
        args = self.args()
        with (
            patch.object(core, "collect_raw_candidates", return_value=([low], [], "fixture")),
            patch.object(nyaa, "fetch_nyaa_detail_page") as fetch,
        ):
            report = core.search_release_report(
                args,
                intent=core.SearchIntent.SEASON_BATCH,
                context=self.context(),
            )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.selected, [])
        self.assertEqual(report.choices, [])
        self.assertEqual(report.diagnostics["aggregate_floor_rejected_count"], 1)
        fetch.assert_not_called()

    def test_exact_season_beats_higher_seeded_multi_season_collection(self) -> None:
        exact = candidate("[A] Atlas Chronicle S1 [01-12] Complete", "18 GiB", 5)
        multi = candidate("[B] Atlas Chronicle S1+S2 Complete", "36 GiB", 500)
        pages = {
            exact.url: self.detail_page("Atlas Chronicle", {1: [1.5] * 12}, extras=True),
            multi.url: self.detail_page("Atlas Chronicle", {1: [1.5] * 12, 2: [1.5] * 12}),
        }
        report = self.run_report([exact, multi], pages)
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.title, exact.title)
        self.assertEqual(report.selected[0].coverage.scope, "exact")

    def test_qualified_multi_season_is_used_when_exact_package_fails_per_file_quality(self) -> None:
        exact = candidate("[A] Atlas Chronicle S1 [01-12] Complete", "18 GiB", 50)
        multi = candidate("[B] Atlas Chronicle S1+S2 Complete", "36 GiB", 10)
        pages = {
            exact.url: self.detail_page("Atlas Chronicle", {1: [0.8] * 12}),
            multi.url: self.detail_page("Atlas Chronicle", {1: [1.5] * 12, 2: [1.5] * 12}),
        }
        report = self.run_report([exact, multi], pages)
        self.assertEqual(report.status, "found")
        self.assertEqual(report.selected[0].candidate.title, multi.title)
        self.assertEqual(report.selected[0].coverage.scope, "multi")

    def test_multi_season_collection_requires_every_regular_file_to_meet_tier(self) -> None:
        multi = candidate("[B] Atlas Chronicle S1+S2 Complete", "36 GiB", 10)
        second_season = [1.5] * 12
        second_season[6] = 0.8
        report = self.run_report(
            [multi],
            {multi.url: self.detail_page("Atlas Chronicle", {1: [1.5] * 12, 2: second_season})},
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.choices, [])
        self.assertEqual(report.diagnostics["season_quality_rejected_count"], 1)

    def test_named_watch_tier_uses_average_with_one_gib_absolute_floor(self) -> None:
        args = self.args("watch")
        args.episodes = 25
        batch = candidate("[G] Atlas Chronicle S1 [01-25] Complete", "57 GiB", 30)
        sizes = [
            2.1, 2.2, 1.8, 2.1, 2.2, 1.9, 2.1, 1.7, 2.1, 2.7,
            2.1, 3.0, 1.9, 2.1, 2.2, 2.2, 2.0, 2.6, 3.0, 2.3,
            2.3, 2.8, 2.8, 2.3, 2.4,
        ]
        context = core.SearchContext(
            canonical_title="Atlas Chronicle",
            search_titles=("Atlas Chronicle",),
            mainline_scope="single",
            resolved_season=1,
            expected_episodes=25,
        )
        report = self.run_report(
            [batch],
            {batch.url: self.detail_page("Atlas Chronicle", {1: sizes})},
            args=args,
            context=context,
        )
        self.assertEqual(report.status, "found")
        coverage = report.selected[0].coverage
        self.assertEqual(coverage.quality_basis, "average")
        self.assertAlmostEqual(coverage.average_gib_per_episode, 2.276, places=3)
        self.assertEqual(coverage.min_gib_per_episode, 1.7)
        self.assertEqual(coverage.max_gib_per_episode, 3.0)

    def test_named_watch_tier_rejects_any_episode_below_absolute_floor(self) -> None:
        args = self.args("watch")
        batch = candidate("[G] Atlas Chronicle S1 [01-12] Complete", "28 GiB", 30)
        sizes = [0.9] + [2.45] * 11
        report = self.run_report(
            [batch],
            {batch.url: self.detail_page("Atlas Chronicle", {1: sizes})},
            args=args,
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.diagnostics["absolute_floor_rejected_count"], 1)
        self.assertEqual(
            report.diagnostics["quality_rejection_samples"][0]["reason"],
            "per_episode_below_absolute_floor",
        )

    def test_explicit_minimum_remains_strict_per_file(self) -> None:
        args = self.args("watch")
        args.size_policy_source = "explicit"
        args.min_gib_per_episode = 2.0
        args.max_gib_per_episode = None
        batch = candidate("[G] Atlas Chronicle S1 [01-12] Complete", "27 GiB", 30)
        sizes = [1.9] + [2.3] * 11
        report = self.run_report(
            [batch],
            {batch.url: self.detail_page("Atlas Chronicle", {1: sizes})},
            args=args,
        )
        self.assertEqual(report.status, "release_unqualified")
        self.assertEqual(report.diagnostics["explicit_per_file_rejected_count"], 1)
        self.assertEqual(
            report.diagnostics["quality_rejection_samples"][0]["quality_basis"],
            "explicit_per_file",
        )

    def test_missing_episode_is_conclusive_no_complete_release(self) -> None:
        partial = candidate("[A] Atlas Chronicle S1 [01-12] Complete", "18 GiB", 20)
        report = self.run_report(
            [partial],
            {partial.url: self.detail_page("Atlas Chronicle", {1: [1.5] * 11})},
        )
        self.assertEqual(report.status, "no_complete_season_release")
        self.assertEqual(report.diagnostics["coverage_rejected_count"], 1)

    def test_unreadable_file_list_is_check_incomplete(self) -> None:
        batch = candidate("[A] Atlas Chronicle S1 [01-12] Complete", "18 GiB", 20)
        report = self.run_report([batch], {batch.url: "<html><body>No file list</body></html>"})
        self.assertEqual(report.status, "season_check_incomplete")
        self.assertEqual(report.selected, [])

    def test_bdmv_can_pass_premium_source_rule_after_coverage_check(self) -> None:
        args = self.args("premium")
        disc = candidate("[BDMV] Foxtrot Archive S1 [01-12] Complete", "180 GiB", 8)
        files = "".join(
            f'<li>{index:05d}.m2ts <span class="file-size">(0.5 GiB)</span></li>'
            for index in range(1, 13)
        )
        page = f'<div class="torrent-file-list"><ul>{files}</ul></div>'
        context = core.SearchContext(
            canonical_title="Foxtrot Archive",
            search_titles=("Foxtrot Archive",),
            mainline_scope="single",
            resolved_season=1,
            expected_episodes=12,
        )
        report = self.run_report([disc], {disc.url: page}, args=args, context=context)
        self.assertEqual(report.status, "found")
        self.assertTrue(report.selected[0].coverage.source_exempt)
        self.assertTrue(report.selected[0].coverage.complete)
        self.assertEqual(report.selected[0].coverage.quality_basis, "source_exempt")

    def test_explicit_minimum_disables_remux_source_exemption(self) -> None:
        args = self.args("premium")
        args.size_policy_source = "explicit"
        args.min_gib_per_episode = 6.0
        args.max_gib_per_episode = None
        remux = candidate("[G] Foxtrot Archive S1 BD Remux Complete", "80 GiB", 8)
        context = core.SearchContext(
            canonical_title="Foxtrot Archive",
            search_titles=("Foxtrot Archive",),
            mainline_scope="single",
            resolved_season=1,
            expected_episodes=12,
        )
        report = self.run_report(
            [remux],
            {remux.url: self.detail_page("Foxtrot Archive", {1: [5.5] * 12})},
            args=args,
            context=context,
        )
        self.assertEqual(report.status, "release_unqualified")
        sample = report.diagnostics["quality_rejection_samples"][0]
        self.assertEqual(sample["quality_basis"], "explicit_per_file")
        self.assertEqual(sample["reason"], "explicit_per_file_size_out_of_range")

    def test_season_only_remux_with_bit_depth_reaches_batch_verification(self) -> None:
        args = self.args("premium")
        args.query = "Atlas Chronicle"
        args.episodes = 25
        remux = candidate(
            "[Group] Atlas Chronicle Season 1 (BD Remux 1080p x264 8-bit PCM)",
            "141.2 GiB",
            5,
        )
        context = core.SearchContext(
            canonical_title="Atlas Chronicle",
            search_titles=("Atlas Chronicle",),
            mainline_scope="single",
            resolved_season=1,
            expected_episodes=25,
        )
        sizes = [5.2] * 24 + [6.1]
        report = self.run_report(
            [remux],
            {remux.url: self.detail_page("Atlas Chronicle", {1: sizes})},
            args=args,
            context=context,
        )
        self.assertEqual(report.status, "found")
        self.assertEqual(report.diagnostics["aggregate_floor_rejected_count"], 0)
        self.assertTrue(report.selected[0].coverage.source_exempt)
        self.assertEqual(report.selected[0].coverage.main_file_count, 25)


class SeasonBatchHighLevelTests(unittest.TestCase):
    @staticmethod
    def unavailable_batch_report(season: int = 1) -> core.ReleaseSearchReport:
        return core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BATCH,
            requested_season=season,
            requested_episode=None,
            status="no_complete_season_release",
            selected=[],
            choices=[],
            diagnostics={"size_policy": {}},
            failures=[],
            cache="miss",
        )

    def test_old_title_only_defaults_to_complete_season(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Harbor Signals",
            search_titles=["Harbor Signals"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            format="TV",
            status="FINISHED",
            episodes=12,
            mainline_scope="single",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(
                    finder,
                    "search_release_report",
                    return_value=self.unavailable_batch_report(),
                ) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Harbor Signals",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["intent"], "season_batch")
        self.assertEqual(payload["season"], "S01")
        self.assertEqual(search.call_args.kwargs["intent"], core.SearchIntent.SEASON_BATCH)

    def test_finished_single_mainline_without_season_defaults_to_s01(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Harbor Signals",
            search_titles=["Harbor Signals"],
            season=None,
            current=False,
            trackable=False,
            source="fixture",
            format="TV",
            status="FINISHED",
            episodes=12,
            mainline_scope="single",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(
                    finder,
                    "search_release_report",
                    return_value=self.unavailable_batch_report(),
                ) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Harbor Signals",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                        "--schedule-cache",
                        str(root / "schedule.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["intent"], "season_batch")
        self.assertEqual(payload["season"], "S01")
        self.assertEqual(search.call_args.args[0].season, "S01")

    def test_old_title_only_asks_before_search_when_season_is_unresolved(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Atlas Chronicle",
            search_titles=["Atlas Chronicle"],
            season=None,
            current=False,
            trackable=False,
            source="fixture",
            format="TV",
            status="FINISHED",
            episodes=12,
            mainline_scope="multi",
            related_titles=["Atlas Chronicle 2"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report") as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Atlas Chronicle",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "needs_season_confirmation")
        self.assertEqual(payload["intent"], "season_batch")
        self.assertIsNone(payload["season"])
        self.assertIn("第几季", payload["reply_text"])
        self.assertNotIn("magnet:?", payload["reply_text"])
        search.assert_not_called()

    def test_premium_falls_back_only_one_level_to_watch(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Harbor Signals",
            search_titles=["Harbor Signals"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            format="TV",
            status="FINISHED",
            episodes=12,
        )
        primary = core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BATCH,
            requested_season=1,
            requested_episode=None,
            status="release_unqualified",
            selected=[],
            choices=[],
            diagnostics={"size_policy": {}},
            failures=[],
            cache="miss",
        )
        release = candidate("[G] Harbor Signals S1 [01-12] Complete", "36 GiB", 12)
        coverage = core.SeasonCoverage(
            scope="exact",
            target_season=1,
            expected_episodes=12,
            covered_episodes=tuple(range(1, 13)),
            covered_seasons=(1,),
            confidence="verified",
            main_file_count=12,
            min_gib_per_episode=3.0,
            max_gib_per_episode=3.0,
            complete=True,
            quality_fit=True,
            reason="verified_complete_and_qualified",
        )
        item = core.ClassifiedCandidate(
            release,
            parse_release_identity(release.title),
            "match",
            effective_season=1,
            season_source="title_coverage",
            work_match="canonical",
            coverage=coverage,
        )
        fallback = core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BATCH,
            requested_season=1,
            requested_episode=None,
            status="found",
            selected=[item],
            choices=[],
            diagnostics={"size_policy": {}},
            failures=[],
            cache="hit",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(finder, "search_release_report", side_effect=[primary, fallback]) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Harbor Signals",
                        "--season",
                        "S01",
                        "--whole-season",
                        "--tier",
                        "premium",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(search.call_count, 2)
        self.assertEqual(search.call_args_list[1].args[0].tier, "watch")
        self.assertEqual(payload["intent"], "season_batch")
        self.assertEqual(payload["quality"]["effective_tier"], "watch")
        self.assertEqual(payload["quality"]["fallback"]["to"], "watch")
        self.assertEqual(payload["selected"]["coverage"]["scope"], "exact")

    def test_watch_prompts_before_upgrading_to_complete_premium_season(self) -> None:
        resolved = finder.ResolvedAnime(
            title="Harbor Signals",
            search_titles=["Harbor Signals"],
            season="S01",
            current=False,
            trackable=False,
            source="fixture",
            format="TV",
            status="FINISHED",
            episodes=12,
            mainline_scope="single",
        )
        failed = core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BATCH,
            requested_season=1,
            requested_episode=None,
            status="release_unqualified",
            selected=[],
            choices=[],
            diagnostics={"size_policy": {}},
            failures=[],
            cache="hit",
        )
        release = candidate("[G] Harbor Signals S1 BD Remux Complete", "132 GiB", 16)
        coverage = core.SeasonCoverage(
            scope="exact",
            target_season=1,
            expected_episodes=12,
            covered_episodes=tuple(range(1, 13)),
            covered_seasons=(1,),
            confidence="verified",
            main_file_count=12,
            average_gib_per_episode=11.0,
            min_gib_per_episode=10.5,
            max_gib_per_episode=11.5,
            quality_basis="source_exempt",
            source_exempt=True,
            complete=True,
            quality_fit=True,
            reason="verified_complete_and_qualified",
        )
        premium_item = core.ClassifiedCandidate(
            release,
            parse_release_identity(release.title),
            "match",
            effective_season=1,
            season_source="title_coverage",
            work_match="canonical",
            coverage=coverage,
        )
        premium = core.ReleaseSearchReport(
            intent=core.SearchIntent.SEASON_BATCH,
            requested_season=1,
            requested_episode=None,
            status="found",
            selected=[premium_item],
            choices=[],
            diagnostics={"size_policy": {}},
            failures=[],
            cache="hit",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title", return_value=("resolved", resolved)),
                patch.object(
                    finder,
                    "search_release_report",
                    side_effect=[failed, failed, premium],
                ) as search,
                contextlib.redirect_stdout(output),
            ):
                finder.main(
                    [
                        "Harbor Signals",
                        "--tier",
                        "watch",
                        "--include-magnet",
                        "--legal-ok",
                        "--no-state-update",
                        "--json",
                        "--state",
                        str(root / "state.json"),
                        "--cache",
                        str(root / "raw.json"),
                    ]
                )
        payload = json.loads(output.getvalue())
        self.assertEqual(search.call_count, 3)
        self.assertEqual([call.args[0].tier for call in search.call_args_list], ["watch", "browse", "premium"])
        self.assertEqual(payload["status"], "needs_quality_upgrade_confirmation")
        self.assertTrue(payload["output_contract"]["ready"])
        self.assertEqual(payload["quality"]["upgrade_candidate"]["source_type"], "Remux")
        self.assertNotIn("magnet", payload["quality"]["upgrade_candidate"])
        self.assertNotIn("magnet:?", payload["reply_text"])
        self.assertIn("是否改用高画质", payload["reply_text"])


if __name__ == "__main__":
    unittest.main()
