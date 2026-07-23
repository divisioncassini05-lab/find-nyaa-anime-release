#!/usr/bin/env python3
"""Track current-season anime search/watch state for this user."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_paths import DEFAULT_STATE


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "shows": []}
    with path.open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    data.setdefault("version", 1)
    data.setdefault("shows", [])
    return data


def save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def names_for(show: dict[str, Any]) -> list[str]:
    names = [show.get("title", "")]
    names.extend(show.get("aliases", []))
    return [x for x in names if x]


def find_show(data: dict[str, Any], query: str) -> dict[str, Any] | None:
    q = norm(query)
    if not q:
        return None

    exact_matches: list[dict[str, Any]] = []
    for show in data.get("shows", []):
        for name in names_for(show):
            n = norm(name)
            if q == n:
                exact_matches.append(show)
                break
    if len(exact_matches) == 1:
        return exact_matches[0]
    if exact_matches or len(q) < 4:
        return None

    partial_matches: list[dict[str, Any]] = []
    for show in data.get("shows", []):
        for name in names_for(show):
            n = norm(name)
            if n and (q in n or n in q):
                partial_matches.append(show)
                break
    if len({id(show) for show in partial_matches}) == 1:
        return partial_matches[0]
    return None


def upsert_show(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    show = find_show(data, args.title)
    if show is None:
        show = {"title": args.title, "aliases": [], "airing": True, "created_at": now_iso()}
        data["shows"].append(show)

    aliases = list(dict.fromkeys(show.get("aliases", []) + (args.alias or [])))
    if args.season is not None:
        show["season"] = args.season
    if args.watched is not None:
        show["watched_episode"] = args.watched
    if args.latest is not None:
        show["latest_known_episode"] = args.latest
    if args.next_episode is not None:
        show["next_episode"] = args.next_episode
    elif args.latest is not None:
        current_next = show.get("next_episode")
        if not isinstance(current_next, int) or current_next <= args.latest:
            show["next_episode"] = args.latest + 1
    if args.status is not None:
        show["status"] = args.status
    if args.notes is not None:
        show["notes"] = args.notes
    show["aliases"] = aliases
    show["airing"] = not args.old
    show["updated_at"] = now_iso()
    return show


def print_show(show: dict[str, Any] | None) -> None:
    if show is None:
        print("No tracked airing show matched.")
        return
    print(json.dumps(show, ensure_ascii=False, indent=2))


def probe_payload(show: dict[str, Any] | None) -> dict[str, Any]:
    if show is None:
        return {"status": "not_tracked", "tracked": False}
    return {
        "status": "tracked",
        "tracked": True,
        "title": show.get("title"),
        "aliases": show.get("aliases", []),
        "season": show.get("season"),
        "latest_known_episode": show.get("latest_known_episode"),
        "next_episode": show.get("next_episode"),
        "airing": show.get("airing"),
        "tracking_status": show.get("status"),
        "search_titles": show.get("search_titles", []),
        "verified_search_titles": show.get("verified_search_titles", []),
    }


def delete_show(data: dict[str, Any], query: str) -> dict[str, Any] | None:
    show = find_show(data, query)
    if show is None:
        return None
    data["shows"] = [item for item in data.get("shows", []) if item is not show]
    return show


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="Find a tracked airing show by title/alias")
    p_get.add_argument("title")

    p_probe = sub.add_parser(
        "probe",
        help="Read a compact tracked-show target without modifying state",
    )
    p_probe.add_argument("title")

    p_list = sub.add_parser("list", help="List tracked airing shows")

    p_update = sub.add_parser("update", help="Create or update an airing show")
    p_update.add_argument("title")
    p_update.add_argument("--alias", action="append")
    p_update.add_argument("--season")
    p_update.add_argument("--watched", type=int)
    p_update.add_argument("--latest", type=int)
    p_update.add_argument("--next-episode", type=int)
    p_update.add_argument("--status", choices=["airing", "waiting", "finished", "paused"])
    p_update.add_argument("--notes")
    p_update.add_argument("--old", action="store_true", help="Mark as not an airing/new show")

    p_delete = sub.add_parser("delete", help="Remove a show from airing tracking")
    p_delete.add_argument("title")

    args = parser.parse_args(argv)
    data = load_state(args.state)

    if args.cmd == "get":
        print_show(find_show(data, args.title))
    elif args.cmd == "probe":
        print(json.dumps(probe_payload(find_show(data, args.title)), ensure_ascii=False))
    elif args.cmd == "list":
        print(json.dumps(data.get("shows", []), ensure_ascii=False, indent=2))
    elif args.cmd == "update":
        show = upsert_show(data, args)
        save_state(args.state, data)
        print_show(show)
    elif args.cmd == "delete":
        show = delete_show(data, args.title)
        if show is not None:
            save_state(args.state, data)
        print_show(show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
