from unittest.mock import patch

from test_release_finder import candidate, search_args, core
from failure_recovery import recovery_plan


def test_partial_alias_failure_cannot_prove_target_absent():
    args = search_args()
    old = candidate('[G] Re:ZERO S04E11 [1080p]', '1.5 GiB', 10)
    with patch.object(core, 'collect_raw_candidates', return_value=([old], ['alias timed out'], 'miss-partial')):
        report = core.search_release_report(args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12)
    assert report.status == 'network_error'
    assert not report.selected


def test_partial_alias_failure_retains_rejections_without_false_negative():
    args = search_args()
    small = candidate('[G] Re:ZERO S04E12 [1080p]', '500 MiB', 10)
    with patch.object(core, 'collect_raw_candidates', return_value=([small], ['alias timed out'], 'miss-partial')):
        report = core.search_release_report(args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12)
    assert report.status == 'network_error'
    assert report.diagnostics['below_min_count'] == 1
    assert report.diagnostics['target_candidate_count'] == 1


def test_partial_latest_cannot_deliver_older_surviving_release():
    args = search_args()
    old = candidate('[G] Re:ZERO S04E11 [1080p]', '1.5 GiB', 10)
    with patch.object(core, 'collect_raw_candidates', return_value=([old], ['alias timed out'], 'miss-partial')):
        report = core.search_release_report(args, core.SearchIntent.LATEST_REGULAR)
    assert report.status == 'latest_unresolved'
    assert not report.selected
    plan = recovery_plan({'status': report.status, 'intent': 'latest_regular',
                          'diagnostic': report.diagnostics})
    assert not plan['latest_confirmed']


def test_complete_quality_rejection_is_distinct_from_failed_query():
    args = search_args()
    small = candidate('[G] Re:ZERO S04E12 [1080p]', '500 MiB', 10)
    with patch.object(core, 'collect_raw_candidates', return_value=([small], [], 'miss')):
        report = core.search_release_report(args, core.SearchIntent.SPECIFIC_EPISODE, requested_episode=12)
    assert report.status == 'release_unqualified'
    plan = recovery_plan({'status': report.status, 'diagnostic': report.diagnostics})
    assert plan['release_confirmed']
    assert plan['retry_basis'] == 'resource_availability'


def test_airing_metadata_does_not_prove_a_release_for_retry():
    plan = recovery_plan({'status': 'no_nyaa_release_for_target', 'target_episode': 9,
                          'availability': {'state': 'aired_no_release', 'official_target': True}})
    assert not plan['release_confirmed']
    assert plan['retry_basis'] is None
    assert plan['action'] == 'bounded_supplement_then_eligible_rescue'


def test_client_timeout_has_separate_retry_basis_and_requires_authorization():
    plan = recovery_plan({'status': 'download_enqueue_failed', 'selected': {'title': 'episode'},
                          'qbittorrent': {'error_code': 'startup_timeout', 'retryable': True}})
    assert plan['release_confirmed']
    assert plan['retry_basis'] == 'client_transient'
    assert plan['scheduled_retry_requires_prompt_authorization']
    assert plan['action'] == 'diagnose_client'


def test_permission_denial_and_unknown_client_cause_do_not_schedule():
    for retryable in (False, None):
        plan = recovery_plan({'status': 'download_enqueue_failed',
                              'qbittorrent': {'retryable': retryable}})
        assert plan['retry_basis'] is None
        assert plan['action'] == 'diagnose_client'


def test_already_handled_and_future_boundaries_stop_recovery():
    for status in ('latest_already_handled', 'not_aired_yet', 'airing_schedule_break',
                   'long_break_unconfirmed', 'split_cour_break', 'part_finished', 'found'):
        plan = recovery_plan({'status': status})
        assert plan['action'] == 'stop'
        assert plan['retry_basis'] is None
