from __future__ import annotations

import contextlib
import io
import json
import re
import shlex
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import find_anime_release as finder
import anime_release.workflow as v2_workflow
import anime_release.providers as v2_providers
import release_search_core as core
import search_nyaa_releases as nyaa
from nyaa_client import NyaaClient, NyaaFileEntry, NyaaRelease, NyaaReleaseDetail, NyaaNotFoundError
from test_release_finder import candidate


def release(release_id=101, episode=5, *, size="1.4 GiB", title=None, score=10):
    item = candidate(title or f"[Group] Example Anime S01E{episode:02d} [1080p]", size, score)
    item.url = f"https://nyaa.si/view/{release_id}"
    item.magnet = "magnet:?xt=urn:btih:" + f"{release_id:040x}"
    item.matched_queries = ["Example Anime"]
    return item


def run_finder(tmp_path, releases, options, *, watched=4, tracked=True, failures=(), client=None, submission=None):
    state_path = tmp_path / "state.json"
    state = {"version": 1, "shows": []}
    if tracked:
        state["shows"].append({
            "title": "Example Anime", "aliases": [], "season": "S01",
            "search_titles": ["Example Anime"], "verified_search_titles": ["Example Anime"],
            "watched_episode": watched, "latest_known_episode": watched,
            "next_episode": watched + 1, "airing": True, "status": "airing", "format": "TV",
            "total_episodes": 2 if "--whole-season" in options else 12,
        })
        state_path.write_text(json.dumps(state), encoding="utf-8")
    before = state_path.read_bytes() if state_path.exists() else None
    resolved = finder.ResolvedAnime(
        title="Example Anime", search_titles=["Example Anime"],
        verified_search_titles=["Example Anime"], season="S01", current=True,
        trackable=True, source="fixture", status="RELEASING", format="TV",
    )
    network = client or Mock(spec=NyaaClient)
    network.search.side_effect = AssertionError("Unexpected live search")
    if client is None:
        def detail_fixture(release_id, **_):
            rid = core.nyaa.nyaa_id_from_url(str(release_id))
            item = next((r for r in releases if core.nyaa.nyaa_id_from_url(r.url)==rid),None)
            if item is None:
                raise NyaaNotFoundError('fixture missing')
            return NyaaReleaseDetail(NyaaRelease(rid,item.title,item.category,item.size,item.size_bytes,
                item.published,None,item.seeders,item.leechers,item.downloads,item.url,
                core.re.search(r'btih:([a-f0-9]{40})',item.magnet).group(1)),
                'Subtitles: English',())
        network.get.side_effect = detail_fixture
        network.get_description.return_value = "Subtitles: English"
    output = io.StringIO()
    with (
        patch.object(v2_providers, "resolve_title", return_value=("resolved", resolved)),
        patch.object(core, "collect_raw_candidates", return_value=(releases, list(failures), "fixture")),
        patch.object(core, "DEFAULT_NYAA_CLIENT", network),
        patch.object(v2_workflow, "submit_magnet", return_value=submission or {"ok": True, "status": "submitted"}) as submit,
        contextlib.redirect_stdout(output),
    ):
        code = finder.main([
            "Example Anime", "--season", "S01", "--json",
            *(["--no-web-resolve"] if tracked else []),
            "--include-magnet", "--legal-ok", "--state", str(state_path),
            "--cache", str(tmp_path / "raw.json"), "--schedule-cache", str(tmp_path / "schedule.json"),
            *options,
        ])
    after = finder.load_state(state_path) if state_path.exists() else None
    return code, json.loads(output.getvalue()), submit, before, after


def test_audited_id_is_submitted_even_when_another_candidate_ranks_higher(tmp_path):
    audited, other = release(), release(202, score=200)
    code, report, submit, _, state = run_finder(tmp_path, [other, audited], [
        "--episode", "5", "--candidate-id", audited.url, "--enqueue-qbittorrent",
    ])
    assert code == 0
    assert report["status"] == "found"
    assert report["diagnostic"]["candidate_id_filter"] == ["101"]
    assert submit.call_args.args[0].split('&')[0] == audited.magnet
    assert state["shows"][0]["watched_episode"] == 5


@pytest.mark.parametrize("title,size,tier,extra", [
    ("[G] Example Anime S01E04", "1.4 GiB", "browse", []),
    ("[G] Example Anime S02E05", "1.4 GiB", "browse", []),
    ("[G] Unrelated Work S01E05", "1.4 GiB", "browse", []),
    (None, "0.8 GiB", "browse", []),
    (None, "1.4 GiB", "watch", []),
    (None, "1.4 GiB", "browse", ["--require-zh"]),
])
def test_pin_rechecks_constraints_without_replacement_or_downgrade(tmp_path, title, size, tier, extra):
    audited = release(title=title, size=size)
    code, report, submit, _, state = run_finder(tmp_path, [audited, release(202, score=200)], [
        "--episode", "5", "--candidate-id", "101", "--tier", tier, "--enqueue-qbittorrent", *extra,
    ])
    assert report["status"] != "found"
    assert report["quality"]["fallback"] is None
    assert "magnet:?" not in json.dumps(report)
    submit.assert_not_called()
    assert state["shows"][0]["watched_episode"] == 4


def test_pinned_first_delivery_creates_current_tracking(tmp_path):
    _, report, submit, _, state = run_finder(tmp_path, [release()], [
        "--episode", "5", "--candidate-id", "101", "--enqueue-qbittorrent",
    ], tracked=False)
    assert report["state_update"] == "advanced"
    assert state["shows"][0]["next_episode"] == 6
    submit.assert_called_once()


def test_latest_pin_cannot_turn_an_older_release_into_latest(tmp_path):
    _, report, submit, before, state = run_finder(tmp_path, [release(), release(202, episode=6)], [
        "--latest", "--candidate-id", "101", "--enqueue-qbittorrent",
    ])
    assert report["target_episode"] == 6
    assert report["status"] != "found"
    submit.assert_not_called()
    assert (tmp_path / "state.json").read_bytes() == before


def test_latest_pin_keeps_already_handled_semantics(tmp_path):
    _, report, submit, before, state = run_finder(tmp_path, [release()], [
        "--latest", "--candidate-id", "101", "--enqueue-qbittorrent",
    ], watched=5)
    assert report["status"] == "latest_already_handled"
    assert report["qbittorrent"]["status"] == "not_attempted"
    submit.assert_not_called()
    assert (tmp_path / "state.json").read_bytes() == before


def test_incomplete_latest_discovery_never_submits_pinned_result(tmp_path):
    _, report, submit, before, state = run_finder(tmp_path, [release()], [
        "--latest", "--candidate-id", "101", "--enqueue-qbittorrent",
    ], failures=["second query timed out"])
    assert report["status"] == "latest_unresolved"
    submit.assert_not_called()
    assert (tmp_path / "state.json").read_bytes() == before


@pytest.mark.parametrize("complete", [True, False])
def test_pinned_whole_season_still_requires_file_coverage(tmp_path, complete):
    batch = release(title="[G] Example Anime S01 [01-02] Complete", size="2.8 GiB")
    client = Mock(spec=NyaaClient)
    client.get.return_value = NyaaReleaseDetail(
        release=NyaaRelease("101", batch.title, "Anime", "2.8 GiB", nyaa.parse_size("2.8 GiB"),
                            None, None, 10, 0, 0, batch.url, f'{101:040x}'),
        description="", files=tuple(
            NyaaFileEntry(f"Example Anime S01E{ep:02d}.mkv", "1.4 GiB", nyaa.parse_size("1.4 GiB"))
            for ep in ((1, 2) if complete else (1,))
        ),
    )
    _, report, submit, before, _ = run_finder(tmp_path, [batch], [
        "--whole-season", "--candidate-id", "101", "--no-state-update",
    ], client=client)
    if complete:
        assert report["status"] == "found"
        assert report["selected"]["coverage"]["complete"] is True
    else:
        assert report["status"] == "no_complete_season_release"
    assert (tmp_path / "state.json").read_bytes() == before
    submit.assert_not_called()


@pytest.mark.parametrize("missing", [False, True])
def test_candidate_absent_from_search_uses_its_detail_page(tmp_path, missing):
    client = Mock(spec=NyaaClient)
    if missing:
        client.get.side_effect = NyaaNotFoundError("not found")
    else:
        client.get.return_value = NyaaReleaseDetail(
            release=NyaaRelease("101", "[G] Example Anime S01E05 [1080p]", "Anime", "1.4 GiB",
                                nyaa.parse_size("1.4 GiB"), None, None, 10, 0, 0,
                                "https://nyaa.si/view/101", info_hash=f"{101:040x}"),
            description="Subtitles: English", files=(),
        )
    code, report, submit, _, state = run_finder(tmp_path, [release(202, score=200)], [
        "--episode", "5", "--candidate-id", "101", "--enqueue-qbittorrent",
    ], client=client)
    client.get.assert_called_once()
    if missing:
        assert code == 4
        assert report["status"] == "candidate_not_found"
        submit.assert_not_called()
        assert state["shows"][0]["watched_episode"] == 4
    else:
        assert code == 0
        assert f"{101:040x}" in submit.call_args.args[0]
        assert report["diagnostic"]["candidate_id_direct_fetched"] == ["101"]


def test_latest_target_is_independent_of_candidate_quality(tmp_path):
    _, report, submit, _, _ = run_finder(tmp_path, [release(), release(202, episode=6, size="0.5 GiB")], [
        "--latest", "--candidate-id", "101", "--enqueue-qbittorrent",
    ])
    assert report["target_episode"] == 6
    submit.assert_not_called()


@pytest.mark.parametrize("error_code", ["handoff_unverified", "permission_denied", "client_busy"])
def test_pinned_enqueue_failure_does_not_advance_progress(tmp_path, error_code):
    code, report, submit, before, _ = run_finder(tmp_path, [release()], [
        "--episode", "5", "--candidate-id", "101", "--enqueue-qbittorrent",
    ], submission={"ok": False, "status": "error", "error_code": error_code})
    assert code == 6
    assert report["status"] == "download_enqueue_failed"
    assert report["qbittorrent"]["error_code"] == error_code
    submit.assert_called_once()
    assert (tmp_path / "state.json").read_bytes() == before


@pytest.mark.parametrize("options", [
    ["--defer-state-until-download-complete"],
    ["--candidate-id", "bad", "--episode", "5"],
    ["--candidate-id", "101"],
    ["--candidate-id", "101", "--episode", "5", "--latest"],
])
def test_invalid_or_retired_options_stop_before_state_or_network(options):
    with patch.object(v2_workflow, "load_state") as load, patch.object(v2_workflow, "submit_magnet") as submit:
        assert finder.main(["Example Anime", *options]) == 2
    load.assert_not_called()
    submit.assert_not_called()


def test_documented_search_commands_parse_with_the_named_entrypoint():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    commands = re.findall(r"^python scripts/(find_anime_release|search_nyaa_releases)\.py (.+)$", text, re.M)
    assert commands
    for script, command in commands:
        argv = shlex.split(command)
        if script == "find_anime_release":
            finder.build_parser().parse_args(argv)
        else:
            nyaa.parse_args(argv)
