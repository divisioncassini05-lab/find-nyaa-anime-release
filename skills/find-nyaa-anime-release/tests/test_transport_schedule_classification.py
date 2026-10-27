import pytest
from http_transport import TransportError, scheduled_outcome
from scheduled_watch import plan_retry


@pytest.mark.parametrize('code', ['tls_unexpected_eof', 'tls_handshake_failed', 'timeout'])
def test_interrupted_connection_gets_bounded_retry(code):
    error = TransportError(code, [{'backend':'urllib','code':'tls_unexpected_eof'}], 'nyaa.si')
    assert error.scheduled_outcome == 'network_transient'
    data = dict(automation_id='test', scope_hash='a'*64, timezone='Asia/Shanghai',
                regular_rrule='RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=23;BYMINUTE=0',
                window_start='2026-10-24T23:00:00+08:00', now='2026-10-27T13:00:00+08:00',
                attempt=0, outcome=error.scheduled_outcome)
    result = plan_retry(data)
    assert result['action'] == 'retry'
    assert result['next_retry_at'] == '2026-10-27T17:00:00+08:00'
    assert plan_retry({**data,'attempt':3})['reason'] == 'retry_exhausted'


@pytest.mark.parametrize('earlier,expected', [
    ('tls_certificate_verification_failed','tls_failure'),
    ('tls_user_context_unavailable','tls_failure'),
    ('permission_denied','permission_denied'),
])
def test_security_failure_is_not_hidden_by_later_generic_handshake(earlier, expected):
    assert scheduled_outcome('tls_handshake_failed', [{'code':earlier}]) == expected


def test_unknown_failure_is_not_automatically_retried():
    assert scheduled_outcome('unknown_tls_error', []) == 'permanent_failure'
