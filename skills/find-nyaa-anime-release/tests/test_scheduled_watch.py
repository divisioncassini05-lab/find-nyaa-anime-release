"""Offline schedule policy, read-back fault injection and template contracts."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from scheduled_watch import plan_retry, prepare_update, verify_application, main

PROMPT = '使用 $find-nyaa-anime-release 追踪固定 S01'
RULE = 'RRULE:FREQ=WEEKLY;BYDAY=TH;BYHOUR=22;BYMINUTE=0'


def context(**overrides):
    value = dict(automation_id='test-anime', scope_hash=hashlib.sha256(PROMPT.encode()).hexdigest(),
                 timezone='Asia/Shanghai', regular_rrule=RULE, current_rrule=RULE,
                 now='2026-10-01T22:00:00+08:00', window_start='2026-10-01T22:00:00+08:00',
                 attempt=0, outcome='not_updated')
    return {**value, **overrides}


def snapshot(**overrides):
    return dict(id='test-anime', prompt=PROMPT, rrule=RULE, status='ACTIVE',
                model='preserved', **overrides)


@pytest.mark.parametrize('reason', ['not_updated','release_unqualified','network_transient','detail_incomplete'])
def test_retry_crosses_midnight(reason):
    plan = plan_retry(context(outcome=reason))
    assert plan['action'] == 'retry' and plan['next_attempt'] == 1
    assert plan['next_retry_at'] == '2026-10-02T02:00:00+08:00'
    assert 'BYDAY=FR;BYHOUR=2;BYMINUTE=0' in plan['desired_rrule']


def test_minute_resolution_rounds_up():
    plan = plan_retry(context(now='2026-10-01T22:00:30+08:00'))
    assert plan['next_retry_at'] == '2026-10-02T02:01:00+08:00'


@pytest.mark.parametrize('attempt', [0,1,2,3])
def test_three_retry_cap(attempt):
    plan = plan_retry(context(attempt=attempt))
    assert plan['action'] == ('retry' if attempt < 3 else 'restore_regular')
    if attempt == 3:
        assert plan['reason'] == 'retry_exhausted' and plan['desired_rrule'] == RULE


@pytest.mark.parametrize('now,reason', [
    ('2026-10-08T18:00:00+08:00','next_regular_check_due'),
    ('2026-10-08T22:00:00+08:00','window_expired')])
def test_never_retry_into_next_window(now, reason):
    plan = plan_retry(context(now=now))
    assert plan['action'] == 'restore_regular' and plan['reason'] == reason


def test_old_handled_episode_is_not_current_window_success():
    assert plan_retry(context(outcome='latest_already_handled'))['action'] == 'retry'
    assert plan_retry(context(outcome='latest_already_handled', current_window_release_verified=True))['reason'] == 'window_succeeded'


def test_acceptance_without_commit_does_not_succeed():
    with pytest.raises(ValueError, match='committed_acceptance_required'):
        plan_retry(context(outcome='delivered'))
    assert plan_retry(context(outcome='delivered', accepted_and_committed=True))['action'] == 'restore_regular'


@pytest.mark.parametrize('reason', ['pre_airing','hiatus','blocked','identity_ambiguous',
    'permission_denied','permanent_failure','tls_failure','read_only_done'])
def test_no_timed_retry_for_excluded_causes(reason):
    assert plan_retry(context(outcome=reason))['action'] == 'restore_regular'


@pytest.mark.parametrize('reason,action', [('completed','drain_outbox'),
    ('cleanup_pending','drain_outbox'), ('client_recovery','recover_operation'),
    ('finale_pending_evidence','await_completion')])
def test_terminal_and_recovery_precede_resource_retry(reason, action):
    result = plan_retry(context(outcome=reason))
    assert result['action'] == action and result['next_retry_at'] is None


def test_memory_write_failure_prevents_update():
    plan = plan_retry(context()); tool = Mock()
    with pytest.raises(ValueError, match='durable_intent_required'):
        changes = prepare_update(plan, snapshot(), None, context()['now'])
        tool(changes)
    tool.assert_not_called()


def test_timeout_after_update_readback_and_repeat_are_idempotent():
    plan = plan_retry(context()); saved = copy.deepcopy(plan); live = snapshot()
    tool = Mock()
    def update(**changes):
        live.update(changes)
        raise TimeoutError('response lost after apply')
    tool.side_effect = update
    gate = prepare_update(plan, live, saved, context()['now'])
    with pytest.raises(TimeoutError): tool(**gate['changes'])
    assert verify_application(plan, live, saved)['status'] == 'schedule_verified'
    assert prepare_update(plan, live, saved, context()['now'])['status'] == 'already_applied'
    assert tool.call_count == 1 and live['model'] == 'preserved'


def test_timeout_before_update_is_not_success():
    plan = plan_retry(context())
    with pytest.raises(ValueError, match='schedule_not_applied'):
        verify_application(plan, snapshot(), plan)


@pytest.mark.parametrize('field,value,error', [
    ('id','other','automation_id_mismatch'),('prompt','changed','automation_scope_changed'),
    ('status','PAUSED','automation_not_active'),
    ('rrule','RRULE:FREQ=WEEKLY;BYDAY=WE;BYHOUR=12;BYMINUTE=0','automation_schedule_changed')])
def test_human_changes_block_replay(field,value,error):
    plan = plan_retry(context()); live = snapshot(); live[field] = value
    with pytest.raises(ValueError, match=error):
        prepare_update(plan, live, plan, context()['now'])


def test_late_update_requires_new_plan():
    plan = plan_retry(context())
    with pytest.raises(ValueError, match='retry_time_expired_replan'):
        prepare_update(plan, snapshot(), plan, plan['next_retry_at'])


def test_success_restores_original_schedule_using_same_id():
    retry = plan_retry(context()); live = snapshot(); live['rrule'] = retry['desired_rrule']
    done = plan_retry(context(current_rrule=live['rrule'], outcome='delivered',
                            accepted_and_committed=True, attempt=1, now=retry['next_retry_at']))
    gate = prepare_update(done, live, done, retry['next_retry_at'])
    assert gate['automation_id'] == live['id'] and gate['changes'] == {'rrule':RULE}
    live.update(gate['changes'])
    assert verify_application(done, live, done)['next_retry_at'] is None


def test_cli_is_read_only(tmp_path, capsys):
    input_file = tmp_path/'input.json'; input_file.write_text(json.dumps(context()), encoding='utf8')
    before = input_file.read_bytes()
    assert main(['plan','--input',str(input_file)]) == 0
    assert json.loads(capsys.readouterr().out)['action'] == 'retry'
    assert input_file.read_bytes() == before and len(list(tmp_path.iterdir())) == 1


def test_template_creation_and_override_contract():
    root = Path(__file__).resolve().parents[1]
    entry = (root/'SKILL.md').read_text(encoding='utf-8-sig')
    reference = (root/'references/scheduled-new-anime.md').read_text(encoding='utf-8-sig')
    assert 'references/scheduled-new-anime.md' in entry
    prompt = reference.split('```text\n',1)[1].split('\n```',1)[0]
    assert prompt.count('{{') == 5
    for phrase in ('最多补查 3 次', '4 小时', '不虚构下一集', 'cleanup_pending',
                   '--enqueue-qbittorrent', '--allow-upward-compatibility', '恢复原 operation_id',
                   'watch cleanup --run RUN_DIR', '不创建第二个任务', '身份未解决时停止创建',
                   '相同目标和用途优先复用', 'read_only_done', '首次交付前修复'):
        assert phrase in reference
    for filename in ('completion.md','failure-recovery.md'):
        text = (root/'references'/filename).read_text(encoding='utf-8-sig')
        assert 'scripts/find_anime_release.py' not in text

