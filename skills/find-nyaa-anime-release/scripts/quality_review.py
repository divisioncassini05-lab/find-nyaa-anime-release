"""Hard policy binding and detail-only semantic comparison evidence."""
import math

from anime_release.models import WorkflowError


BOUNDS = {'browse': (1.0, 2.0), 'watch': (2.0, 4.0), 'premium': (6.0, None)}
POLICY_FIELDS = {'tier', 'min_gib', 'max_gib', 'allow_upward', 'require_zh', 'want_zh',
                 'min_total_gib', 'max_total_gib', 'require_audio', 'require_source', 'prefer_groups'}


def need(ok, code):
    if not ok:
        raise WorkflowError('quality', code, False, (), 'review_detail_evidence')


def policy_from_args(args):
    get = lambda name, default=None: getattr(args, name, default)
    return dict(tier=get('tier', 'browse'), min_gib=get('min_gib_per_episode'),
                max_gib=get('max_gib_per_episode'), allow_upward=bool(get('allow_upward_compatibility', False)),
                require_zh=bool(get('require_zh', False)), want_zh=bool(get('want_zh', False)),
                min_total_gib=get('min_total_gib'), max_total_gib=get('max_total_gib'),
                require_audio=list(get('require_audio', []) or []),
                require_source=list(get('require_source', []) or []),
                prefer_groups=list(get('prefer_group', []) or []))


def validate_policy(review, policy):
    need(isinstance(policy, dict) and set(policy) == POLICY_FIELDS, 'original_quality_policy_required')
    need(review.get('quality_policy') == policy, 'quality_policy_mismatch')
    need(policy['tier'] in BOUNDS, 'invalid_quality_policy')
    need(all(type(policy[key]) is bool for key in ('allow_upward', 'require_zh', 'want_zh')),
         'invalid_quality_policy')
    need(all(isinstance(policy[key], (list, tuple)) and
             all(isinstance(v, str) and v.strip() for v in policy[key])
             for key in ('require_audio', 'require_source', 'prefer_groups')), 'invalid_quality_policy')
    for key in ('min_gib', 'max_gib', 'min_total_gib', 'max_total_gib'):
        value = policy[key]
        need(value is None or type(value) in (int, float) and math.isfinite(value) and value > 0,
             'invalid_size_bounds')
    lower, upper = bounds(policy)
    need(lower >= 1 and (upper is None or upper >= lower), 'invalid_size_bounds')
    lower = policy['min_total_gib'] if policy['min_total_gib'] is not None else 10
    need(policy['max_total_gib'] is None or policy['max_total_gib'] >= lower, 'invalid_size_bounds')


def recovery_policy(saved, supplied=None):
    """Never fill missing historic constraints with current CLI defaults."""
    from submission_gate import digest
    policy = supplied if supplied is not None else saved
    need(bool(policy), 'original_quality_policy_required')
    validate_policy({'quality_policy': policy}, policy)
    if saved and supplied is not None:
        need(all(key in policy and digest(value) == digest(policy[key]) for key, value in saved.items()),
             'quality_policy_mismatch')
    return policy


def bounds(policy):
    lower, upper = BOUNDS[policy['tier']]
    if policy['min_gib'] is not None or policy['max_gib'] is not None:
        lower = policy['min_gib'] if policy['min_gib'] is not None else lower
        upper = policy['max_gib']
    elif policy['allow_upward']:
        upper = None
    return lower, upper


def material(detail):
    return '\n'.join([detail['release']['title'], detail['description'],
                      *[entry['name'] for entry in detail['files']]])


def quotes_valid(quotes, detail):
    text = material(detail)
    return (isinstance(quotes, list) and bool(quotes) and
            all(isinstance(q, str) and q.strip() and q in text for q in quotes))


def draft_comparison():
    # Deliberately incomplete: an Agent must record the actual decision.
    return dict(result=None, reason='', limitations='', alternatives=[])


def validate_comparison(review, selected, base, *, client=None, timeout=20):
    """Validate citations/freshness, not pretend to evaluate human picture quality."""
    from anime_release.reviewed import load_report, resolve_path
    from anime_release import raw_evidence as raw
    comparison = review.get('quality_comparison') or {}
    need(comparison.get('result') in {'clear_advantage', 'comparable', 'unknown', 'only_eligible'},
         'quality_comparison_required')
    need(isinstance(comparison.get('reason'), str) and bool(comparison['reason'].strip()),
         'quality_comparison_required')
    if comparison['result'] == 'unknown':
        need(bool(comparison.get('limitations')), 'quality_uncertainty_required')
    alternatives = comparison.get('alternatives')
    need(isinstance(alternatives, list), 'invalid_quality_comparison')
    seen = {selected['release']['nyaa_id']}
    for alt in alternatives:
        need(isinstance(alt, dict) and bool(alt.get('reason')), 'invalid_quality_comparison')
        old = load_report(resolve_path(base, alt.get('detail_report')), 'nyaa_detail')
        cid = old['release']['nyaa_id']
        need(cid not in seen, 'duplicate_quality_candidate')
        seen.add(cid)
        need(raw.digest(raw.stable_detail(old)) == old['content_sha256'], 'saved_detail_corrupt')
        fresh = raw.details(cid, client=client, timeout=timeout)
        need(fresh['content_sha256'] == old['content_sha256'], 'comparison_details_changed')
        need(alt.get('relation') in {'better', 'comparable', 'unknown', 'ineligible'}, 'invalid_quality_comparison')
        need(quotes_valid(alt.get('quotes'), fresh), 'quality_evidence_required')
    if comparison['result'] == 'clear_advantage':
        need(quotes_valid(comparison.get('selected_quotes'), selected), 'quality_evidence_required')
        need(any(a.get('relation') == 'better' for a in alternatives), 'quality_alternative_required')
    return comparison


def validate_requirements(review, detail, policy):
    from search_nyaa_releases import detect_chinese_in_detail
    selection = review['selection']
    subtitle_quotes = selection.get('subtitle_quotes', [])
    if subtitle_quotes:
        need(quotes_valid(subtitle_quotes, detail), 'subtitle_evidence_required')
    if policy['require_zh']:
        need(quotes_valid(subtitle_quotes, detail) and
             detect_chinese_in_detail('\n'.join(subtitle_quotes))[0], 'subtitle_unqualified')
    entries = selection.get('requirement_evidence', [])
    for kind, values in [('audio', policy['require_audio']), ('source', policy['require_source'])]:
        for value in values:
            need(any(e.get('kind') == kind and e.get('value') == value and bool(e.get('reason'))
                     and quotes_valid(e.get('quotes'), detail) for e in entries), 'requirement_evidence_required')


def inspection_key(candidate):
    """Ascending practical order only; size/codec/bitrate/score never enter it."""
    from nyaa_client import nyaa_id_from_url
    cid = nyaa_id_from_url(candidate.url or '') or '0'
    return (not candidate.detail_chinese_confirmed, -max(candidate.seeders, 0),
            2 if getattr(candidate, 'avoided_group', False) else int(not getattr(candidate, 'preferred_group', False)), int(cid))
