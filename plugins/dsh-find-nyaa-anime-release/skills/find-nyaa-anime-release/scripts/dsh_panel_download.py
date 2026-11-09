"""Explicit inbox delivery of an already reviewed resource; never run discovery."""
from dataclasses import asdict
from pathlib import Path


def compatible(entry, plan):
    policy = entry.get('qualityPolicy', {})
    return (bool(entry.get('reviewPath')) and policy.get('tier') == plan.get('tier', 'browse')
            and bool(policy.get('require_zh')) == bool(plan.get('requireZh')))


def submit(state, plan_id, info_hash, *, client=None, validator=None, evidence_client=None):
    import dsh_panel_run as panel
    from anime_release.storage import file_lock
    from watch_v3.store import StateRepository
    from watch_v3.workflow import Workflow, Request
    from watch_v3.evidence import QualityPolicy
    from watch_v3.cli import parser, client as configured_client
    from datetime import datetime, timezone
    file = panel.result_path(state, plan_id)
    with file_lock(file.with_suffix('.download.lock')):
        plan = panel.load_plan(state, plan_id)
        saved = panel.read(file, {})
        entry = next((r for r in saved.get('finds', []) if r.get('infoHash') == info_hash), None)
        if not entry or not compatible(entry, plan):
            return {'status': 'resource_review_required'}
        review_path = Path(entry['reviewPath']).resolve()
        if not review_path.is_relative_to(file.parent.resolve()) or not review_path.is_file():
            return {'status': 'resource_review_required'}
        if client is None:
            args = parser().parse_args(['--state', str(state), 'recover', '--operation', 'panel'])
            client = configured_client(args)
        status = 'download_pending'
        reason = None
        try:
            if entry['scope'] == 'regular':
                repo = StateRepository(state)
                show = repo.find(track_id=plan['trackId']) or {}
                previous = next((op for op in show.get('operations', {}).values()
                                 if op.get('info_hash') == info_hash and op.get('kind') == 'regular'), None)
                workflow = Workflow(repo, client, validator=validator)
                result = workflow.recover(previous['operation_id']) if previous else workflow.deliver(
                    Request(None, review_path, QualityPolicy(**entry['qualityPolicy'])))
                result = asdict(result)
            else:
                from package_release import deliver
                result = deliver(review_path, entry['qualityPolicy'], file.parent / 'deliveries',
                                 client, evidence_client=evidence_client)
            if result['status'] in {'delivery_recorded', 'already_accepted', 'recovered', 'accepted_receipt_commit_failed'}:
                status = 'download_submitted'
            elif result['status'] not in {'available_enqueue_failed', 'recovery_required'}:
                status = 'resource_review_required'
        except Exception as exc:
            # Never return credential-bearing exception strings to the page.
            from watch_v3.clients import ClientFailure
            if not isinstance(exc, (ClientFailure, OSError)):
                status = 'resource_review_required'
            reason = 'submission_unconfirmed' if status == 'download_pending' else 'evidence_changed'
        downloads = panel.read(file, {}).get('downloads', {})
        downloads[info_hash] = {'status': status, 'checkedAt': datetime.now(timezone.utc).isoformat(), 'reason': reason}
        panel.update_result(state, plan, {'downloads': downloads})
        return {'status': status}
