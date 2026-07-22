#!/usr/bin/env python3
"""Portable runtime paths for the release finder."""

from __future__ import annotations

import os
from pathlib import Path


LEGACY_STATE = Path(r"C:\User_data\Download\Anime_Tracking\airing_watch_state.json")


def default_state_path() -> Path:
    override = os.environ.get("ANIME_TRACKING_STATE")
    if override:
        return Path(override).expanduser()
    if LEGACY_STATE.exists():
        return LEGACY_STATE
    return Path.home() / "Downloads" / "Anime_Tracking" / "airing_watch_state.json"


DEFAULT_STATE = default_state_path()
