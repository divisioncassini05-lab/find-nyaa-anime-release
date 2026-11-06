"""Normalize request intent once, before any identity or provider work."""
from .models import ReleaseRequest, WorkflowError
from release_identity import parse_release_identity, normalize_season_number

def from_args(args):
    parsed = parse_release_identity(args.title)
    season = normalize_season_number(args.season) if args.season else parsed.season
    if args.season and parsed.season and season != parsed.season:
        raise WorkflowError('request', 'conflicting_explicit_season', False, (), 'clarify_season')
    intent = ('specific_episode' if args.episode is not None else 'latest_regular' if args.latest
              else 'season_batch' if args.whole_season else 'next_tracked')
    return ReleaseRequest(args.title, f'S{season:02d}' if season else None, args.episode, intent,
        args.no_state_update, args.enqueue_qbittorrent, args.require_zh, args.want_zh,
        args.min_gib_per_episode, args.max_gib_per_episode, args.candidate_id)
