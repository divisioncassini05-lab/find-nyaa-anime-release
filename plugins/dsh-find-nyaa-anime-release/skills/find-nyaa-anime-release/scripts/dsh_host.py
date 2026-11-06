#!/usr/bin/env python3
"""Convert real DSH scheduler readbacks into the existing v3 evidence contracts.

This module never calls, edits or deletes a scheduler. The Agent supplies the
unmodified schedule tool JSON. Missing, partial or stale inventory fails closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from dsh_paths import data_home

MAX_AGE_SECONDS = 120
DAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')


def now_utc():
    return datetime.now(timezone.utc)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp_required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone_required')
    return result


def fresh(value, now=None):
    age = ((now or now_utc()) - timestamp(value)).total_seconds()
    if not 0 <= age <= MAX_AGE_SECONDS:
        raise ValueError('scheduler_snapshot_stale_or_future')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_json(path, value):
    write_atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def valid_task(task):
    if not isinstance(task, dict) or 'code' in task:
        raise ValueError('scheduler_tool_error_is_not_absence')
    for key in ('id', 'title', 'prompt', 'kind', 'scheduledAt'):
        if not isinstance(task.get(key), str) or not task[key]:
            raise ValueError('invalid_scheduler_task_' + key)
    if task.get('status') not in {'active', 'paused', 'ended'} or not isinstance(task.get('target'), dict):
        raise ValueError('invalid_scheduler_task_status_or_target')
    timestamp(task['scheduledAt'])
    return task


def parse_inventory(payload, now=None):
    if not isinstance(payload, dict):
        raise ValueError('scheduler_inventory_object_required')
    fresh(payload.get('observed_at'), now)
    pages = payload.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('complete_unfiltered_schedule_list_required')
    tasks, seen, offset, total = [], set(), 0, None
    for page in pages:
        if not isinstance(page, dict) or 'code' in page:
            raise ValueError('scheduler_list_failed')
        if page.get('active') is not None:
            raise ValueError('filtered_schedule_list_not_authoritative')
        rows, count = page.get('items'), page.get('total')
        if (not isinstance(rows, list) or type(count) is not int or count < 0
                or type(page.get('offset')) is not int or page['offset'] != offset
                or type(page.get('shown')) is not int or page['shown'] != len(rows)
                or type(page.get('limit')) is not int or not 1 <= page['limit'] <= 500
                or len(rows) > page['limit'] or (total is not None and count != total)):
            raise ValueError('incomplete_or_changed_scheduler_pagination')
        total = count
        for task in rows:
            valid_task(task)
            if task['id'] in seen:
                raise ValueError('duplicate_scheduler_task')
            seen.add(task['id'])
            tasks.append(task)
        offset += len(rows)
    if offset != total:
        raise ValueError('incomplete_scheduler_inventory')
    if payload.get('unfiltered') is not True:
        raise ValueError('confirm_schedule_list_called_without_active_filter')
    return {'schema': 1, 'complete': True, 'checked_at': payload['observed_at'], 'tasks': tasks}


def import_inventory(payload, now=None):
    path = data_home() / 'scheduler' / 'inventory.json'
    try:
        inventory = parse_inventory(payload, now)
    except (ValueError, TypeError, KeyError) as exc:
        save_json(path, {'schema': 1, 'complete': False, 'error': str(exc)})
        raise
    save_json(path, inventory)
    return {'status': 'snapshot_saved', 'task_count': len(inventory['tasks']),
            'path': str(path), 'valid_seconds': MAX_AGE_SECONDS}


def import_inventory_file(path):
    try:
        payload = read_json(path)
    except (OSError, ValueError) as exc:
        save_json(data_home() / 'scheduler' / 'inventory.json',
                  {'schema': 1, 'complete': False, 'error': str(exc)})
        raise
    return import_inventory(payload)


def inventory_for_state(data, now=None):
    try:
        snapshot = read_json(data_home() / 'scheduler' / 'inventory.json')
        if not isinstance(snapshot, dict) or snapshot.get('schema') != 1 or snapshot.get('complete') is not True:
            raise ValueError('scheduler_inventory_not_complete')
        fresh(snapshot.get('checked_at'), now)
        entries, seen = [], set()
        for task in snapshot['tasks']:
            valid_task(task)
            if task['id'] in seen:
                raise ValueError('duplicate_scheduler_task')
            seen.add(task['id'])
            text = (task['prompt'] + '\n' + task['title']).casefold()
            matches = []
            for show in data['shows']:
                track_id = show['track_id']
                names = [show['identity']['title'], *show['identity'].get('aliases', [])]
                explicit = re.search(r'(?<![\w-])' + re.escape(track_id.casefold()) + r'(?![\w-])', text)
                named = any(name and (re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', text)
                            if name.isascii() else name.casefold() in text) for name in names)
                if explicit or named:
                    matches.append(track_id)
            entries.append({'automation_id': task['id'],
                            'scope_hash': hashlib.sha256(task['prompt'].encode('utf-8')).hexdigest(),
                            'referenced_track_ids': matches})
        return {'automations': entries, 'errors': []}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'automations': [], 'errors': [{'error': 'dsh_scheduler_inventory_unavailable',
                                              'reason': str(exc), 'required_tool': 'schedule_list'}]}


def task_snapshot(payload, now=None):
    if not isinstance(payload, dict):
        raise ValueError('scheduler_task_snapshot_object_required')
    fresh(payload.get('observed_at'), now)
    task = valid_task(payload['task'])
    rule, zone = None, task.get('timeZone')
    if task['kind'] == 'weekly':
        weekdays = task.get('weekdays')
        clock = re.fullmatch(r'([01]\d|2[0-3]):([0-5]\d)(?::00(?:\.0{1,3})?)?', task.get('time', ''))
        if (isinstance(weekdays, list) and len(weekdays) == 1 and type(weekdays[0]) is int
                and 1 <= weekdays[0] <= 7 and clock):
            rule = f'RRULE:FREQ=WEEKLY;BYDAY={DAYS[weekdays[0]-1]};BYHOUR={int(clock[1])};BYMINUTE={int(clock[2])}'
    elif task['kind'] == 'rrule':
        lines = task.get('rrule', '').splitlines()
        rules = [line for line in lines if line.startswith('RRULE:')]
        starts = [line for line in lines if line.startswith('DTSTART')]
        if len(rules) == 1 and len(starts) == 1:
            rule = rules[0]
            match = re.match(r'DTSTART;TZID=([^:]+):', starts[0])
            zone = match[1] if match else 'UTC' if starts[0].endswith('Z') else None
    supported = False
    if rule and zone == 'Asia/Shanghai':
        from scheduled_watch import weekly_fields
        try:
            weekly_fields(rule)
            supported = True
        except (ValueError, KeyError):
            pass
    return {'id': task['id'], 'name': task['title'], 'prompt': task['prompt'],
            'status': task['status'].upper(), 'rrule': rule,
            'raw_task': task, 'observed_at': payload['observed_at'],
            'scope_hash': hashlib.sha256(task['prompt'].encode('utf-8')).hexdigest(),
            'retry_supported': supported, 'timezone': zone,
            'memory_directory': str(data_home() / 'scheduler' / 'memory' / hashlib.sha256(task['id'].encode()).hexdigest())}


def binding_toml(snapshot):
    # JSON strings are a subset of TOML basic strings; no raw prompt interpolation.
    fields = {key: snapshot[key] for key in ('id', 'name', 'prompt', 'status')}
    if snapshot['rrule']:
        fields['rrule'] = snapshot['rrule']
    return '\n'.join(key + ' = ' + json.dumps(value, ensure_ascii=False) for key, value in fields.items()) + '\n'


def retry_edit(plan, snapshot, saved_intent, now=None):
    fresh(snapshot['observed_at'], now)
    if not snapshot.get('retry_supported'):
        raise ValueError('retry_requires_single_weekly_asia_shanghai_rule')
    from scheduled_watch import prepare_update, weekly_fields, SHANGHAI
    current = (now or now_utc()).astimezone(SHANGHAI)
    decision = prepare_update(plan, snapshot, saved_intent, current.isoformat())
    if decision['status'] == 'already_applied':
        return decision
    updated = snapshot['raw_task'].get('updatedAt')
    if not isinstance(updated, str) or not updated:
        raise ValueError('scheduler_revision_required')
    if plan.get('next_retry_at'):
        start = timestamp(plan['next_retry_at']).astimezone(SHANGHAI)
    else:
        weekday, hour, minute = weekly_fields(plan['desired_rrule'])
        start = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        start += timedelta(days=(weekday - start.weekday()) % 7)
        if start <= current:
            start += timedelta(days=7)
    full_rule = 'DTSTART;TZID=Asia/Shanghai:' + start.strftime('%Y%m%dT%H%M%S') + '\n' + plan['desired_rrule']
    return {'status': 'update_required', 'required_tool': 'schedule_edit',
            'arguments': {'id': snapshot['id'], 'action': 'update', 'rrule': full_rule,
                          'expectedUpdatedAt': updated},
            'preserve_other_fields': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    sub = commands.add_parser('import-inventory')
    sub.add_argument('--input', type=Path, required=True)
    sub = commands.add_parser('task-snapshot')
    sub.add_argument('--input', type=Path, required=True)
    sub.add_argument('--output', type=Path, required=True)
    sub.add_argument('--toml', type=Path)
    sub = commands.add_parser('retry-edit')
    for field in ('plan', 'snapshot', 'saved-intent'):
        sub.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'import-inventory':
            result = import_inventory_file(args.input)
        elif args.command == 'task-snapshot':
            snapshot = task_snapshot(read_json(args.input))
            save_json(args.output, snapshot)
            if args.toml:
                write_atomic(args.toml, binding_toml(snapshot))
            result = {'status': 'snapshot_saved', 'output': str(args.output),
                      'binding_config': str(args.toml) if args.toml else None,
                      'scope_hash': snapshot['scope_hash'], 'retry_supported': snapshot['retry_supported'],
                      'memory_directory': snapshot['memory_directory']}
        else:
            result = retry_edit(read_json(args.plan), read_json(args.snapshot), read_json(args.saved_intent))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'host_adapter_error', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
