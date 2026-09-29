"""Extracted policy module: cli."""

from __future__ import annotations
from .settings import DEFAULT_CACHE, DEFAULT_SCHEDULE_CACHE

import argparse
from pathlib import Path

from qbittorrent_submit import DEFAULT_SAVE_PATH as DEFAULT_QBITTORRENT_SAVE_PATH
from runtime_paths import DEFAULT_STATE
from state_io import StateFileError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, help='Agent-reviewed complete page evidence; bypass heuristic discovery, not objective delivery checks')
    parser.add_argument('--identity-evidence', type=Path, help='Agent-reviewed official work/season binding evidence JSON')
    parser.add_argument("title")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--tier", default="browse", choices=["browse", "watch", "premium"])
    parser.add_argument("--season")
    parser.add_argument("--episode", type=int)
    parser.add_argument(
        "--candidate-id",
        help="Finalize exactly one reviewed Nyaa ID or view URL; requires --episode, --latest, or --whole-season. No automatic quality fallback.",
    )
    parser.add_argument("--min-gib-per-episode", type=float)
    parser.add_argument("--max-gib-per-episode", type=float)
    parser.add_argument(
        "--allow-upward-compatibility",
        action="store_true",
        help=(
            "For named tiers only, treat the tier's upper size target as a "
            "soft preference and accept a higher tier when the lower floor "
            "and all other checks pass; explicit max bounds stay hard."
        ),
    )
    parser.add_argument("--timeout", type=int, default=8)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument(
        "--query-limit",
        type=int,
        default=2,
        help="Maximum metadata title queries; one protected broad query may be added.",
    )
    parser.add_argument(
        "--search-title",
        action="append",
        help="Verified English/romaji Nyaa title supplied by the bounded web-resolution fallback.",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--offline-catalog", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "identity_catalog.json")
    parser.add_argument("--source-numbering", choices=['anidb','tvdb'])
    parser.add_argument("--target-numbering", choices=['anidb','tvdb'])
    parser.add_argument("--schedule-cache", type=Path, default=DEFAULT_SCHEDULE_CACHE)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--include-magnet", "--include-magnets", dest="include_magnet", action="store_true")
    parser.add_argument(
        "--enqueue-qbittorrent",
        action="store_true",
        help="Silently submit the final qualified magnet to the local qBittorrent client.",
    )
    parser.add_argument(
        "--defer-state-until-download-complete",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--qbittorrent-exe", type=Path)
    parser.add_argument("--qbittorrent-profile", type=Path)
    parser.add_argument("--qbittorrent-backup-dir", type=Path)
    parser.add_argument(
        "--qbittorrent-save-path",
        type=Path,
        default=DEFAULT_QBITTORRENT_SAVE_PATH,
    )
    parser.add_argument("--include-page-link", action="store_true")
    parser.add_argument("--legal-ok", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-web-resolve", action="store_true")
    parser.add_argument("--no-state-update", action="store_true")
    parser.add_argument("--mark-finished", action="store_true")
    parser.add_argument("--completion-evidence", type=Path,
                        help="Agent-reviewed official final-episode/end-date evidence JSON")
    parser.add_argument("--latest", action="store_true", help="Find the latest regular episode using airing metadata.")
    parser.add_argument(
        "--official-air-date",
        action="store_true",
        help="Return the read-only official AniList airing date for --episode and skip Nyaa search.",
    )
    parser.add_argument(
        "--whole-season",
        action="store_true",
        help="Find one verified package covering the complete target season.",
    )
    parser.add_argument("--include-specials", action="store_true", help="Select a special/OVA after explicit user confirmation.")
    parser.add_argument("--explain", action="store_true", help="Include compact staged diagnostics in the JSON report.")
    parser.add_argument("--want-zh", action="store_true")
    parser.add_argument(
        "--require-zh",
        action="store_true",
        help="Require Simplified or Traditional Chinese subtitles verified from the Nyaa detail page.",
    )
    parser.add_argument(
        "--release-group-hint",
        action="append",
        default=[],
        help="Preferred release-group clue for a strict subtitle search; repeatable.",
    )
    parser.add_argument("--airing-priority", action="store_true")
    parser.add_argument("--no-auto-batch", action="store_true", help=argparse.SUPPRESS)
    return parser


def status_return_code(status: str) -> int | None:
    return {
        "found": 0,
        "latest_already_handled": 0,
        "airing_schedule_break": 0,
        "long_break_unconfirmed": 0,
        "split_cour_break": 0,
        "part_finished": 0,
        "completed": 0,
        "needs_completion_review": 0,
        "finished_deleted": 0,
        "needs_quality_upgrade_confirmation": 0,
        "network_error": 1,
        "review_required": 2,
        "latest_unresolved": 4,
        "release_unqualified": 3,
        "subtitle_unqualified": 3,
        "subtitle_check_incomplete": 3,
        "season_check_incomplete": 3,
        "no_complete_season_release": 4,
        "no_nyaa_release_for_target": 4,
        "candidate_not_found": 4,
        "candidate_id_title_mismatch": 4,
        "output_incomplete": 5,
        "download_enqueue_failed": 6,
    }.get(status)


def main(argv=None):
    from .workflow import run
    from .models import WorkflowError
    from .trace import TRACE
    from .queries import emit_json
    args = build_parser().parse_args(argv)
    token = TRACE.set([])
    try:
        if args.review:
            from .reviewed import run as run_reviewed
            return run_reviewed(args)
        return run(args)
    except WorkflowError as exc:
        report = {'status': exc.code, 'error_detail': exc.as_dict(), 'state_update': 'not_confirmed',
                  'reply_text': str(exc)}
        emit_json(report) if args.json else print(report['reply_text'])
        return 6 if exc.stage in {'delivery', 'state_commit'} else 4
    except (StateFileError, OSError) as exc:
        from .trace import TRACE as trace
        stage = (trace.get() or [{'stage': 'request'}])[-1]['stage']
        error = WorkflowError(stage, 'permission_denied' if isinstance(exc, PermissionError) else 'io_failed',
                              False, (), 'inspect_execution_context_and_state')
        emit_json({'status': error.code, 'error_detail': error.as_dict(), 'state_update': 'not_confirmed'})
        return 6 if stage in {'delivery', 'state_commit'} else 2
    finally:
        TRACE.reset(token)

