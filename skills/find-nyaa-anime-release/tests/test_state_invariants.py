from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import airing_watch_state as watch_state
import find_anime_release as finder
import state_io


def show(title: str, watched: int, *, anilist_id: int) -> dict[str, object]:
    return {
        "title": title,
        "aliases": [],
        "anilist_id": anilist_id,
        "season": "S01",
        "watched_episode": watched,
        "latest_known_episode": watched,
        "next_episode": watched + 1,
        "airing": True,
        "status": "airing",
    }


class CorruptStateTests(unittest.TestCase):
    def test_state_cli_preserves_corrupt_file_and_returns_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            original = b'{"version": 1, "shows": ['
            path.write_bytes(original)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = watch_state.main(
                    ["--state", str(path), "record-found", "Example", "--episode", "2"]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(2, code)
            self.assertEqual("state_corrupt", payload["status"])
            self.assertEqual(original, path.read_bytes())

    def test_high_level_cli_stops_before_network_on_corrupt_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            original = b"not-json"
            path.write_bytes(original)
            output = io.StringIO()
            with (
                patch.object(finder, "resolve_title") as resolve,
                contextlib.redirect_stdout(output),
            ):
                code = finder.main(["Example", "--state", str(path), "--json"])
            payload = json.loads(output.getvalue())
            self.assertEqual(2, code)
            self.assertEqual("state_corrupt", payload["status"])
            self.assertEqual("unchanged", payload["state_update"])
            self.assertEqual(original, path.read_bytes())
            resolve.assert_not_called()

    def test_invalid_state_shape_is_not_silently_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            original = b'{"version":1,"shows":"wrong"}'
            path.write_bytes(original)
            with self.assertRaises(state_io.StateFileError):
                state_io.load_state(path)
            self.assertEqual(original, path.read_bytes())

    def test_failed_atomic_replace_preserves_previous_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            original = {"version": 1, "shows": [show("A", 1, anilist_id=1)]}
            state_io.save_state(path, original)
            before = path.read_bytes()
            changed = {"version": 1, "shows": [show("A", 2, anilist_id=1)]}
            with patch.object(state_io.os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    state_io.save_state(path, changed)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual([], list(path.parent.glob("state.json.*.tmp")))


class ConcurrentStateMergeTests(unittest.TestCase):
    def test_twenty_simultaneous_titles_do_not_lose_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state_io.save_state(path, {"version": 1, "shows": []})
            barrier = threading.Barrier(20)

            def worker(index: int) -> None:
                base = state_io.load_state(path)
                desired = copy.deepcopy(base)
                desired["shows"].append(show(f"Show {index}", index, anilist_id=index + 1))
                barrier.wait(timeout=5)
                state_io.save_state(path, desired, base=base)

            with ThreadPoolExecutor(max_workers=20) as pool:
                list(pool.map(worker, range(20)))

            saved = state_io.load_state(path)
            self.assertEqual(20, len(saved["shows"]))
            self.assertEqual({f"Show {index}" for index in range(20)}, {item["title"] for item in saved["shows"]})

    def test_concurrent_different_titles_are_both_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            base = {"version": 1, "shows": []}
            state_io.save_state(path, base)
            first = copy.deepcopy(base)
            first["shows"].append(show("Alpha", 2, anilist_id=1))
            second = copy.deepcopy(base)
            second["shows"].append(show("Beta", 4, anilist_id=2))

            state_io.save_state(path, first, base=base)
            state_io.save_state(path, second, base=base)

            saved = state_io.load_state(path)
            self.assertEqual({"Alpha", "Beta"}, {item["title"] for item in saved["shows"]})

    def test_stale_same_title_writer_cannot_move_progress_backward(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            base = {"version": 1, "shows": [show("Alpha", 5, anilist_id=1)]}
            state_io.save_state(path, base)
            episode_seven = copy.deepcopy(base)
            watch_state.record_found_episode(episode_seven, "Alpha", 7)
            episode_six = copy.deepcopy(base)
            watch_state.record_found_episode(episode_six, "Alpha", 6)

            state_io.save_state(path, episode_seven, base=base)
            state_io.save_state(path, episode_six, base=base)

            saved = state_io.load_state(path)["shows"][0]
            self.assertEqual(7, saved["watched_episode"])
            self.assertEqual(7, saved["latest_known_episode"])
            self.assertEqual(8, saved["next_episode"])

    def test_delete_delta_does_not_remove_a_concurrent_new_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            base = {"version": 1, "shows": [show("Alpha", 5, anilist_id=1)]}
            state_io.save_state(path, base)
            concurrent = copy.deepcopy(base)
            concurrent["shows"].append(show("Beta", 1, anilist_id=2))
            deletion = {"version": 1, "shows": []}

            state_io.save_state(path, concurrent, base=base)
            state_io.save_state(path, deletion, base=base)

            saved = state_io.load_state(path)
            self.assertEqual(["Beta"], [item["title"] for item in saved["shows"]])


if __name__ == "__main__":
    unittest.main()
