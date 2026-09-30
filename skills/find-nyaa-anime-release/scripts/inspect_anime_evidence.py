#!/usr/bin/env python3
"""Read complete Nyaa evidence, without token-saving title expansion or filtering."""
import argparse
import json
import sys
from pathlib import Path

from anime_release import raw_evidence as evidence
from anime_release.repository import StateRepository, require_record
from runtime_paths import DEFAULT_STATE


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('search', help='One exact query, chronological page, every row')
    listing.add_argument('query')
    listing.add_argument('--page', type=int, default=1)
    listing.add_argument('--timeout', type=int, default=20)
    listing.add_argument('--output', type=Path, required=True)
    detail = sub.add_parser('detail', help='Complete description and file list for one ID')
    detail.add_argument('candidate_id')
    detail.add_argument('--timeout', type=int, default=20)
    detail.add_argument('--output', type=Path, required=True)
    draft = sub.add_parser('draft', help='Unreviewed form; no inferred judgments or submission')
    draft.add_argument('--state', type=Path, default=DEFAULT_STATE)
    draft.add_argument('--track-id', required=True)
    draft.add_argument('--listing', type=Path, action='append', required=True)
    draft.add_argument('--detail', type=Path, required=True)
    draft.add_argument('--intent', choices=['latest_regular', 'specific_episode', 'next_tracked'], required=True)
    draft.add_argument('--episode', type=int, required=True)
    draft.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'search':
            result = evidence.listing(args.query, args.page, timeout=args.timeout)
        elif args.command == 'detail':
            result = evidence.details(args.candidate_id, timeout=args.timeout)
        else:
            track = require_record(StateRepository(args.state).read(), args.track_id)
            result = evidence.draft(track, args.listing, args.detail, args.intent, args.episode)
        from evidence_artifacts import output_path, register, collect_expired
        state_path = getattr(args,'state',DEFAULT_STATE)
        target = output_path(args.output,state_path)
        saved = evidence.save(target, result)
        register(saved,state_path)
        result['output_path'] = str(saved)
        collect_expired(state_path)
        # All source rows/text are also kept in the file when a tool truncates stdout.
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'evidence_read_failed', 'error_type': type(exc).__name__,
                          'error': str(exc), 'output_written': False}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
