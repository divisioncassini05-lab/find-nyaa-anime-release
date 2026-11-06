import json
import pytest
from scheduled_watch import trigger_gate, main

RULE = 'RRULE:FREQ=WEEKLY;BYDAY=SA;BYHOUR=23;BYMINUTE=0'


def test_actual_oct24_early_arrival_waits_for_new_window():
    result = trigger_gate(RULE, '2026-10-24T14:58:00.296Z')
    assert result['action'] == 'wait_until_due'
    assert result['due_at'] == '2026-10-24T23:00:00+08:00'
    assert result['remaining_seconds'] == 120
    assert result['wait_seconds'] == 60
    assert result['counts_as_attempt'] is False
    assert result['schedule_mutation_required'] is False


@pytest.mark.parametrize('time,action,wait', [
    ('22:55:00', 'wait_until_due', 60),
    ('22:59:30', 'wait_until_due', 30),
    ('23:00:00', 'due', 0),
    ('23:02:00', 'due', 0),
])
def test_arrival_boundaries(time, action, wait):
    result = trigger_gate(RULE, f'2026-10-24T{time}+08:00')
    assert result['action'] == action
    assert result['wait_seconds'] == wait
    assert result['due_at'] == '2026-10-24T23:00:00+08:00'


def test_midnight_retry_uses_exact_due_and_does_not_consume_attempt():
    rule = 'RRULE:FREQ=WEEKLY;BYDAY=SU;BYHOUR=0;BYMINUTE=0'
    result = trigger_gate(rule, '2026-10-24T23:58:00+08:00', '2026-10-25T00:00:00+08:00')
    assert result['action'] == 'wait_until_due'
    assert result['counts_as_attempt'] is False


def test_far_future_retry_does_not_wait_or_run():
    result = trigger_gate(RULE, '2026-10-24T22:00:00+08:00', '2026-10-24T23:00:00+08:00')
    assert result['action'] == 'not_due'
    assert result['wait_seconds'] == 0


def test_changed_schedule_rejects_stale_retry_due():
    with pytest.raises(ValueError, match='due_must_match_current_schedule'):
        trigger_gate(RULE, '2026-10-24T22:58:00+08:00', '2026-10-24T22:00:00+08:00')


def test_naive_time_rejected():
    with pytest.raises(ValueError, match='timezone_required'):
        trigger_gate(RULE, '2026-10-24T22:58:00')


def test_cli_replay_does_not_sleep_or_write(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(['gate', '--rrule', RULE, '--now', '2026-10-24T22:58:00+08:00']) == 0
    assert json.loads(capsys.readouterr().out)['action'] == 'wait_until_due'
    assert list(tmp_path.iterdir()) == []
