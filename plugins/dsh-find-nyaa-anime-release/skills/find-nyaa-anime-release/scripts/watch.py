#!/usr/bin/env python3
"""Public v3 watch command."""
import sys
from watch_v3.cli import run

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(run())
