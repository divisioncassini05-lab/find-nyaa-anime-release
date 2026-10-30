"""Reviewed movie/season delivery without creating a regular tracking record."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re

from anime_release import raw_evidence as raw
from anime_release.reviewed import load_report, resolve_path, VIDEO
from anime_release.models import WorkflowError
from anime_release.storage import atomic_json, file_lock
from nyaa_client import NyaaClient, NyaaClientError, magnet_from_hash
from qbittorrent_submit import extract_btih
from quality_review import (need, policy_from_args, validate_policy, validate_comparison,
                           validate_requirements, draft_comparison, quotes_valid, bounds, recovery_policy)
from submission_gate import _issue, digest
from runtime_paths import DEFAULT_STATE
from watch_v3.clients import DeliveryRequest, DeliveryReceipt, AcceptanceEvidence, ClientFailure, receipt


def source_exception(detail):
    """Source labels alone never waive an episode floor."""
    names = [f['name'].replace('\\', '/').lower() for f in detail['files']]
    if (any('/bdmv/playlist/' in '/' + n and n.endswith('.mpls') for n in names)
            and any('/bdmv/stream/' in '/' + n and n.endswith('.m2ts') for n in names)):
        return 'bdmv'
    description = detail['description']
    if (re.search(r'\bremux\b', description, re.I)
            and re.search(r'(?:no|without)\s+re[- ]?encod|untouched\s+video|video[^\n]{0,30}(?:stream\s+copy|not\s+re[- ]?encoded)|视频未重编码|未重新编码', description, re.I)
            and not re.search(r'video\s+(?:was\s+)?re[- ]?encoded|不是\s*remux', description, re.I)):
        return 'remux'
    return None


def make_draft(args):
    scope = json.loads(args.scope.read_text(encoding='utf-8-sig'))
    detail = load_report(args.detail, 'nyaa_detail')
    return dict(schema_version=1, kind='package_review', reviewed=False, scope=scope,
                candidate_id=detail['release']['nyaa_id'], detail_report=str(args.detail.resolve()),
                listing_reports=[str(p.resolve()) for p in args.listing],
                quality_policy=policy_from_args(args), quality_comparison=draft_comparison(),
                selection=dict(work_reason='', work_quotes=[], subtitle_quotes=[],
                               episodes=[], excluded_videos=[], source_exception=None))


def audit(path, policy, *, client=None):
    client = client or NyaaClient()
    path = Path(path)
    review = json.loads(path.read_text(encoding='utf-8-sig'))
    need(review.get('kind') == 'package_review' and review.get('schema_version') == 1
         and review.get('reviewed') is True, 'agent_review_required')
    validate_policy(review, policy)
    scope = review.get('scope', {})
    need(scope.get('kind') in {'season', 'movie'} and bool(scope.get('title'))
         and scope.get('reviewed') is True and bool(scope.get('source_url'))
         and bool(scope.get('evidence_text')), 'package_scope_evidence_required')
    count = scope.get('episodes') if scope['kind'] == 'season' else 1
    need(type(count) is int and count > 0, 'expected_episode_count_required')
    cid = str(review.get('candidate_id', ''))
    reports = review.get('listing_reports')
    need(isinstance(reports, list) and bool(reports), 'listing_evidence_required')
    listings = [load_report(resolve_path(path.parent, p), 'nyaa_listing') for p in reports]
    rows = {}
    pages = {}
    for listing in listings:
        need(listing.get('sort') == 'id' and listing.get('order') == 'desc'
             and listing.get('row_count') == len(listing['rows']), 'invalid_listing_coverage')
        pages.setdefault(listing['query'], set()).add(listing['page'])
        for row in listing['rows']:
            previous = rows.get(str(row['nyaa_id']))
            need(previous is None or previous['title'] == row['title'], 'conflicting_listing_evidence')
            rows[str(row['nyaa_id'])] = row
    need(all(values == set(range(1, max(values) + 1)) for values in pages.values()), 'listing_page_gap')
    need(cid in rows, 'selected_candidate_not_in_evidence')
    old = load_report(resolve_path(path.parent, review.get('detail_report')), 'nyaa_detail')
    need(old['release']['nyaa_id'] == cid and raw.digest(raw.stable_detail(old)) == old['content_sha256'],
         'saved_detail_corrupt')
    detail = raw.details(cid, client=client)
    need(detail['content_sha256'] == old['content_sha256'], 'candidate_details_changed')
    need(detail['release']['title'] == rows[cid]['title'], 'candidate_title_changed')
    selection = review.get('selection', {})
    need(bool(selection.get('work_reason')) and quotes_valid(selection.get('work_quotes'), detail),
         'work_evidence_required')
    validate_requirements(review, detail, policy)
    comparison = validate_comparison(review, detail, path.parent, client=client)
    videos = {f['name']: f for f in detail['files'] if Path(f['name']).suffix.lower() in VIDEO}
    need(bool(videos), 'video_file_list_required')
    need(len(videos) == sum(Path(f['name']).suffix.lower() in VIDEO for f in detail['files']), 'duplicate_video_path')
    entries = selection.get('episodes', [])
    need(isinstance(entries, list) and len(entries) == count, 'incomplete_episode_coverage')
    need({e.get('episode') for e in entries} == set(range(1, count + 1)), 'incomplete_episode_coverage')
    included = []
    sizes = []
    for entry in entries:
        names = entry.get('files', [])
        need(isinstance(names, list) and bool(names) and bool(entry.get('reason'))
             and quotes_valid(entry.get('quotes'), detail), 'episode_mapping_required')
        need(all(n in videos for n in names), 'episode_file_not_found')
        need(all(type(videos[n].get('size_bytes')) is int and videos[n]['size_bytes'] > 0 for n in names),
             'video_size_unknown')
        included.extend(names)
        sizes.append(sum(videos[n]['size_bytes'] for n in names) / 1024 ** 3)
    need(len(included) == len(set(included)), 'duplicate_episode_file')
    exclusions = selection.get('excluded_videos', [])
    need(isinstance(exclusions, list), 'unclassified_video_files')
    excluded = [e.get('file') for e in exclusions]
    need(len(excluded) == len(set(excluded)) and not set(excluded) & set(included)
         and set(excluded) | set(included) == set(videos), 'unclassified_video_files')
    need(all(bool(e.get('reason')) and quotes_valid(e.get('quotes'), detail) for e in exclusions),
         'excluded_file_evidence_required')
    exemption = selection.get('source_exception')
    exempt = False
    if exemption:
        need(policy['tier'] == 'premium' and policy['min_gib'] is None and policy['max_gib'] is None,
             'source_exception_not_applicable')
        need(isinstance(exemption, dict) and exemption.get('type') == source_exception(detail)
             and bool(exemption.get('type')) and bool(exemption.get('reason'))
             and quotes_valid(exemption.get('quotes'), detail), 'source_exception_unverified')
        exempt = True
    # Multiple streams per episode are valid for verified disc layouts, not a way
    # to add alternate small encodes until their sum reaches the size floor.
    if any(len(e['files']) != 1 for e in entries):
        need(exempt and exemption['type'] == 'bdmv', 'multiple_encodes_per_episode')
    lower, upper = bounds(policy)
    if scope['kind'] == 'movie':
        lower = policy['min_total_gib'] if policy['min_total_gib'] is not None else 10.0
        upper = policy['max_total_gib']
        need(sum(sizes) >= lower and (upper is None or sum(sizes) <= upper), 'release_unqualified')
    elif not exempt:
        # Every regular episode must pass; a larger file cannot mask a smaller one.
        need(all(v >= 1 for v in sizes), 'per_episode_below_absolute_floor')
        need(all(v >= lower and (upper is None or v <= upper) for v in sizes), 'release_unqualified')
    info_hash = detail['release'].get('info_hash', '').lower()
    magnet = magnet_from_hash(info_hash, detail['release']['title'])
    need(bool(magnet) and extract_btih(magnet) == info_hash, 'magnet_incomplete')
    permit = _issue(info_hash, cid, detail['release']['url'], policy, digest(review), detail['content_sha256'])
    report = dict(status='found', eligibility='passed', candidate_id=cid, info_hash=info_hash,
                  source_url=detail['release']['url'], magnet=magnet, scope=scope,
                  quality_policy=policy, quality_comparison=comparison,
                  coverage=dict(complete=True, quality_fit=True, episodes=count, sizes_gib=sizes,
                                source_exception=exemption if exempt else None), state_update='none')
    return permit, report, review


def durable_review(path, review, directory):
    """Keep pending package evidence outside the expiring discovery cache."""
    review = json.loads(json.dumps(review))
    def keep(value):
        source = resolve_path(Path(path).parent, value)
        data = json.loads(source.read_text(encoding='utf-8-sig'))
        target = directory / (digest(data) + '.json')
        atomic_json(target, data)
        return str(target.resolve())
    review['detail_report'] = keep(review['detail_report'])
    review['listing_reports'] = [keep(p) for p in review['listing_reports']]
    for alternative in review['quality_comparison']['alternatives']:
        alternative['detail_report'] = keep(alternative['detail_report'])
    target = directory / ('review-' + digest(review) + '.json')
    atomic_json(target, review)
    return target, digest(review)


def _execute(request, op, journal, client):
    request.authorize()
    try:
        accepted = client.submit(request).validate(request)
    except ClientFailure as exc:
        atomic_json(journal, {**op, 'status': 'failed', 'failure': asdict(exc.recovery)})
        return dict(status='available_enqueue_failed', operation_id=op['operation_id'], recovery=asdict(exc.recovery))
    saved = {**op, 'status': 'accepted', 'receipt': asdict(accepted)}
    try:
        atomic_json(journal, saved)
    except OSError:
        return dict(status='accepted_receipt_commit_failed', operation_id=op['operation_id'], receipt=asdict(accepted))
    return dict(status='delivery_recorded', operation_id=op['operation_id'], receipt=asdict(accepted), state_update='none')


def deliver(path, policy, journal_root, client, *, evidence_client=None, save_path=None):
    permit, report, review = audit(path, policy, client=evidence_client)
    opid = digest({'kind': 'package', 'scope': review['scope'], 'hash': report['info_hash']})[:24]
    directory = Path(journal_root) / opid
    journal = directory / 'operation.json'
    with file_lock(directory / '.lock'):
        if journal.exists():
            # Never overwrite a prepared operation or its original constraints.
            return recover(journal, client, evidence_client=evidence_client)
        saved_review, review_digest = durable_review(path, review, directory)
        request = DeliveryRequest('package:' + opid, opid, report['info_hash'], report['magnet'],
                                  save_path=str(save_path) if save_path else None,
                                  source_url=report['source_url'], validation=permit)
        op = dict(operation_id=opid, status='prepared', request=request.saved_request(),
                  quality_policy=policy, review_path=str(saved_review), review_digest=review_digest)
        atomic_json(journal, op)
        return {**_execute(request, op, journal, client), 'report': report}


def recover(journal, client, *, evidence_client=None, review_path=None, original_policy=None):
    journal = Path(journal)
    with file_lock(journal.parent / '.lock'):
        op = json.loads(journal.read_text(encoding='utf-8-sig'))
        request = DeliveryRequest(**op['request'])
        request.validate()
        need(request.operation_id == op['operation_id'], 'operation_request_conflict')
        if op.get('receipt', {}).get('accepted') is True:
            accepted = op['receipt']
            DeliveryReceipt(**{**accepted, 'evidence': AcceptanceEvidence(**accepted['evidence'])}).validate(request)
            return dict(status='already_accepted', operation_id=op['operation_id'], receipt=accepted, state_update='none')
        observed = client.inspect(request.info_hash)
        need(observed.info_hash == request.info_hash, 'inspection_hash_mismatch')
        if observed.verified:
            accepted = asdict(receipt(request, 'already_present', observed))
            atomic_json(journal, {**op, 'status': 'accepted', 'receipt': accepted})
            return dict(status='recovered', operation_id=op['operation_id'], receipt=accepted, state_update='none')
        need(review_path is not None or bool(op.get('review_path')), 're_review_required')
        policy = recovery_policy(op.get('quality_policy'), original_policy)
        path = Path(review_path or op['review_path'])
        review = json.loads(path.read_text(encoding='utf-8-sig'))
        if review_path is None:
            need(digest(review) == op['review_digest'], 'recovery_review_changed')
        else:
            previous = json.loads(Path(op['review_path']).read_text(encoding='utf-8-sig'))
            need(review.get('scope') == previous.get('scope') and
                 review.get('candidate_id') == previous.get('candidate_id'), 'recovery_scope_changed')
        permit, report, _ = audit(path, policy, client=evidence_client)
        need(report['info_hash'] == request.info_hash, 'recovery_validation_failed')
        if review_path is not None:
            saved_path, review_digest = durable_review(path, review, journal.parent)
            op.update(quality_policy=policy, review_path=str(saved_path), review_digest=review_digest)
            atomic_json(journal, op)
        from dataclasses import replace
        return _execute(replace(request, validation=permit), op, journal, client)


def main(argv=None):
    from watch_v3.cli import quality_args, client_args, client
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    draft = sub.add_parser('draft')
    draft.add_argument('--scope', type=Path, required=True)
    draft.add_argument('--listing', type=Path, action='append', required=True)
    draft.add_argument('--detail', type=Path, required=True)
    draft.add_argument('--output', type=Path, required=True)
    quality_args(draft)
    for name in ('audit', 'deliver'):
        p = sub.add_parser(name)
        p.add_argument('--review', type=Path, required=True)
        quality_args(p)
        if name == 'deliver':
            client_args(p)
            p.add_argument('--legal-ok', action='store_true', required=True)
            p.add_argument('--enqueue-qbittorrent', action='store_true', required=True)
            p.add_argument('--journal-root', type=Path, default=DEFAULT_STATE.parent / '.package-deliveries')
    p = sub.add_parser('recover')
    p.add_argument('--journal', type=Path, required=True)
    p.add_argument('--review', type=Path)
    p.add_argument('--original-policy', type=Path)
    client_args(p)
    args = parser.parse_args(argv)
    try:
        if args.command == 'draft':
            report = make_draft(args)
            raw.save(args.output, report)
            report = dict(status='draft', output=str(args.output), reviewed=False)
        elif args.command == 'audit':
            _, report, _ = audit(args.review, policy_from_args(args))
            report.pop('magnet', None)
        elif args.command == 'deliver':
            report = deliver(args.review, policy_from_args(args), args.journal_root, client(args),
                             save_path=args.qbittorrent_save_path)
        else:
            need(args.original_policy is None or args.review is not None, 're_review_required')
            report = recover(args.journal, client(args), review_path=args.review,
                             original_policy=json.loads(args.original_policy.read_text(encoding='utf-8-sig')) if args.original_policy else None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['status'] in {'draft', 'found', 'delivery_recorded', 'already_accepted', 'recovered'} else 3
    except (WorkflowError, ClientFailure, NyaaClientError, OSError, ValueError, KeyError, TypeError) as exc:
        report = dict(status='validation_failed', error=str(exc), delivery_status='not_confirmed_by_this_result')
        if isinstance(exc, WorkflowError):
            report.update(exc.as_dict())
        print(json.dumps(report, ensure_ascii=False))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
