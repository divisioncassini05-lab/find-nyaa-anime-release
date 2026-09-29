"""Per-run structured stage records, isolated across recursive batch runs."""
from contextvars import ContextVar
from datetime import datetime, timezone

TRACE = ContextVar('release_stage_trace', default=None)

def trace_stage(stage, **evidence):
    trace = TRACE.get()
    if trace is not None:
        trace.append({'stage': stage, 'at': datetime.now(timezone.utc).isoformat(), **evidence})

def attach_trace(report):
    report.setdefault('stages', list(TRACE.get() or []))
    if 'error_detail' not in report:
        phases = {'identity_conflict': 'identity', 'ambiguous': 'identity',
                  'latest_unresolved': 'target', 'release_unqualified': 'verification',
                  'subtitle_unqualified': 'verification', 'subtitle_check_incomplete': 'verification',
                  'output_incomplete': 'verification', 'download_enqueue_failed': 'delivery',
                  'network_error': 'retrieval', 'state_corrupt': 'state_read'}
        if report.get('status') in phases:
            report['error_detail'] = {'stage': phases[report['status']], 'code': report['status'],
                'retryable': False, 'evidence': report.get('diagnostic', {}),
                'next_action': (report.get('recovery') or {}).get('next_action', 'inspect_stage_evidence')}
    return report
