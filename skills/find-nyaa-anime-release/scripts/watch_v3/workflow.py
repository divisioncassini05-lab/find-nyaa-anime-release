"""Typed stages of the bounded local workflow. No discovery during recovery."""
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
from .clients import DeliveryRequest, ClientFailure, ClientContext, receipt
from .evidence import ReviewManifest, QualityPolicy, ReviewValidator
from .store import require, now_iso
from .outbox import drain

@dataclass(frozen=True)
class Request:
    title: str | None
    review: Path
    policy: QualityPolicy
    save_path: str | None = None
    operation_id: str | None = None

@dataclass(frozen=True)
class TargetPlan:
    episode: int | None
    phase: str
    deliverable: bool

@dataclass(frozen=True)
class WorkflowResult:
    status: str
    track_id: str | None
    operation_id: str | None = None
    receipt: dict | None = None
    recovery: dict | None = None
    report: dict | None = None
    post_commit: dict | None = None
    tracking_snapshot: dict | None = None


def normalize_request(request):
    return request, ReviewManifest.load(request.review)


def load_metadata_snapshot(repo, track_id):
    show = repo.find(track_id=track_id)
    require(show is not None, 'track_not_found')
    return show


def plan_target(show):
    phase, target = show['lifecycle']['phase'], show['progress']['target_episode']
    return TargetPlan(target, phase, phase not in {'completed', 'blocked'} and target is not None)


def preflight_delivery_context(client):
    context = client.preflight()
    if not isinstance(context, ClientContext) or not context.verified:
        raise ClientFailure('client_context_required')
    return context


def commit_delivery(repo, track_id, accepted):
    repo.command(track_id, 'record_delivery', receipt=accepted, acceptance_only=True)
    repo.command(track_id, 'record_delivery', receipt=accepted)


def reconcile_completion(repo, track_id):
    return repo.command(track_id, 'reconcile_completion')


def drain_outbox(repo, automation=None, track_id=None):
    return drain(repo, automation=automation, track_id=track_id)


def render_report(repo, result):
    current = repo.find(track_id=result.track_id) if result.track_id else None
    show = current or result.tracking_snapshot
    report = asdict(result)
    report.pop('tracking_snapshot', None)
    return {**report, 'progress':show['progress'] if show else None,
            'lifecycle':show['lifecycle'] if show else None,
            'outbox':current['outbox'] if current else [], 'local_record_exists':current is not None}


class Workflow:
    def __init__(self, repo, client, validator=None, automation=None):
        self.repo, self.client = repo, client
        self.validator = validator or ReviewValidator()
        self.automation = automation

    def deliver(self, request):
        result = self._deliver(request)
        result = self._finish(result)
        if result.status in {'delivery_recorded', 'already_accepted', 'latest_already_handled', 'completed'}:
            from dataclasses import replace
            from evidence_artifacts import cleanup
            try:
                housekeeping = cleanup(self.repo, review=request.review)
            except Exception as exc:
                housekeeping = {'status':'cleanup_pending', 'error':str(exc)}
            result = replace(result, post_commit={**(result.post_commit or {}), 'artifacts':housekeeping})
        return result

    def _finish(self, result):
        from dataclasses import replace
        if result.track_id is None:
            return result
        snapshot = self.repo.find(track_id=result.track_id)
        result = replace(result, tracking_snapshot=snapshot)
        try:
            actions = drain_outbox(self.repo, self.automation, result.track_id)
            from evidence_artifacts import cleanup
            finalization = self.repo.finalize(result.track_id, apply=True)
            housekeeping = cleanup(self.repo, expired=True)
            return replace(result, post_commit={'actions': actions, 'finalization':finalization,
                                               'expired_artifacts':housekeeping})
        except Exception as exc:
            # The delivery pivot remains successful if the worker or its ACK fails.
            return replace(result, post_commit={'status':'outbox_pending', 'error':str(exc)})

    def _deliver(self, request):
        request, manifest = normalize_request(request)
        tid = manifest.content['track_id']
        with self.repo.work_lock(tid):
            if self.repo.find(track_id=tid) is None:
                return WorkflowResult('track_absent', tid)
            show = load_metadata_snapshot(self.repo, tid)
            if request.title:
                require(request.title.casefold() in {s.casefold() for s in [show['identity']['title'], *show['identity'].get('aliases', [])]}, 'review_work_conflict')
            reconcile_completion(self.repo, tid)
            show = load_metadata_snapshot(self.repo, tid)
            plan = plan_target(show)
            if not plan.deliverable:
                return WorkflowResult(plan.phase, tid)
            pending = [op for op in show['operations'].values() if not op.get('committed') and op.get('status') in {'prepared','recovering','accepted'}]
            if pending:
                return WorkflowResult('recovery_required', tid, pending[0]['operation_id'])
            selection = self.validator.validate(manifest, show, request.policy)
            if selection.release is None:
                return WorkflowResult(selection.report['status'], tid, report=selection.report)
            release = selection.release
            opid = request.operation_id or hashlib.sha256(f'{tid}:{release.target.episode}:{release.info_hash}'.encode()).hexdigest()[:24]
            delivery = DeliveryRequest(tid, opid, release.info_hash, release.magnet, request.save_path, release.source_url, validation=release.permit)
            delivery.validate()
            op = {'operation_id':opid, 'track_id':tid, 'identity_revision':show['identity_revision'],
                  'info_hash':release.info_hash, 'episode':release.target.episode, 'kind':'regular',
                  'candidate_id':release.candidate_id, 'request':delivery.saved_request(), 'quality_policy':asdict(request.policy),
                  'review_path':str(manifest.path.resolve()), 'review_manifest':manifest.content, 'review_digest':hashlib.sha256(manifest.path.read_bytes()).hexdigest()}
            self.repo.command(tid, 'record_pending_operation', expected_revision=show['revision'], operation=op)
            saved = self.repo.find(track_id=tid)['operations'][opid]
            if saved.get('committed'):
                return WorkflowResult('already_accepted', tid, opid, receipt=saved.get('receipt'))
            return self._execute(delivery, selection.report)

    def _execute(self, delivery, report=None):
        tid, opid = delivery.track_id, delivery.operation_id
        try:
            delivery.authorize()
            preflight_delivery_context(self.client)
            accepted = self.client.submit(delivery).validate(delivery)
        except ClientFailure as exc:
            self.repo.command(tid, 'record_failed_operation', operation_id=opid, recovery=asdict(exc.recovery))
            return WorkflowResult('available_enqueue_failed', tid, opid, recovery=asdict(exc.recovery), report=report)
        except Exception as exc:
            failure = ClientFailure('submission_unverified', retryable=True)
            self.repo.command(tid, 'record_failed_operation', operation_id=opid, recovery=asdict(failure.recovery))
            return WorkflowResult('available_enqueue_failed', tid, opid, recovery=asdict(failure.recovery), report=report)
        accepted_dict = {**asdict(accepted), 'checked_at':now_iso()}
        try:
            commit_delivery(self.repo, tid, accepted_dict)
        except Exception:
            return WorkflowResult('accepted_receipt_commit_failed', tid, opid, receipt=accepted_dict,
                                  recovery=asdict(ClientFailure('accepted_receipt_commit_failed', retryable=True).recovery))
        return WorkflowResult('delivery_recorded', tid, opid, receipt=accepted_dict, report=report)

    def recover(self, operation_id, *, review=None, original_policy=None):
        result = self._recover(operation_id, review=review, original_policy=original_policy)
        result = self._finish(result)
        if result.status in {'recovered','already_accepted','delivery_recorded'}:
            from evidence_artifacts import cleanup
            try:
                op = self.repo.find(track_id=result.track_id)['operations'][operation_id]
                if op.get('review_path'):
                    cleanup(self.repo, review=op['review_path'])
            except Exception:
                pass  # expiry sweep retries housekeeping, acceptance stays durable
        return result

    def _recover(self, operation_id, *, review=None, original_policy=None):
        matches = [(s, s['operations'][operation_id]) for s in self.repo.read()['shows'] if operation_id in s['operations']]
        if not matches:
            return WorkflowResult('track_absent', None, operation_id)
        require(len(matches) == 1, 'operation_not_found')
        tid = matches[0][0]['track_id']
        with self.repo.work_lock(tid):
            show = self.repo.find(track_id=tid)
            if show is None:
                return WorkflowResult('track_absent', tid, operation_id)
            op = show['operations'][operation_id]
            if op.get('committed'):
                return WorkflowResult('already_accepted', tid, operation_id)
            # Accepted ledger entries can finish with the client completely offline.
            if op.get('receipt', {}).get('accepted') is True:
                commit_delivery(self.repo, tid, op['receipt'])
                return WorkflowResult('recovered', tid, operation_id, receipt=op['receipt'])
            require(show['lifecycle']['phase'] not in {'blocked','completed'}, 'track_not_deliverable')
            require(op['identity_revision'] == show['identity_revision'], 'operation_identity_conflict')
            delivery = DeliveryRequest(**op['request'])
            delivery.validate()
            try:
                preflight_delivery_context(self.client)
                evidence = self.client.inspect(op['info_hash'])
                require(evidence.info_hash == op['info_hash'], 'inspection_hash_mismatch')
                if evidence.verified:
                    accepted = asdict(receipt(delivery, 'already_present', evidence))
                    commit_delivery(self.repo, tid, accepted)
                    return WorkflowResult('recovered', tid, operation_id, receipt=accepted)
            except ClientFailure as exc:
                self.repo.command(tid, 'record_failed_operation', operation_id=operation_id, recovery=asdict(exc.recovery))
                return WorkflowResult('recovery_failed', tid, operation_id, recovery=asdict(exc.recovery))
            # Inspecting an accepted hash is read-only; a new add needs fresh validation.
            from dataclasses import replace
            from quality_review import recovery_policy, POLICY_FIELDS
            if review is None and (set(op.get('quality_policy') or {}) != POLICY_FIELDS or not op.get('review_path')):
                return WorkflowResult('re_review_required', tid, operation_id)
            policy = recovery_policy(op.get('quality_policy'), original_policy)
            manifest = ReviewManifest.load(Path(review or op['review_path']))
            require(manifest.content.get('track_id') == tid, 'review_work_conflict')
            review_digest = hashlib.sha256(manifest.path.read_bytes()).hexdigest()
            if review is None:
                require(review_digest == op['review_digest'], 'recovery_review_changed')
            selection = self.validator.validate(manifest, show, QualityPolicy(**policy))
            require(selection.release is not None and selection.release.info_hash == op['info_hash']
                    and selection.release.target.episode == op['episode']
                    and (not op.get('candidate_id') or selection.release.candidate_id == op['candidate_id']),
                    'recovery_validation_failed')
            if review is not None:
                self.repo.command(tid, 'record_operation_review', expected_revision=show['revision'],
                                  operation_id=operation_id, info_hash=op['info_hash'], episode=op['episode'],
                                  quality_policy=policy, review_path=str(manifest.path.resolve()),
                                  review_manifest=manifest.content, review_digest=review_digest)
            delivery = replace(delivery, validation=selection.release.permit)
            return self._execute(delivery, selection.report)
