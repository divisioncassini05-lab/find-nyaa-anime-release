"""Crash-safe, concurrency-safe persistence for airing watch state."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class StateFileError(RuntimeError):
    """The tracking state cannot be trusted and must not be overwritten."""


_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _local_lock(path: Path) -> threading.RLock:
    key = str(path.resolve()).casefold()
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "shows": []}


def _norm(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _validate_state(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise StateFileError(f"追番状态文件格式损坏：{path}（根节点不是对象）")
    shows = data.get("shows", [])
    if not isinstance(shows, list) or not all(isinstance(show, dict) for show in shows):
        raise StateFileError(f"追番状态文件格式损坏：{path}（shows 不是对象列表）")
    data.setdefault("version", 1)
    data.setdefault("shows", [])
    return data


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateFileError(f"追番状态文件无法读取，已保留原文件：{path}（{exc}）") from exc
    return _validate_state(data, path)


@contextmanager
def _state_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with _local_lock(path):
        with lock_path.open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _show_names(show: dict[str, Any]) -> set[str]:
    values = [show.get("title"), *show.get("aliases", []), *show.get("search_titles", [])]
    return {_norm(value) for value in values if isinstance(value, str) and _norm(value)}


def _same_show(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("anilist_id", "bangumi_id"):
        left_id = left.get(key)
        right_id = right.get(key)
        if isinstance(left_id, int) and isinstance(right_id, int) and left_id == right_id:
            return True
    return bool(_show_names(left) & _show_names(right))


def _find_show(shows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    matches = [show for show in shows if _same_show(show, target)]
    return matches[0] if len(matches) == 1 else None


def _merge_list(current: Any, desired: list[Any]) -> list[Any]:
    result = list(current) if isinstance(current, list) else []
    for item in desired:
        if item not in result:
            result.append(copy.deepcopy(item))
    return result


def _apply_show_delta(
    current: dict[str, Any],
    base: dict[str, Any] | None,
    desired: dict[str, Any],
) -> None:
    baseline = base or {}
    missing = object()
    for key in set(baseline) | set(desired):
        before = baseline.get(key, missing)
        after = desired.get(key, missing)
        if before == after:
            continue
        if key not in desired:
            current.pop(key, None)
            continue
        value = desired[key]
        if key in {"watched_episode", "latest_known_episode", "next_episode"}:
            values = [item for item in (current.get(key), value) if isinstance(item, int)]
            current[key] = max(values) if values else copy.deepcopy(value)
        elif key in {"aliases", "search_titles", "verified_search_titles", "related_titles"} and isinstance(value, list):
            current[key] = _merge_list(current.get(key), value)
        elif key == "updated_at" and isinstance(value, str) and isinstance(current.get(key), str):
            current[key] = max(current[key], value)
        else:
            current[key] = copy.deepcopy(value)


def merge_state(
    current: dict[str, Any],
    base: dict[str, Any],
    desired: dict[str, Any],
) -> dict[str, Any]:
    """Apply only this run's changes to the newest on-disk state."""

    merged = copy.deepcopy(current)
    merged.setdefault("shows", [])
    current_shows = merged["shows"]
    base_shows = base.get("shows", [])
    desired_shows = desired.get("shows", [])

    for base_show in base_shows:
        if _find_show(desired_shows, base_show) is None:
            current_match = _find_show(current_shows, base_show)
            if current_match is not None:
                current_shows.remove(current_match)

    for desired_show in desired_shows:
        base_show = _find_show(base_shows, desired_show)
        if base_show is not None and base_show == desired_show:
            continue
        current_show = _find_show(current_shows, desired_show)
        if current_show is None:
            current_shows.append(copy.deepcopy(desired_show))
        else:
            _apply_show_delta(current_show, base_show, desired_show)

    missing = object()
    for key in set(base) | set(desired):
        if key == "shows" or base.get(key, missing) == desired.get(key, missing):
            continue
        if key not in desired:
            merged.pop(key, None)
        else:
            merged[key] = copy.deepcopy(desired[key])
    merged["version"] = max(
        value for value in (current.get("version", 1), desired.get("version", 1)) if isinstance(value, int)
    )
    return merged


def save_state(path: Path, data: dict[str, Any], *, base: dict[str, Any] | None = None) -> None:
    _validate_state(data, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _state_lock(path):
        payload = data
        if base is not None:
            current = load_state(path)
            payload = copy.deepcopy(data) if current == base else merge_state(current, base, data)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        temp = Path(handle.name)
        try:
            with handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
