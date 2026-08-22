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
        "watched_episode": show.get("watched_episode"),
        "latest_known_episode": show.get("latest_known_episode"),
        "next_episode": show.get("next_episode"),
        "airing": show.get("airing"),
        "tracking_status": show.get("status"),
        "search_titles": show.get("search_titles", []),
        "verified_search_titles": show.get("verified_search_titles", []),
        "pending_download": show.get("pending_download"),
    }


def completed_episode(show: dict[str, Any] | None) -> int | None:
    if show is None:
        return None
    values: list[int] = []
    watched_episode = show.get("watched_episode")
    if isinstance(watched_episode, int):
        values.append(watched_episode)
    next_episode = show.get("next_episode")
    if isinstance(next_episode, int) and next_episode > 1:
        values.append(next_episode - 1)
    return max(values) if values else None


def pending_download(show: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a well-formed queued download without treating it as watched progress."""
    if show is None:
        return None
    value = show.get("pending_download")
    if not isinstance(value, dict):
        return None
    episode = value.get("episode")
    if not isinstance(episode, int) or episode < 1:
        return None
    return value


def record_pending_download(
    data: dict[str, Any],
    query: str,
    *,
    episode: int,
    season: str | None = None,
    info_hash: str | None = None,
    magnet: str | None = None,
    release_title: str | None = None,
    nyaa_url: str | None = None,
) -> dict[str, Any]:
    """Persist a queued qBittorrent target while leaving watched progress unchanged."""
    show = find_show(data, query)
    if show is None:
        return {
            "status": "not_tracked",
            "tracked": False,
            "title": query,
            "episode": episode,
        }
    current = pending_download(show)
    if current is not None:
        current_hash = str(current.get("info_hash") or "").casefold()
        requested_hash = str(info_hash or "").casefold()
        if current.get("episode") == episode and (
            not requested_hash or not current_hash or requested_hash == current_hash
        ):
            return {
                "status": "unchanged",
                "tracked": True,
                "title": show.get("title"),
                "episode": episode,
                "pending_download": current,
                "reason": "same_download_already_pending",
            }
        return {
            "status": "conflict",
            "tracked": True,
            "title": show.get("title"),
            "episode": episode,
            "pending_download": current,
            "reason": "another_download_is_pending",
        }

    queued: dict[str, Any] = {
        "episode": episode,
        "queued_at": now_iso(),
    }
    for key, value in (
        ("season", season),
        ("info_hash", info_hash),
        ("magnet", magnet),
        ("release_title", release_title),
        ("nyaa_url", nyaa_url),
    ):
        if value not in (None, ""):
            queued[key] = value
    show["pending_download"] = queued
    show["status"] = "waiting"
    show["airing"] = True
    show["notes"] = (
        f"Regular episode {episode} was accepted by qBittorrent but is not confirmed complete; "
        "watched progress remains unchanged until completion is observed."
    )
    show["updated_at"] = now_iso()
    return {
        "status": "pending",
        "tracked": True,
        "title": show.get("title"),
        "episode": episode,
        "pending_download": queued,
        "watched_episode": show.get("watched_episode"),
        "latest_known_episode": show.get("latest_known_episode"),
        "next_episode": show.get("next_episode"),
    }


def clear_pending_download(
    data: dict[str, Any],
    query: str,
    *,
    episode: int | None = None,
    info_hash: str | None = None,
) -> dict[str, Any]:
    """Clear only the matching queued target; stale retry runs cannot clear a newer one."""
    show = find_show(data, query)
    if show is None:
        return {"status": "not_tracked", "tracked": False, "title": query}
    current = pending_download(show)
    if current is None:
        return {"status": "unchanged", "tracked": True, "title": show.get("title"), "reason": "no_pending_download"}
    if episode is not None and current.get("episode") != episode:
        return {"status": "unchanged", "tracked": True, "title": show.get("title"), "pending_download": current, "reason": "episode_mismatch"}
    if info_hash and str(current.get("info_hash") or "").casefold() != info_hash.casefold():
        return {"status": "unchanged", "tracked": True, "title": show.get("title"), "pending_download": current, "reason": "info_hash_mismatch"}
    removed = show.pop("pending_download")
    show["updated_at"] = now_iso()
    return {"status": "cleared", "tracked": True, "title": show.get("title"), "pending_download": removed}


def record_found_episode(
    data: dict[str, Any],
    query: str,
    episode: int,
) -> dict[str, Any]:
    show = find_show(data, query)
    if show is None:
        return {
            "status": "not_tracked",
            "tracked": False,
            "title": query,
            "episode": episode,
        }

    current_completed = completed_episode(show)
    if current_completed is not None and episode <= current_completed:
        return {
            "status": "unchanged",
            "tracked": True,
            "title": show.get("title"),
            "episode": episode,
            "watched_episode": show.get("watched_episode"),
            "latest_known_episode": show.get("latest_known_episode"),
            "next_episode": show.get("next_episode"),
            "reason": "requested_episode_not_ahead_of_completed_progress",
        }

    watched_episode = episode
    current_latest = show.get("latest_known_episode")
    latest_known_episode = max(
        episode,
        current_latest if isinstance(current_latest, int) else 0,
    )
    current_next = show.get("next_episode")
    next_episode = max(
        watched_episode + 1,
        current_next if isinstance(current_next, int) else 1,
    )

    show["watched_episode"] = watched_episode
    show["latest_known_episode"] = latest_known_episode
    show["next_episode"] = next_episode
    show["status"] = "airing"
    show["airing"] = True
    show["notes"] = (
        f"Successfully found regular episode {episode}; "
        f"treated as watched. Next target is episode {next_episode}."
    )
    queued = pending_download(show)
    if queued is not None and queued.get("episode", 0) <= episode:
        show.pop("pending_download", None)
    show["updated_at"] = now_iso()
    return {
        "status": "recorded",
        "tracked": True,
        "title": show.get("title"),
        "episode": episode,
        "watched_episode": watched_episode,
        "latest_known_episode": latest_known_episode,
        "next_episode": next_episode,
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

    p_record_found = sub.add_parser(
        "record-found",
        help="Record a successfully returned regular episode as watched",
    )
    p_record_found.add_argument("title")
    p_record_found.add_argument("--episode", type=int, required=True)

    p_record_pending = sub.add_parser(
        "record-pending",
        help="Record a qBittorrent-accepted regular episode without advancing watched progress",
    )
    p_record_pending.add_argument("title")
    p_record_pending.add_argument("--episode", type=int, required=True)
    p_record_pending.add_argument("--season")
    p_record_pending.add_argument("--info-hash")
    p_record_pending.add_argument("--magnet")
    p_record_pending.add_argument("--release-title")
    p_record_pending.add_argument("--nyaa-url")

    p_clear_pending = sub.add_parser(
        "clear-pending",
        help="Clear a matching queued download after qBittorrent confirms completion",
    )
    p_clear_pending.add_argument("title")
    p_clear_pending.add_argument("--episode", type=int)
    p_clear_pending.add_argument("--info-hash")

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
    elif args.cmd == "record-found":
        if args.episode < 1:
            parser.error("--episode must be a positive integer")
        result = record_found_episode(data, args.title, args.episode)
        if result["status"] == "recorded":
            save_state(args.state, data)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in {"recorded", "unchanged"} else 1
    elif args.cmd == "record-pending":
        if args.episode < 1:
            parser.error("--episode must be a positive integer")
        result = record_pending_download(
            data,
            args.title,
            episode=args.episode,
            season=args.season,
            info_hash=args.info_hash,
            magnet=args.magnet,
            release_title=args.release_title,
            nyaa_url=args.nyaa_url,
        )
        if result["status"] in {"pending", "unchanged"}:
            save_state(args.state, data)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in {"pending", "unchanged"} else 1
    elif args.cmd == "clear-pending":
        result = clear_pending_download(
            data,
            args.title,
            episode=args.episode,
            info_hash=args.info_hash,
        )
        if result["status"] == "cleared":
            save_state(args.state, data)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] in {"cleared", "unchanged"} else 1
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
