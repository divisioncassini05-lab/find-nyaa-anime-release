import pytest
from test_qbittorrent_submit import qbt


@pytest.mark.parametrize('code', ['startup_exited_without_client', 'handoff_unverified'])
def test_context_failure_preserves_evidence_and_requires_full_approved_retry(code):
    error = qbt.SubmissionError('unverified', code=code,
                                diagnostics={'info_hash': 'a' * 40, 'submission_attempts': 2})
    report = error.as_report()
    assert report['info_hash'] == 'a' * 40
    assert report['submission_attempts'] == 2
    assert report['ok'] is False
    recovery = report['client_recovery']
    assert recovery['requires_execution_tool_approval']
    assert recovery['startup_only_is_insufficient']
    assert recovery['recheck_acceptance_before_submission']
    assert recovery['max_context_retries'] == 1
    assert recovery['cause_confirmed'] is False


@pytest.mark.parametrize('code', ['permission_denied', 'executable_missing', 'client_busy'])
def test_unrelated_failure_does_not_authorize_context_retry(code):
    assert 'client_recovery' not in qbt.SubmissionError('failed', code=code).as_report()
