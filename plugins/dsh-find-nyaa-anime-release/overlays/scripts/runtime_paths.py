#!/usr/bin/env python3
"""Portable DSH runtime paths; never discover or migrate another host's records."""
from dsh_paths import state_path


def default_state_path():
    return state_path()


DEFAULT_STATE = default_state_path()
