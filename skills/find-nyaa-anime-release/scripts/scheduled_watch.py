"""Read-only retry planning and scheduler read-back verification.

No tracking writes, scheduler calls, downloads, or inferred episode evidence.
The Agent persists the returned intent before calling the app's automation tool.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
DAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')
RETRY_OUTCOMES = {'not_updated', 'release_unqualified', 'network_transient', 'detail_incomplete'}
STOP_OUTCOMES = {'pre_airing', 'hiatus', 'blocked', 'identity_ambiguous',
                 'permission_denied', 'permanent_failure', 'tls_failure', 'read_only_done'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone_required')
    return result.astimezone(SHANGHAI)


def weekly_fields(rrule):
    fields = dict(item.split('=', 1) for item in rrule.removeprefix('RRULE:').split(';'))
    if (fields.get('FREQ') != 'WEEKLY' or fields.get('BYDAY') not in DAYS
            or set(fields) - {'FREQ', 'BYDAY', 'BYHOUR', 'BYMINUTE', 'BYSECOND', 'INTERVAL'}
            or fields.get('INTERVAL', '1') != '1' or fields.get('BYSECOND', '0') != '0'):
        raise ValueError('single_weekly_schedule_required')
    hour, minute = int(fields['BYHOUR']), int(fields['BYMINUTE'])
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError('invalid_schedule_time')
    return DAYS.index(fields['BYDAY']), hour, minute


def plan_retry(data):
    """attempt is the current executed check: main=0, retries=1..3.

    window_start is the original main tick, not the temporary retry tick.
    Scope hash is SHA-256 of the exact saved prompt, excluding the schedule.
    """
    if not data.get('automation_id') or not re.fullmatch('[0-9a-f]{64}', data.get('scope_hash', '')):
        raise ValueError('exact_automation_binding_required')
    if data.get('timezone') != 'Asia/Shanghai':
        raise ValueError('template_timezone_required')
    attempt = data['attempt']
    if type(attempt) is not int or not 0 <= attempt <= 3:
        raise ValueError('invalid_attempt')
    now, start = timestamp(data['now']), timestamp(data['window_start'])
    weekday, hour, minute = weekly_fields(data['regular_rrule'])
    if (start.weekday(), start.hour, start.minute, start.second, start.microsecond) != (weekday, hour, minute, 0, 0):
        raise ValueError('window_must_match_regular_schedule')
    if now < start:
        raise ValueError('window_not_started')
    end = start + timedelta(days=7)
    result = {key: data[key] for key in ('automation_id', 'scope_hash', 'regular_rrule', 'timezone')}
    result.update(window_start=start.isoformat(), window_end=end.isoformat(), attempt=attempt,
                  outcome=data['outcome'], desired_rrule=data['regular_rrule'], next_retry_at=None,
                  next_attempt=None, action='restore_regular', requires_saved_intent=True,
                  observed_rrule=data.get('current_rrule', data['regular_rrule']))
    weekly_fields(result['observed_rrule'])
    outcome = data['outcome']
    if outcome in {'completed', 'cleanup_pending'}:
        result.update(action='drain_outbox', reason=outcome)
    elif outcome == 'client_recovery':
        result.update(action='recover_operation', reason=outcome)
    elif outcome == 'finale_pending_evidence':
        result.update(action='await_completion', reason=outcome)
    elif now >= end:
        result['reason'] = 'window_expired'
    elif outcome == 'delivered':
        if data.get('accepted_and_committed') is not True:
            raise ValueError('committed_acceptance_required')
        result['reason'] = 'window_succeeded'
    elif outcome == 'latest_already_handled' and data.get('current_window_release_verified') is True:
        result['reason'] = 'window_succeeded'
    elif outcome in RETRY_OUTCOMES or outcome == 'latest_already_handled':
        # Round up so minute-resolution scheduling never shortens the four-hour delay.
        target = now + timedelta(hours=4)
        if target.second or target.microsecond:
            target = target.replace(second=0, microsecond=0) + timedelta(minutes=1)
        if attempt == 3:
            result['reason'] = 'retry_exhausted'
        elif target >= end:
            result['reason'] = 'next_regular_check_due'
        else:
            result.update(action='retry', reason=outcome, next_attempt=attempt + 1,
                          next_retry_at=target.isoformat(),
                          desired_rrule=f'RRULE:FREQ=WEEKLY;BYDAY={DAYS[target.weekday()]};BYHOUR={target.hour};BYMINUTE={target.minute}')
    elif outcome in STOP_OUTCOMES:
        result['reason'] = outcome
    else:
        raise ValueError('unknown_outcome')
    result['plan_id'] = digest(result)
    return result


def validate_intent(plan, snapshot, saved_intent):
    if saved_intent != plan or plan.get('plan_id') != digest({k:v for k,v in plan.items() if k != 'plan_id'}):
        raise ValueError('durable_intent_required')
    if snapshot.get('id') != plan['automation_id']:
        raise ValueError('automation_id_mismatch')
    actual_scope = hashlib.sha256(snapshot['prompt'].encode('utf-8')).hexdigest()
    if actual_scope != plan['scope_hash']:
        raise ValueError('automation_scope_changed')
    if snapshot.get('status') != 'ACTIVE':
        raise ValueError('automation_not_active')


def prepare_update(plan, snapshot, saved_intent, now):
    """Read-only gate before the Agent calls automation_update with full fields."""
    validate_intent(plan, snapshot, saved_intent)
    current = weekly_fields(snapshot['rrule'])
    desired = weekly_fields(plan['desired_rrule'])
    if current not in (weekly_fields(plan['observed_rrule']), desired):
        raise ValueError('automation_schedule_changed')
    if plan['next_retry_at'] and timestamp(plan['next_retry_at']) <= timestamp(now):
        raise ValueError('retry_time_expired_replan')
    return {'status':'already_applied' if current == desired else 'update_required',
            'automation_id':plan['automation_id'], 'changes':{'rrule':plan['desired_rrule']},
            'plan_id':plan['plan_id'], 'preserve_other_fields':True}


def verify_application(plan, snapshot, saved_intent):
    """Only live read-back plus the exact durable intent confirms a schedule change."""
    validate_intent(plan, snapshot, saved_intent)
    if weekly_fields(snapshot['rrule']) != weekly_fields(plan['desired_rrule']):
        raise ValueError('schedule_not_applied')
    return {'status':'schedule_verified', 'automation_id':plan['automation_id'],
            'plan_id':plan['plan_id'], 'next_retry_at':plan['next_retry_at']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan'); plan.add_argument('--input', type=Path, required=True)
    for command in ('prepare', 'verify'):
        sub = commands.add_parser(command)
        for name in ('plan', 'snapshot', 'saved-intent'):
            sub.add_argument('--'+name, type=Path, required=True)
        if command == 'prepare':
            sub.add_argument('--now', required=True)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))
    try:
        if args.command == 'plan':
            result = plan_retry(read(args.input))
        else:
            values = (read(args.plan), read(args.snapshot), read(args.saved_intent))
            result = prepare_update(*values, args.now) if args.command == 'prepare' else verify_application(*values)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, TypeError, OSError) as exc:
        print(json.dumps({'status':'schedule_plan_error', 'error':str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
