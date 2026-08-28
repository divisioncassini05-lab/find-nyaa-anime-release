from __future__ import annotations

import base64
import copy
import itertools
import sys
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings, strategies as st


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import airing_watch_state as watch_state
import qbittorrent_submit as qbt
import release_search_core as core
import search_nyaa_releases as nyaa
from release_identity import EpisodeKind, parse_release_identity


PROPERTY_SETTINGS = settings(max_examples=500, deadline=None, derandomize=True)


@PROPERTY_SETTINGS
@given(
    season=st.integers(min_value=1, max_value=20),
    episode=st.integers(min_value=1, max_value=99),
    resolution=st.sampled_from((720, 1080, 2160)),
    bit_depth=st.sampled_from((8, 10, 12)),
    fps=st.sampled_from((23, 24, 30, 60)),
)
def test_explicit_season_episode_survives_technical_number_noise(
    season: int,
    episode: int,
    resolution: int,
    bit_depth: int,
    fps: int,
) -> None:
    title = (
        f"[Group] Example S{season:02d}E{episode:02d} "
        f"{resolution}p {bit_depth}bit {fps}fps AAC2.0"
    )
    identity = parse_release_identity(title)
    assert identity.kind is EpisodeKind.REGULAR
    assert identity.season == season
    assert identity.episode == Decimal(episode)


@PROPERTY_SETTINGS
@given(
    episodes=st.lists(
        st.integers(min_value=1, max_value=500),
        min_size=1,
        max_size=60,
    )
)
def test_record_found_is_monotonic_and_idempotent(episodes: list[int]) -> None:
    data = {
        "version": 1,
        "shows": [
            {
                "title": "Example",
                "aliases": [],
                "watched_episode": 0,
                "latest_known_episode": 0,
                "next_episode": 1,
                "airing": True,
            }
        ],
    }
    observed = 0
    for episode in episodes:
        before = copy.deepcopy(data)
        result = watch_state.record_found_episode(data, "Example", episode)
        observed = max(observed, episode)
        show = data["shows"][0]
        assert show["watched_episode"] == observed
        assert show["latest_known_episode"] >= show["watched_episode"]
        assert show["next_episode"] >= show["watched_episode"] + 1
        if episode <= before["shows"][0]["watched_episode"]:
            assert result["status"] == "unchanged"
            assert data == before


@PROPERTY_SETTINGS
@given(raw_hash=st.binary(min_size=20, max_size=20))
def test_hex_and_base32_magnets_resolve_to_the_same_hash(raw_hash: bytes) -> None:
    expected = raw_hash.hex()
    hexadecimal = f"magnet:?xt=urn:btih:{expected}"
    base32 = base64.b32encode(raw_hash).decode("ascii")
    encoded = f"magnet:?xt=urn:btih:{base32}"
    assert qbt.extract_btih(hexadecimal) == expected
    assert qbt.extract_btih(encoded) == expected


@PROPERTY_SETTINGS
@given(
    marker=st.sampled_from(("OVA", "OAD", "SP", "Special", "Recap")),
    episode=st.integers(min_value=1, max_value=99),
)
def test_special_markers_never_become_regular_progress(marker: str, episode: int) -> None:
    identity = parse_release_identity(f"[Group] Example S01E{episode:02d} {marker} 1080p")
    assert identity.kind is EpisodeKind.SPECIAL


def _candidate(title: str, seeders: int) -> nyaa.Candidate:
    return nyaa.Candidate(
        rank=0,
        score=float(seeders),
        title=title,
        group="Group",
        resolution="1080p",
        codec="AVC",
        bit_depth=None,
        audio_signal="unknown",
        subtitle_signal="not confirmed",
        size="1.4 GiB",
        size_bytes=nyaa.parse_size("1.4 GiB"),
        size_basis="fixture",
        bitrate_note="fixture",
        tier_fit="in-tier",
        seeders=seeders,
        leechers=0,
        downloads=0,
        published="2026-08-29",
        category="Anime",
        url=f"https://nyaa.si/view/{seeders}",
        magnet=f"magnet:?xt=urn:btih:{seeders:040x}",
        matched_queries=["Example"],
    )


def test_wrong_high_seed_candidates_and_input_order_cannot_replace_exact_target() -> None:
    candidates = (
        _candidate("[Group] Example S01E08 1080p", 5),
        _candidate("[Group] Example S01E07 1080p", 999),
        _candidate("[Group] Example S02E08 1080p", 998),
        _candidate("[Group] Example S01E08 OVA 1080p", 997),
    )
    context = core.SearchContext(
        canonical_title="Example",
        aliases=("Example",),
        search_titles=("Example",),
        resolved_season=1,
        mainline_scope="single",
    )
    for permutation in itertools.permutations(candidates):
        classified = core._classify(list(permutation), 1, context)
        exact = [item for item in classified if core._is_exact_regular_episode(item, 8)]
        assert [item.candidate.title for item in exact] == ["[Group] Example S01E08 1080p"]
