#!/usr/bin/env python3
"""Mechanical search orchestration; the caller supplies every semantic decision.

Raw listings/details remain intact on disk. Presentation removes redundant fields,
never candidates, titles, description text or file entries.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

from anime_release import raw_evidence as raw
from anime_release.models import WorkflowError
from anime_release.reviewed import VIDEO
from anime_release.storage import atomic_json
from evidence_artifacts import new_workspace, register, root, cleanup
from quality_review import bounds, policy_from_args, validate_policy
from runtime_paths import DEFAULT_STATE
from watch_v3.evidence import DiscoveryService, QualityPolicy, ReviewManifest, ReviewValidator
from watch_v3.store import StateRepository


def need(ok, code):
    if not ok:
        raise ValueError(code)


def save(path, value, state):
    atomic_json(path, value)
    register(path, state)
    return path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def date_text(row):
    stamp = row.get('published_at')
    return (datetime.fromtimestamp(stamp, timezone.utc).astimezone().isoformat(timespec='minutes')
            if stamp is not None else row.get('published'))


def table(report, policy=None, scope=None):
    """One intact title per source row; ID reconstructs URL, date includes offset."""
    lower, upper = bounds(policy) if policy else (1, 2)
    count = (scope or {}).get('episodes', 1)
    count = count if type(count) is int and count > 0 else 1
    if (scope or {}).get('kind') == 'movie':
        count, lower, upper = 1, (policy or {}).get('min_total_gib') or 10, (policy or {}).get('max_total_gib')
    def hint(row):
        size = row.get('size_bytes')
        if type(size) is not int:
            return 'unknown'
        gib = size / 1024 ** 3
        return 'below_estimate' if gib < count * lower else 'above_estimate' if upper is not None and gib > count * upper else 'within_estimate'
    return {'query': report['query'], 'page': report['page'], 'rows': report['row_count'],
            'later_pages': report['later_pages'],
            'size_hint_basis': {'episodes': count, 'per_episode_min_gib': lower, 'per_episode_max_gib': upper,
                                'use': 'coarse_inspection_only_never_qualification_or_title_classification'},
            'columns': ['id', 'title', 'size', 'published', 'seeders', 'leechers', 'downloads', 'total_size_hint'],
            'values': [[r['nyaa_id'], r['title'], r['size'], date_text(r),
                        r['seeders'], r['leechers'], r['downloads'], hint(r)] for r in report['rows']]}


def identity_context(show):
    return {key: show[key] for key in ('track_id', 'identity_revision', 'identity',
                                     'broadcast', 'progress', 'lifecycle')}


def checked_show(repo, track_id):
    show = repo.find(track_id=track_id)
    need(show is not None, 'identity_required')
    need(show['lifecycle']['phase'] != 'blocked', 'identity_blocked')
    pending = [op['operation_id'] for op in show.get('operations', {}).values() if not op.get('committed')]
    need(not pending, 'recover_pending_operation_first')
    return show


def load_session(state, run, binding=None):
    need(not Path(run).is_symlink(), 'owned_run_required')
    run = Path(run).resolve()
    need(run.is_relative_to(root(state).resolve()) and run != root(state).resolve(), 'owned_run_required')
    need(not Path(run).is_symlink(), 'owned_run_required')
    need(read(run / '.run.json').get('state') == str(Path(state).resolve()), 'run_state_mismatch')
    session = read(run / 'session.json')
    need(session.get('kind') == 'semantic-search-session' and session.get('binding') == binding,
         'search_binding_changed')
    need(all(re.fullmatch(r'listing-[1-9][0-9]*\.json', name) for name in session['listings'])
         and all(re.fullmatch(r'[0-9]+', cid) and name == f'detail-{cid}.json'
                 for cid, name in session['details'].items()), 'invalid_session_evidence_paths')
    need(all(not (run / name).is_symlink() for name in session['listings'] + list(session['details'].values())),
         'invalid_session_evidence_paths')
    validate_policy({'quality_policy': session['policy']}, session['policy'])
    if session.get('track_id'):
        show = checked_show(StateRepository(state), session['track_id'])
        need(show['identity_revision'] == session['identity_revision'], 'identity_revision_conflict')
    return run, session


def start(state, *, track_id=None, title=None, query=None, pages=2, intent='next_tracked',
          episode=None, policy=None, binding=None, scope=None, client=None):
    policy = policy or policy_from_args(argparse.Namespace())
    validate_policy({'quality_policy': policy}, policy)
    repo = StateRepository(state)
    show = repo.find(track_id=track_id) if track_id else repo.find(title=title) if title else None
    package = intent in {'season', 'movie'}
    if not package and show is None:
        return {'status': 'identity_required', 'track_id': track_id, 'title': title,
                'next': 'Verify work/season/aliases, then create the authorized track using airing-watch-state.md.'}
    if show and not package:
        show = checked_show(repo, show['track_id'])
    context = {'identity': identity_context(show) if show and not package else scope,
               'intent': intent, 'quality_policy': policy, 'size_bounds_gib': bounds(policy)}
    if not query:
        return {'status': 'query_required', 'read_only': True, **context,
                'write_directory': str(Path(state).resolve().parent),
                'next': 'Choose distinctive verified work aliases (usually the romanized release name); batch them as repeated --query arguments. Interpret season markers from titles, not fragile query suffixes. Query stages write evidence: use host-approved access to write_directory.'}
    need(intent != 'specific_episode' or type(episode) is int and episode > 0, 'target_episode_required')
    need(not package or isinstance(scope, dict) and scope.get('kind') == intent, 'package_scope_required')
    run = new_workspace(state)
    session = {'kind': 'semantic-search-session', 'binding': binding, 'policy': policy,
               'track_id': show['track_id'] if show and not package else None,
               'identity_revision': show['identity_revision'] if show and not package else None,
               'intent': intent, 'episode': episode, 'scope': scope,
               'listings': [], 'details': {}, 'errors': []}
    save(run / 'session.json', session, state)
    return {**collect(state, run, query=query, pages=pages, binding=binding, client=client), **context}


def collect(state, run, *, query, pages=2, binding=None, client=None):
    run, session = load_session(state, run, binding)
    need(type(pages) is int and 1 <= pages <= 20, 'invalid_page_count')
    queries = [query] if isinstance(query, str) else query
    need(isinstance(queries, list) and queries and all(isinstance(q, str) and q.strip() for q in queries), 'queries_required')
    queries = list(dict.fromkeys(q.strip() for q in queries))
    existing = [raw.read(run / name, 'nyaa_listing') for name in session['listings']]
    reports = []
    for query in queries:
        first = max((p['page'] for p in existing if p['query'] == query), default=0) + 1
        for page in range(first, first + pages):
            key = {'query': query, 'page': page}
            try:
                report = raw.listing(query, page, client=client)
            except Exception as error:
                session['errors'] = [e for e in session['errors'] if e.get('request') != key]
                session['errors'].append({'request': key, 'error': type(error).__name__})
                break
            name = f'listing-{len(session["listings"]) + 1}.json'
            save(run / name, report, state)
            session['listings'].append(name)
            session['errors'] = [e for e in session['errors'] if e.get('request') != key]
            reports.append(table(report, session['policy'], session.get('scope')))
            if page + 1 not in report['later_pages']:
                break
    save(run / 'session.json', session, state)
    return {'status': 'search_incomplete' if session['errors'] else 'listings_ready',
            'run': str(run), 'listings': reports, 'errors': session['errors'],
            'next': 'Read every title. Request details for plausible candidates together; collect more pages/verified aliases if coverage is unresolved.'}


def evidence_refs(report):
    """Candidate-local exact text; references cannot borrow another release's evidence."""
    return {'title': report['release']['title'],
            **{f'd{i}': text for i, text in enumerate(report['description'].split('\n\n'), 1)},
            **{f'f{i}': entry['name'] for i, entry in enumerate(report['files'], 1)}}


def expand_refs(value, report):
    """The Agent chooses evidence; scripts copy it without paraphrasing or guessing."""
    sources = evidence_refs(report)
    keys = {'refs': 'quotes', 'work_refs': 'work_quotes', 'evidence_refs': 'evidence_quotes',
            'subtitle_refs': 'subtitle_quotes', 'selected_refs': 'selected_quotes'}
    if isinstance(value, list):
        return [expand_refs(item, report) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: expand_refs(item, report) for key, item in value.items() if key not in keys}
    for key, dest in keys.items():
        if key not in value:
            continue
        refs = value[key]
        need(isinstance(refs, list) and all(isinstance(ref, str) and ref in sources for ref in refs),
             'evidence_ref_not_in_candidate')
        quotes = result.get(dest, [])
        need(isinstance(quotes, list), 'evidence_quotes_required')
        result[dest] = list(dict.fromkeys([*quotes, *(sources[ref] for ref in refs)]))
    return result


def detail_view(report, policy):
    release = report['release']
    lower, upper = bounds(policy)
    files = []
    for i, entry in enumerate(report['files'], 1):
        size = entry.get('size_bytes')
        gib = size / 1024 ** 3 if type(size) is int else None
        hint = 'unknown' if gib is None else 'below' if gib < lower else 'above' if upper is not None and gib > upper else 'within'
        files.append([entry['name'], entry['size'], round(gib, 6) if gib is not None else None, hint, f'f{i}'])
    return {'id': release['nyaa_id'], 'title': release['title'], 'size': release['size'],
            'published': date_text(release), 'seeders': release['seeders'],
            'leechers': release['leechers'], 'downloads': release['downloads'],
            'title_ref': 'title', 'description_columns': ['ref', 'text'],
            'description': [[ref, text] for ref, text in evidence_refs(report).items() if ref.startswith('d')],
            'file_columns': ['name', 'size', 'gib', 'regular_size_hint', 'ref'],
            'files': files}


def details(state, run, ids, *, binding=None, client=None):
    run, session = load_session(state, run, binding)
    ids = list(dict.fromkeys(str(cid) for cid in ids))
    rows = {r['nyaa_id'] for name in session['listings'] for r in raw.read(run / name, 'nyaa_listing')['rows']}
    need(ids and all(cid in rows for cid in ids), 'candidate_not_in_listing')
    reports = []
    for cid in ids:
        key = {'candidate_id': cid}
        try:
            report = raw.details(cid, client=client)
        except Exception as error:
            session['errors'] = [e for e in session['errors'] if e.get('request') != key]
            session['errors'].append({'request': key, 'error': type(error).__name__})
            continue
        name = f'detail-{cid}.json'
        save(run / name, report, state)
        session['details'][cid] = name
        session['errors'] = [e for e in session['errors'] if e.get('request') != key]
        reports.append(detail_view(report, session['policy']))
    save(run / 'session.json', session, state)
    return {'status': 'search_incomplete' if session['errors'] else 'details_ready',
            'run': str(run), 'candidates': reports, 'errors': session['errors'],
            'next': 'Submit semantic decision via stdin; use candidate-local title/dN/fN evidence refs to avoid copying quotes. Unknown subtitle languages stay unknown; size hints do not classify files or prove quality.'}


def make_review(state, run, session, decision):
    need(isinstance(decision, dict), 'semantic_decision_required')
    cid = str(decision.get('candidate_id', ''))
    need(cid in session['details'], 'candidate_details_required')
    detail_path = run / session['details'][cid]
    detail = raw.read(detail_path, 'nyaa_detail')
    listings = [run / name for name in session['listings']]
    selection = expand_refs(copy.deepcopy(decision.get('selection', {})), detail)
    need(isinstance(selection, dict), 'semantic_selection_required')
    if session['track_id']:
        show = checked_show(StateRepository(state), session['track_id'])
        episode = decision.get('episode')
        need(type(episode) is int and episode > 0, 'target_episode_required')
        need(session['episode'] is None or episode == session['episode'], 'target_episode_conflict')
        review = DiscoveryService().draft(show, listings, detail_path, session['intent'], episode, session['policy'])
        need(selection.get('kind') == 'regular', 'regular_episode_decision_required')
        numbering = selection.get('numbering', {})
        need(isinstance(numbering, dict), 'numbering_review_required')
        numbering.update(target_episode=episode, target_season=show['identity'].get('season'))
        selection['numbering'] = numbering
        videos = [entry for entry in detail['files'] if Path(entry['name']).suffix.lower() in VIDEO]
        need(len(videos) == 1, 'single_regular_file_unconfirmed')
        # The Agent classifies this release as one regular episode. Its sole file
        # path is mechanical; the validator still checks its exact current size.
        selection['video_file'] = videos[0]['name']
        review['coverage'] = copy.deepcopy(decision.get('coverage', {}))
        review['key_decisions'] = copy.deepcopy(decision.get('key_decisions', []))
    else:
        review = {'schema_version': 1, 'kind': 'package_review', 'candidate_id': cid,
                  'scope': copy.deepcopy(session['scope']), 'quality_policy': session['policy'],
                  'listing_reports': [str(p) for p in listings], 'detail_report': str(detail_path)}
    comparison = copy.deepcopy(decision.get('quality_comparison', {}))
    need(isinstance(comparison, dict), 'quality_comparison_required')
    alternatives = comparison.pop('alternatives', [])
    comparison = expand_refs(comparison, detail)
    comparison['alternatives'] = []
    for alternative in alternatives:
        alt_id = str(alternative.pop('candidate_id', ''))
        need(alt_id in session['details'], 'comparison_details_required')
        alternative = expand_refs(alternative, raw.read(run / session['details'][alt_id], 'nyaa_detail'))
        alternative['detail_report'] = str(run / session['details'][alt_id])
        comparison['alternatives'].append(alternative)
    review.update(selection=selection, quality_comparison=comparison, reviewed=True)
    return review


def final_receipt(result, scopes, session):
    """Objective answer facts come from recorded requests and the validation result."""
    report = result.get('report', result)
    counts = {}
    for page in scopes:
        count = counts.setdefault(page['query'], {'pages': 0, 'rows': 0})
        count['pages'] += 1
        count['rows'] += page['rows']
    facts = {'queries': [{'query': q, **n} for q, n in counts.items()],
             'listing_rows': sum(p['rows'] for p in scopes), 'candidate_details': len(session['details'])}
    lines = [f"本次获取 {facts['listing_rows']} 条完整列表记录，检查 {facts['candidate_details']} 份候选详情。",
             '实际查询：' + '；'.join(f"{json.dumps(q, ensure_ascii=False)}：{n['pages']} 页、{n['rows']} 条" for q, n in counts.items()) + '。']
    if report.get('eligibility') == 'passed':
        title = (report.get('work_identity') or session.get('scope') or {}).get('title')
        episode = report.get('target_episode')
        lines.append(f"审核通过：{title or '目标作品'}" + (f"，第 {episode} 集。" if type(episode) is int else '。'))
        selected = report.get('selected') or {}
        url = selected.get('url') or report.get('source_url')
        if url:
            lines.append(f"资源：{url}")
        if selected.get('title'):
            lines.append('标题：' + selected['title'])
        if selected.get('size'):
            lines.append('大小：' + str(selected['size']))
        if selected.get('seeders') is not None:
            lines.append('做种数：' + str(selected['seeders']))
        if selected and not selected.get('subtitle_evidence'):
            lines.append('本次审核未核实具体字幕语言。')
    qb = report.get('qbittorrent') or {}
    if qb.get('status') == 'not_attempted':
        lines.append('本次未提交下载。')
    if (report.get('progress') or {}).get('advanced') is False:
        lines.append('观看进度未推进。')
    result['search_facts'] = facts
    result['answer'] = '\n\n'.join(lines)
    return result


def finish(state, run, decision, *, binding=None, client=None, enqueue=False, delivery_args=None, keep_run=False):
    run, session = load_session(state, run, binding)
    need(not session['errors'], 'incomplete_search_evidence')
    if isinstance(decision, list):
        need(decision and not enqueue, 'choices_require_link_only')
        results = [finish(state, run, item, binding=binding, client=client, keep_run=True) for item in decision]
        return {'status': 'choices_ready', 'choices': results, 'cleanup': cleanup(StateRepository(state), run=run)}
    review = make_review(state, run, session, decision)
    path = save(run / 'review.json', review, state)
    scopes = [{'query': page['query'], 'page': page['page'], 'rows': page['row_count']}
              for name in session['listings'] for page in [raw.read(run / name, 'nyaa_listing')]]
    if session['track_id']:
        show = checked_show(StateRepository(state), session['track_id'])
        policy = QualityPolicy(**session['policy'])
        if enqueue:
            from watch_v3.cli import client as delivery_client
            from watch_v3.workflow import Workflow, Request, render_report
            repo = StateRepository(state)
            result = render_report(repo, Workflow(repo, delivery_client(delivery_args), validator=ReviewValidator(client)).deliver(
                Request(show['identity']['title'], path, policy,
                        str(delivery_args.qbittorrent_save_path) if delivery_args.qbittorrent_save_path else None)))
        else:
            result = ReviewValidator(client).validate(ReviewManifest.load(path), show, policy).report
    else:
        import package_release
        if enqueue:
            from watch_v3.cli import client as delivery_client
            result = package_release.deliver(path, session['policy'], Path(state).parent / '.package-deliveries',
                delivery_client(delivery_args), evidence_client=client,
                save_path=str(delivery_args.qbittorrent_save_path) if delivery_args.qbittorrent_save_path else None)
        else:
            _, result, _ = package_release.audit(path, session['policy'], client=client)
    final_receipt(result, scopes, session)
    # Keep the audit result intact; append the factual receipt and owned cleanup.
    if not keep_run and (result.get('eligibility') == 'passed' or result.get('status') in {'delivery_recorded', 'already_accepted', 'recovered'}):
        try:
            result['cleanup'] = cleanup(StateRepository(state), run=run) if run.exists() else {'status': 'already_cleaned'}
        except (ValueError, OSError):
            result['cleanup'] = {'status': 'cleanup_pending'}
    return result


def close(state, run, status, reason, *, binding=None):
    run, session = load_session(state, run, binding)
    need(bool(reason.strip()), 'outcome_reason_required')
    if session['errors']:
        return {'status': 'search_incomplete', 'errors': session['errors'], 'run': str(run)}
    return {'status': status, 'reason': reason, 'decision_source': 'agent_semantic_review',
            'cleanup': cleanup(StateRepository(state), run=run), 'state_update': 'none'}


def parser():
    from watch_v3.cli import quality_args, client_args
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, default=DEFAULT_STATE)
    sub = p.add_subparsers(dest='command', required=True)
    start_parser = sub.add_parser('start')
    start_parser.add_argument('--track-id'); start_parser.add_argument('--title')
    start_parser.add_argument('--query', action='append'); start_parser.add_argument('--pages', type=int, default=2)
    start_parser.add_argument('--intent', choices=['latest_regular', 'specific_episode', 'next_tracked', 'season', 'movie'], default='next_tracked')
    start_parser.add_argument('--episode', type=int)
    scope_group = start_parser.add_mutually_exclusive_group()
    scope_group.add_argument('--scope', type=Path)
    scope_group.add_argument('--scope-stdin', action='store_true')
    quality_args(start_parser)
    c = sub.add_parser('collect'); c.add_argument('--run', type=Path, required=True)
    c.add_argument('--query', required=True, action='append'); c.add_argument('--pages', type=int, default=2)
    d = sub.add_parser('details'); d.add_argument('--run', type=Path, required=True)
    d.add_argument('--ids', nargs='+', required=True)
    f = sub.add_parser('finish'); f.add_argument('--run', type=Path, required=True)
    f.add_argument('--enqueue-qbittorrent', action='store_true')
    f.add_argument('--legal-ok', action='store_true')
    client_args(f)
    c = sub.add_parser('close'); c.add_argument('--run', type=Path, required=True)
    c.add_argument('--status', choices=['no_nyaa_release_for_target', 'release_unqualified', 'subtitle_unqualified', 'latest_unresolved'], required=True)
    c.add_argument('--reason', required=True)
    return p


def execute(args, *, binding=None, client=None):
    if args.command == 'start':
        return start(args.state, track_id=args.track_id, title=args.title, query=args.query,
                     pages=args.pages, intent=args.intent, episode=args.episode, policy=policy_from_args(args),
                     scope=json.load(sys.stdin) if args.scope_stdin else read(args.scope) if args.scope else None,
                     binding=binding, client=client)
    if args.command == 'collect':
        return collect(args.state, args.run, query=args.query, pages=args.pages, binding=binding, client=client)
    if args.command == 'details':
        return details(args.state, args.run, args.ids, binding=binding, client=client)
    if args.command == 'close':
        return close(args.state, args.run, args.status, args.reason, binding=binding)
    need(not args.enqueue_qbittorrent or args.legal_ok, 'delivery_authorization_required')
    return finish(args.state, args.run, json.load(sys.stdin), binding=binding, client=client,
                  enqueue=args.enqueue_qbittorrent, delivery_args=args)


def run(argv=None, *, binding=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args, binding=binding)
    except WorkflowError as error:
        result = {'status': 'review_required', **error.as_dict()}
    except (OSError, ValueError) as error:
        code = str(error)
        result = {'status': 'search_failed', 'error': code if re.fullmatch(r'[a-z][a-z0-9_]{0,79}', code) else type(error).__name__}
        if isinstance(error, PermissionError):
            result.update(error='permission_denied', path=error.filename, next_action='use_host_approved_access_or_stop')
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 6 if result['status'] in {'search_failed', 'review_required', 'search_incomplete'} else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(run())
