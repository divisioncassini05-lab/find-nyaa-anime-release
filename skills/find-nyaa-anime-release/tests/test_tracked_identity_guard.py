"""Local priority and metadata boundaries must survive wrong remote responses."""
import contextlib
import copy
import io
import json
import ssl
import urllib.error
from datetime import date
from unittest.mock import patch

import pytest

import airing_watch_state as watch
import find_anime_release as finder
import anime_release.workflow as v2_workflow
import anime_release.providers as v2_providers
import state_io
from failure_recovery import recovery_plan
from nyaa_client import NyaaClient, NyaaTLSVerificationError


def record(title="Re:ZERO -Starting Life in Another World- Season 4", **extra):
    return {"title": title, "season": "S04", "aliases": ["Re:Zero kara Hajimeru Isekai Seikatsu", "Re:从零开始的异世界生活"],
            "search_titles": ["Re:Zero kara Hajimeru Isekai Seikatsu 4th Season"],
            "airing": True, "status": "airing", "anilist_id": 21355, "format": "TV",
            "watched_episode": 17, "next_episode": 18, "latest_known_episode": 17, **extra}


def media(title="Re:ZERO -Starting Life in Another World-", **extra):
    return {"id": 21355, "title": {"english": title}, "format": "TV", "status": "FINISHED",
            "episodes": 25, "endDate": {"year": 2016, "month": 9, "day": 19},
            "relations": {"edges": [{"relationType": "SEQUEL", "node": {"type": "ANIME", "format": "TV"}}]}, **extra}


@pytest.mark.parametrize("query", ["re0", "ReZero", "Re:ZERO", "Re:从零开始的异世界生活"])
def test_probe_and_resolver_choose_current_tracked_season(query, tmp_path):
    current = record()
    old = record(title="Re:ZERO", season="S01", airing=False, status="completed")
    data = {"shows": [old, current]}
    assert watch.find_show(data, query) is current
    assert finder.find_show(data, query) is current
    args = finder.build_parser().parse_args([query, "--schedule-cache", str(tmp_path / "cache.json")])
    with patch.object(v2_providers, "resolve_title", side_effect=AssertionError("must use tracked identity")), \
         patch.object(v2_providers, "resolve_bangumi_title", side_effect=AssertionError("must use tracked identity")):
        result = finder.resolve_work_identity(args, data, date.today())
    assert result.state_show is current and result.resolved.season == "S04"


def test_generic_policy_applies_to_other_franchises():
    old = record("Example", aliases=["例子"], search_titles=[], season="S01", airing=False, status="completed")
    new = record("Example Season 3", aliases=["例子"], search_titles=[], season="S03")
    for query in ["Example", "例子"]:
        assert finder.find_show({"shows": [old, new]}, query) is new
    old["title"] = "Example Season 1"
    assert finder.find_show({"shows": [old, new]}, "Example Season 1") is old


def test_one_shared_name_is_not_a_multi_show_request():
    data = {"shows": [record("Example", aliases=["Example"], season="S01", airing=False),
                      record("Example Season 4", aliases=["Example"])]}
    assert finder.detect_tracked_titles(data, "Example") == []


def test_official_date_rescue_rejects_wrong_quarter_identity(tmp_path):
    resolved = finder.resolved_from_state(record(), "")
    identity = finder.IdentityResolution("resolved", resolved, record(), True, "alias")
    with patch.object(v2_providers, "anilist_air_date_request", return_value={"data": {"Media": media()}}):
        result = finder.official_air_date_report(identity, 18, tmp_path / "cache.json", 1, True, date.today())
    assert result["status"] == "identity_conflict" and not result["recent_scan_eligible"]


def test_corrupted_id_does_not_merge_or_delete_another_season():
    first = record("Example Season 1", season="S01", airing=False)
    fourth = record("Example Season 4")
    data = {"shows": [first, fourth]}
    before_first = copy.deepcopy(first)
    resolved = finder.resolved_from_state(fourth, "")
    finder.upsert_show(data, fourth["title"], [], "S04", 18, 19, "test", resolved=resolved,
                       show_hint=fourth, watched_episode=18)
    assert len(data["shows"]) == 2 and first == before_first


def test_two_active_matches_never_fall_through_to_global_search(tmp_path):
    data = {"shows": [record(), record(season="S03")]}
    args = finder.build_parser().parse_args(["re0", "--schedule-cache", str(tmp_path / "cache.json")])
    with patch.object(v2_providers, "resolve_title", side_effect=AssertionError("ambiguous local match")):
        result = finder.resolve_work_identity(args, data, date.today())
    assert result.status == "ambiguous" and len(result.resolved.choices) == 2


def test_short_unregistered_name_cannot_match_arbitrary_substrings():
    assert finder.find_show({"shows": [record("Gundam UC RE:0096", aliases=[], search_titles=[])]}, "re0") is None


def test_request_cannot_label_remote_first_season_as_fourth():
    fresh, _ = finder.media_to_resolved(record()["title"], media(), date.today())
    assert fresh.season is None
    assert record()["title"] not in fresh.aliases
    merged = finder.merge_resolved(finder.resolved_from_state(record(), ""), fresh)
    assert merged.identity_conflicts[0]["reasons"] == ["season_unverified", "work_title_mismatch"]
    assert merged.season == "S04" and merged.title == record()["title"]
    assert not merged.completion and merged.status != "FINISHED"


@pytest.mark.parametrize("fresh", [
    finder.ResolvedAnime("Example Season 1", season="S01", anilist_id=21355),
    finder.ResolvedAnime("Example Season 4", season="S04", anilist_id=999),
    finder.ResolvedAnime("Example Season 4", season="S04", format="MOVIE"),
])
def test_conflicting_merge_is_non_mutating(fresh):
    base = finder.resolved_from_state(record("Example Season 4"), "")
    original = copy.deepcopy((base, fresh))
    merged = finder.merge_resolved(base, fresh)
    assert merged.identity_conflicts
    assert (base, fresh) == original


def test_same_identity_can_refresh_normally():
    base = finder.resolved_from_state(record(), "")
    fresh, _ = finder.media_to_resolved("re0", media(record()["title"], status="RELEASING", episodes=19, endDate={}), date.today())
    merged = finder.merge_resolved(base, fresh)
    assert not merged.identity_conflicts and merged.episodes == 19


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("readonly", [False, True])
def test_wrong_live_or_cached_metadata_stops_before_search_client_and_state(tmp_path, cached, readonly):
    saved = record()
    path = tmp_path / "state.json"
    state_io.save_state(path, {"version": 1, "shows": [saved]})
    before = path.read_bytes()
    cache = tmp_path / "schedule.json"
    if cached:
        wrong, _ = finder.media_to_resolved("unrelated query", media(), date.today())
        finder.write_schedule_snapshot(cache, "anilist:21355", wrong)
    out = io.StringIO()
    with patch.object(v2_providers, "anilist_media_request", return_value={"data": {"Media": media()}}), \
         patch.object(v2_providers, "anilist_request", return_value={"data": {"Page": {"media": [media()]}}}), \
         patch.object(v2_providers, "bangumi_request", return_value={"data": []}), \
         patch.object(v2_workflow, "search_release_report", side_effect=AssertionError("no Nyaa on identity conflict")), \
         patch.object(v2_workflow, "submit_magnet", side_effect=AssertionError("no enqueue on identity conflict")), contextlib.redirect_stdout(out):
        finder.main(["re0", "--latest", "--state", str(path), "--schedule-cache", str(cache),
                     "--json", *(["--no-state-update"] if readonly else [])])
    result = json.loads(out.getvalue())
    assert result["status"] == "identity_conflict"
    assert result["target_episode"] is None and result["qbittorrent"]["status"] == "not_attempted"
    assert path.read_bytes() == before
    assert result["recovery"]["action"] == "verify_tracked_work_metadata"


@pytest.mark.parametrize("wrapped", [False, True])
def test_certificate_failure_is_not_a_transient_retry(wrapped):
    error = ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed certificate")
    if wrapped:
        error = urllib.error.URLError(error)
    opener = __import__("unittest.mock", fromlist=["Mock"]).Mock(side_effect=error)
    with pytest.raises(NyaaTLSVerificationError) as raised:
        NyaaClient(opener=opener)._request("https://nyaa.si/", 1)
    assert opener.call_count == 1
    assert raised.value.retryable is False
    result = recovery_plan({"status": "network_error", "failures": [str(raised.value)]})
    assert result["action"] == "inspect_tls_trust_and_execution_context"
    assert result["retry_basis"] is None and not result["latest_confirmed"]


def test_timeout_still_has_bounded_retry():
    result = recovery_plan({"status": "network_error", "failures": ["timed out"]})
    assert result["action"] == "retry_failed_queries_once"
