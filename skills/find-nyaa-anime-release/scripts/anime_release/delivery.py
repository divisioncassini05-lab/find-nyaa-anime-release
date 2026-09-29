"""Verified-release-only finalization with durable intent and exact-hash recovery."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from .models import VerifiedRelease, DeliveryReceipt, StateCommand, WorkflowError, TargetDecision
from .repository import StateRepository, require_record, handled
from .storage import atomic_json
from .evidence import timestamp

def verify(identity, target, selected, item, status, output_ready, *, reviewed_id=None, enqueue=False):
    from qbittorrent_submit import extract_btih
    from nyaa_client import nyaa_id_from_url
    from release_identity import EpisodeKind, normalize_season_number
    if status != 'found' or not output_ready or item is None or selected is None:
        raise WorkflowError('verification', 'release_not_verified')
    source_url = item.candidate.url
    candidate_id = nyaa_id_from_url(source_url)
    if enqueue and (not reviewed_id or candidate_id != nyaa_id_from_url(str(reviewed_id))):
        raise WorkflowError('verification', 'agent_review_required')
    parsed = item.identity
    if parsed.season and normalize_season_number(identity.season) != parsed.season:
        raise WorkflowError('verification', 'candidate_season_conflict')
    if target.episode is not None and parsed.kind == EpisodeKind.REGULAR and parsed.episode != target.episode:
        raise WorkflowError('verification', 'candidate_episode_conflict')
    if target.intent == 'latest_regular' and not target.latest_confirmed:
        raise WorkflowError('target', 'latest_not_confirmed')
    magnet = selected.get('magnet') or ''
    try:
        info_hash = extract_btih(magnet)
    except Exception as exc:
        raise WorkflowError('verification', 'magnet_incomplete') from exc
    if not candidate_id or not info_hash:
        raise WorkflowError('verification', 'magnet_incomplete')
    kind = 'regular' if parsed.kind == EpisodeKind.REGULAR and target.intent != 'season_batch' else 'collection'
    return VerifiedRelease(identity, target, str(candidate_id), selected['title'], magnet, info_hash,
        source_url, kind, json.dumps(selected, ensure_ascii=False))

def finalize(release, request, state_path, submit, *, client_options, create_record=None, completion=None, broadcast=None, evidence=()):
    if not isinstance(release, VerifiedRelease):
        raise WorkflowError('delivery', 'verified_release_required')
    if request.read_only:
        return {'status': 'not_attempted', 'ok': True, 'reason': 'read_only'}, None
    repo = StateRepository(state_path)
    identity = release.identity
    operation_id = hashlib.sha256(f'{identity.track_id}:{identity.revision}:{release.info_hash}'.encode()).hexdigest()
    journal = Path(state_path).parent / '.delivery-journal' / (operation_id + '.json')
    with repo.work_lock(identity.track_id):
        from qbittorrent_submit import extract_btih
        from nyaa_client import nyaa_id_from_url
        if (release.target.identity != identity
            or extract_btih(release.magnet) != release.info_hash
            or str(nyaa_id_from_url(release.source_url)) != release.candidate_id):
            raise WorkflowError('delivery', 'verified_candidate_conflict')
        state = repo.read()
        record = next((s for s in state['shows'] if s['track_id'] == identity.track_id), None)
        if record is not None:
            if record['identity_revision'] != identity.revision or record.get('season') != identity.season:
                raise WorkflowError('delivery', 'identity_revision_conflict', False, (), 'repeat_identity_verification')
            if record.get('status') == 'completed' and release.kind == 'regular' and release.target.intent in {'latest_regular', 'next_tracked'}:
                return {'status': 'not_attempted', 'ok': True, 'reason': 'season_completed'}, None
            if release.kind == 'regular' and release.target.intent in {'latest_regular', 'next_tracked'} and (release.target.episode or 0) <= handled(record):
                return {'status': 'not_attempted', 'ok': True, 'reason': 'latest_already_handled'}, None
        # Explicit redelivery is allowed, but is retrieval-only with respect to
        # watch state, including metadata fields and revisions.
        persist_receipt = not (record is not None and release.kind == 'regular'
            and (release.target.episode or 0) <= handled(record))
        operation = {'operation_id': operation_id, 'info_hash': release.info_hash,
            'candidate_id': release.candidate_id, 'episode': release.target.episode,
            'kind': release.kind, 'identity_revision': identity.revision,
            'status': 'prepared', 'created_at': timestamp()}
        previous = None
        if journal.exists():
            try:
                previous = json.loads(journal.read_text(encoding='utf-8'))
            except (ValueError, OSError) as exc:
                raise WorkflowError('delivery', 'journal_unreadable', False, (), 'inspect_delivery_journal') from exc
        if previous and any(previous.get(key) != operation[key] for key in
            ('operation_id', 'info_hash', 'episode', 'kind', 'identity_revision')):
            raise WorkflowError('delivery', 'journal_target_conflict', False, (previous,), 'inspect_delivery_journal')
        if not previous:
            atomic_json(journal, operation)
        try:
            if request.enqueue:
                # The existing profile-level submitter checks the exact hash under
                # its own interprocess lock BEFORE any send, including on recovery.
                result = submit(release.magnet, source_url=release.source_url, **client_options)
                from qbittorrent_submit import SUCCESS_STATUSES
                accepted = bool(result.get('ok') and result.get('status') in SUCCESS_STATUSES)
            else:
                result = {'status': 'link_delivered', 'ok': True, 'info_hash': release.info_hash}
                accepted = True
        except Exception:
            # Keep prepared intent; no advance. Next run rechecks the client hash.
            raise
        receipt = DeliveryReceipt(operation_id, identity.track_id, release.info_hash,
            result.get('status', 'unknown'), accepted, timestamp(), json.dumps(result, ensure_ascii=False))
        try:
            atomic_json(journal, {**operation, 'status': 'accepted' if accepted else 'failed', 'receipt': asdict(receipt)})
        except OSError as exc:
            raise WorkflowError('state_commit' if accepted else 'delivery',
                'accepted_receipt_commit_failed' if accepted else 'failed_receipt_commit_failed',
                True, (asdict(receipt),), 'recover_same_hash_receipt') from exc
        if accepted and persist_receipt and (record is not None or create_record is not None):
            commands = [] if record else [StateCommand(identity.track_id, 'create', fields=create_record)]
            commands.append(StateCommand(identity.track_id, 'operation', expected_identity_revision=identity.revision,
                                         fields={'operation': previous or operation}))
            commands.append(StateCommand(identity.track_id, 'delivery_success',
                expected_identity_revision=identity.revision, receipt=receipt))
            if broadcast:
                commands.append(StateCommand(identity.track_id, 'broadcast',
                    expected_identity_revision=identity.revision, fields=broadcast))
            if completion and completion.get('confirmed') and release.kind == 'regular' and release.target.episode == completion.get('final_episode'):
                commands.append(StateCommand(identity.track_id, 'completed', expected_identity_revision=identity.revision,
                                              fields={'completion': completion}))
            if evidence:
                commands.append(StateCommand(identity.track_id, 'metadata_bind',
                    expected_identity_revision=identity.revision, fields={'evidence':[asdict(e) for e in evidence]}))
            try:
                repo.commit(*commands)
            except (OSError, WorkflowError) as exc:
                raise WorkflowError('state_commit', 'accepted_state_commit_failed', True,
                    (asdict(receipt),), 'recover_same_hash_receipt') from exc
        return result, receipt
