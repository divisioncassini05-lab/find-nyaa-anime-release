#!/usr/bin/env python3
"""Preview/apply v3 migration through the single repository."""
import sys
from watch_v3.cli import run
if __name__ == '__main__':
    args = sys.argv[1:]
    state = []
    if '--state' in args:
        pos = args.index('--state')
        state = args[pos:pos + 2]
        del args[pos:pos + 2]
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(run([*state, 'migrate', *args]))
