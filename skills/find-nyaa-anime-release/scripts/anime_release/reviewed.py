"""Agent interprets full evidence; code enforces freshness, constraints and receipts."""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from nyaa_client import NyaaClient, NyaaClientError, nyaa_id_from_url, magnet_from_hash
from qbittorrent_submit import submit_magnet, extract_btih, DEFAULT_BACKUP_DIR, SubmissionError
from . import raw_evidence as evidence
from .delivery import finalize
from .models import WorkIdentity, TargetDecision, VerifiedRelease, ReleaseRequest, WorkflowError, StateCommand
from .repository import StateRepository, require_record, handled


VIDEO = {'.mkv', '.mp4', '.m4v', '.avi', '.ts', '.m2ts', '.webm'}
BOUNDS = {'browse': (1.0, 2.0), 'watch': (2.0, 4.0), 'premium': (6.0, None)}


def need(condition, code, stage='review', detail=()):
    if not condition:
        raise WorkflowError(stage, code, False, tuple(detail), 'inspect_full_evidence')


def load_report(path, kind):
    try:
        report = evidence.read(path, kind)
        checked = datetime.fromisoformat(report['checked_at'])
        age = datetime.now(timezone.utc) - checked
        need(timedelta(minutes=-5) <= age <= timedelta(hours=24), 'stale_evidence')
        return report
    except (ValueError, KeyError, TypeError) as exc:
        raise WorkflowError('review', 'invalid_evidence', evidence=(str(exc),)) from exc


def resolve_path(base, value):
    need(isinstance(value, str) and bool(value), 'missing_evidence_path')
    path = Path(value)
    return path if path.is_absolute() else base / path


def require_quotes(quotes, material, code):
    need(isinstance(quotes, list) and bool(quotes), code)
    need(all(isinstance(q, str) and bool(q.strip()) and q in material for q in quotes), code)


def listing_identity(report):
    return {'query': report['query'], 'page': report['page'], 'later_pages': report['later_pages'],
            'rows': [{key: row.get(key) for key in ('nyaa_id', 'title', 'size_bytes', 'info_hash', 'published_at')}
                     for row in report['rows']]}


def audit(args, *, client=None, track=None):
    """No state writes or client submission. Semantic decisions come only from review."""
    client = client or NyaaClient()
    from evidence_artifacts import input_path
    review_path = input_path(args.review)
    try:
        review = json.loads(review_path.read_text(encoding='utf-8-sig'))
    except (ValueError, TypeError) as exc:
        raise WorkflowError('review', 'invalid_review', evidence=(str(exc),)) from exc
    need(isinstance(review, dict) and review.get('schema_version') == 1
         and review.get('reviewed') is True, 'agent_review_required')
    if track is None:
        state = StateRepository(args.state).read()
        track = require_record(state, review.get('track_id'))
    need(track['track_id'] == review.get('track_id'), 'review_work_conflict')
    need(review.get('identity_revision') == track['identity_revision'], 'identity_revision_conflict')
    # No fuzzy title matching, remote title resolution, or inferred season.
    names = [track['title'], *track.get('aliases', [])]
    need(args.title.casefold().strip() in {x.casefold().strip() for x in names}, 'review_work_conflict')
    if args.season:
        need(args.season.upper() == track.get('season'), 'explicit_season_conflict')
    need(not (args.whole_season or args.include_specials or args.mark_finished or args.official_air_date),
         'review_requires_regular_episode')
    need(not (args.source_numbering or args.target_numbering or args.identity_evidence),
         'review_does_not_mutate_provider_bindings')
    if args.completion_evidence:
        from completion import read_evidence
        try:
            track['completion'] = read_evidence(args.completion_evidence,
                SimpleNamespace(anilist_id=track.get('anilist_id'), bangumi_id=track.get('bangumi_id')),
                track.get('season'))
        except (ValueError, TypeError, KeyError) as exc:
            raise WorkflowError('review', 'invalid_completion_evidence', evidence=(str(exc),)) from exc
    need(not (args.no_state_update and args.enqueue_qbittorrent), 'read_only_prohibits_enqueue')
    need(not args.include_magnet or args.legal_ok, 'legal_confirmation_required')
    need(not args.enqueue_qbittorrent or args.include_magnet and args.legal_ok, 'delivery_flags_required')
    need(not (args.latest and args.episode is not None), 'conflicting_target_flags')
    intent = 'latest_regular' if args.latest else 'specific_episode' if args.episode is not None else 'next_tracked'
    # Completion is an independent reconciliation step.  A delivered finale
    # may be followed by official evidence on a later run; do not force a
    # second torrent submission merely to close the season.
    completion = track.get('completion') or {}
    if (completion.get('confirmed') is True and type(completion.get('final_episode')) is int
            and handled(track) >= completion['final_episode']
            and intent in {'latest_regular', 'next_tracked'}):
        return ('reconcile_completion', track), {
            'status': 'completed', 'target_episode': completion['final_episode'],
            'state_update': 'none', 'qbittorrent': {'status': 'not_attempted'},
            'progress': {'before_episode': handled(track), 'after_episode': handled(track),
                         'next_episode': None, 'advanced': False},
            'completion': completion,
        }
    need(review.get('intent') == intent, 'review_intent_conflict')
    episode = review.get('target_episode')
    need(type(episode) is int and episode > 0, 'invalid_target_episode')
    if args.episode is not None:
        need(episode == args.episode, 'review_episode_conflict')
    if intent == 'next_tracked':
        need(type(track.get('next_episode')) is int and episode == track['next_episode'], 'next_episode_unconfirmed')
    cid = nyaa_id_from_url(str(review.get('candidate_id', '')))
    need(bool(cid), 'invalid_candidate_id')
    if args.candidate_id:
        need(nyaa_id_from_url(args.candidate_id) == cid, 'review_candidate_conflict')
    if track.get('status') in {'completed', 'finished'} and intent != 'specific_episode':
        return None, {'status': 'completed', 'state_update': 'none' if args.no_state_update else 'unchanged',
                      'completion': track.get('completion', {}),
                      'progress': {'after_episode': handled(track), 'next_episode': track.get('next_episode')},
                      'qbittorrent': {'status': 'not_attempted'}}

    paths = review.get('listing_reports')
    need(isinstance(paths, list) and bool(paths), 'listing_evidence_required')
    listing_paths = [resolve_path(review_path.parent, p) for p in paths]
    listings = [load_report(p, 'nyaa_listing') for p in listing_paths]
    rows = {}
    pages = {}
    for report in listings:
        need(report.get('sort') == 'id' and report.get('order') == 'desc'
             and report.get('row_count') == len(report['rows']), 'invalid_listing_coverage')
        pages.setdefault(report['query'], set()).add(report['page'])
        for row in report['rows']:
            old = rows.get(row['nyaa_id'])
            need(old is None or old['title'] == row['title'], 'conflicting_listing_evidence')
            rows[row['nyaa_id']] = row
    need(all(values == set(range(1, max(values) + 1)) for values in pages.values()), 'listing_page_gap')
    # Only selection-changing alternatives/ambiguities need a structured note.
    # Complete page reading is an Agent responsibility, not one form per row.
    assessments = review.get('key_decisions', [])
    need(isinstance(assessments, list), 'invalid_key_decisions')
    decisions = {str(a.get('candidate_id')): a for a in assessments}
    need(len(decisions) == len(assessments) and set(decisions) <= set(rows), 'invalid_key_decisions')
    for assessment in assessments:
        verdict = assessment.get('verdict')
        need(verdict in {'match', 'exclude', 'unresolved'} and bool(assessment.get('reason', '').strip()),
             'incomplete_candidate_decision')
        if verdict == 'match':
            need(type(assessment.get('episode')) is int and assessment['episode'] > 0, 'invalid_candidate_episode')
        need(verdict != 'unresolved', 'latest_unresolved' if intent == 'latest_regular' else 'selection_unresolved')
        if intent == 'latest_regular':
            if verdict == 'match':
                need(assessment['episode'] <= episode, 'newer_episode_observed')
    need(cid in rows, 'selected_candidate_not_in_evidence')
    if cid in decisions:
        need(decisions[cid]['verdict'] == 'match' and decisions[cid]['episode'] == episode,
             'selected_candidate_decision_conflict')
    coverage = review.get('coverage', {})
    need(coverage.get('complete_for_target') is True and bool(coverage.get('reason', '').strip()), 'coverage_review_required')

    detail_path = resolve_path(review_path.parent, review.get('detail_report'))
    saved_detail = load_report(detail_path, 'nyaa_detail')
    need(saved_detail['release']['nyaa_id'] == cid, 'detail_candidate_conflict')
    # A new release can change latest. Recheck the same full chronological scope.
    if intent == 'latest_regular':
        for path, old in zip(listing_paths, listings):
            fresh = evidence.listing(old['query'], old['page'], client=client, timeout=args.timeout)
            if listing_identity(fresh) != listing_identity(old):
                fresh_path = path.with_name(path.stem + '.fresh.json')
                evidence.save(fresh_path, fresh)
                need(False, 'discovery_changed', detail=(str(fresh_path),))
    fresh = evidence.details(cid, client=client, timeout=args.timeout)
    need(saved_detail['content_sha256'] == evidence.digest(evidence.stable_detail(saved_detail)), 'saved_detail_corrupt')
    if fresh['content_sha256'] != saved_detail['content_sha256']:
        fresh_path = detail_path.with_name(detail_path.stem + '.fresh.json')
        evidence.save(fresh_path, fresh)
        need(False, 'candidate_details_changed', detail=(str(fresh_path),))
    need(fresh['release']['title'] == rows[cid]['title'], 'candidate_title_changed')
    selection = review.get('selection', {})
    need(selection.get('kind') == 'regular', 'review_requires_regular_episode')
    need(bool(selection.get('work_reason', '').strip()), 'work_review_required')
    material = '\n'.join([fresh['release']['title'], fresh['description'], *[f['name'] for f in fresh['files']]])
    require_quotes(selection.get('work_quotes'), material, 'work_evidence_required')
    numbering = selection.get('numbering', {})
    need(numbering.get('target_season') == track.get('season') and numbering.get('target_episode') == episode,
         'review_numbering_conflict')
    need(bool(numbering.get('reason', '').strip()), 'numbering_review_required')
    require_quotes([numbering.get('release_label')], material, 'release_numbering_evidence_required')
    require_quotes(numbering.get('evidence_quotes'), material, 'numbering_evidence_required')
    # The source season is not compared to a guessed local season. The review
    # explicitly explains the mapping while the locked local identity is unchanged.
    videos = [f for f in fresh['files'] if Path(f['name']).suffix.lower() in VIDEO]
    need(len(videos) == 1 and videos[0]['name'] == selection.get('video_file'), 'single_regular_file_unconfirmed')
    size_bytes = videos[0].get('size_bytes')
    need(type(size_bytes) is int and size_bytes > 0, 'video_size_unknown')
    lower, upper = BOUNDS[args.tier]
    if args.min_gib_per_episode is not None or args.max_gib_per_episode is not None:
        lower = args.min_gib_per_episode if args.min_gib_per_episode is not None else lower
        upper = args.max_gib_per_episode
    elif args.allow_upward_compatibility:
        upper = None
    need(math.isfinite(lower) and lower >= 1 and (upper is None or math.isfinite(upper) and upper >= lower),
         'invalid_size_bounds')
    gib = size_bytes / 1024 ** 3
    need(gib >= lower and (upper is None or gib <= upper), 'release_unqualified', 'quality', (gib, lower, upper))
    subtitle_quotes = selection.get('subtitle_quotes', [])
    if subtitle_quotes:
        require_quotes(subtitle_quotes, material, 'subtitle_evidence_required')
    if args.require_zh:
        require_quotes(subtitle_quotes, material, 'subtitle_evidence_required')
        # Candidate semantics were reviewed; this checks an actual language signal,
        # never MultiSub or the work's Chinese title by itself.
        from search_nyaa_releases import detect_chinese_in_detail
        need(detect_chinese_in_detail('\n'.join(subtitle_quotes))[0], 'subtitle_unqualified')
    info_hash = fresh['release'].get('info_hash')
    magnet = magnet_from_hash(info_hash, fresh['release']['title'])
    try:
        valid_hash = bool(magnet) and extract_btih(magnet) == info_hash.lower()
    except (ValueError, AttributeError, SubmissionError):
        valid_hash = False
    need(valid_hash, 'magnet_incomplete', 'verification')
    identity = WorkIdentity(track['track_id'], track['title'], track.get('season'), track.get('part'),
                            track['identity_revision'], tuple(track.get('aliases', [])), track.get('format'))
    target = TargetDecision(identity, intent, episode, 'agent_reviewed_full_pages', intent == 'latest_regular')
    release = VerifiedRelease(identity, target, cid, fresh['release']['title'], magnet,
                              info_hash.lower(), fresh['release']['url'], 'regular',
                              json.dumps({'review': review, 'fresh_detail_sha256': fresh['content_sha256']}, ensure_ascii=False))
    result = {'status': 'found', 'work_identity': asdict(identity), 'target_episode': episode,
              'selected': {'nyaa_id': cid, 'title': release.title, 'url': release.source_url,
                           'size': fresh['release']['size'], 'video_size_gib': round(gib, 4),
                           'seeders': fresh['release']['seeders'], 'subtitle_evidence': subtitle_quotes,
                           'magnet': magnet if args.include_magnet else None},
              'scope': [{'query': p['query'], 'page': p['page'], 'rows': p['row_count']} for p in listings],
              'raw_rows_available': len(rows), 'key_decisions_recorded': len(assessments),
              'state_update': 'none',
              'qbittorrent': {'status': 'not_attempted'},
              'progress': {'before_episode': track.get('watched_episode'), 'advanced': False}}
    if intent in {'latest_regular', 'next_tracked'} and episode <= handled(track):
        result['status'] = 'latest_already_handled'
        return None, result
    return (release, track), result


def run(args, *, client=None, submit=None):
    try:
        validated, result = audit(args, client=client)
        if validated and validated[0] == 'reconcile_completion':
            _, track = validated
            if not args.no_state_update:
                StateRepository(args.state).commit(StateCommand(
                    track['track_id'], 'completed',
                    expected_identity_revision=track['identity_revision'],
                    fields={'completion': track['completion']}))
                after = require_record(StateRepository(args.state).read(), track['track_id'])
                result['state_update'] = 'completed'
                result['progress'].update(after_episode=handled(after), next_episode=None)
                result['completion'] = after.get('completion', track['completion'])
        elif validated and not args.no_state_update and args.include_magnet:
            release, track = validated
            request = ReleaseRequest(title=args.title, season=release.identity.season,
                                     episode=release.target.episode, intent=release.target.intent,
                                     read_only=False, enqueue=args.enqueue_qbittorrent,
                                     require_zh=args.require_zh, want_zh=args.want_zh,
                                     candidate_id=release.candidate_id)
            options = {'executable': args.qbittorrent_exe, 'save_path': args.qbittorrent_save_path,
                       'backup_dir': args.qbittorrent_backup_dir or DEFAULT_BACKUP_DIR,
                       'profile_path': args.qbittorrent_profile}
            delivery, receipt = finalize(release, request, args.state, submit or submit_magnet,
                                         client_options=options, completion=track.get('completion'))
            result['qbittorrent'] = delivery
            if receipt and receipt.accepted:
                after = require_record(StateRepository(args.state).read(), track['track_id'])
                result['state_update'] = 'delivery_recorded'
                result['progress'].update(after_episode=after.get('watched_episode'),
                                          next_episode=after.get('next_episode'),
                                          advanced=handled(after) > handled(track))
                if after.get('status') == 'completed':
                    result.update(status='completed', state_update='completed', completion=after.get('completion', {}))
            elif delivery.get('reason') == 'latest_already_handled':
                result['status'] = 'latest_already_handled'
            else:
                result['status'] = 'available_enqueue_failed'
        from completion import automation_cleanup
        result['automation_cleanup'] = automation_cleanup(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 6 if result['status'] == 'available_enqueue_failed' else 0
    except SubmissionError as exc:
        report = dict(result)
        report.update(status=exc.code if exc.code.startswith('client_context_') else 'available_enqueue_failed',
                      qbittorrent=exc.as_report(), state_update='none')
        from completion import automation_cleanup
        report['automation_cleanup'] = automation_cleanup(report)
        print(json.dumps(report, ensure_ascii=False))
        return 6
    except NyaaClientError as exc:
        raise WorkflowError('evidence_fetch', getattr(exc, 'error_code', 'evidence_fetch_failed'),
                            getattr(exc, 'retryable', False), (str(exc),), 'inspect_transport_evidence') from exc
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise WorkflowError('review', 'invalid_review', evidence=(str(exc),)) from exc
