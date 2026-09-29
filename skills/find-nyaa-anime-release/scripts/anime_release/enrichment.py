"""Bounded provider enrichment. Returns evidence/repair proposals, never writes state."""
import copy
import json
from . import evidence_cache
from .evidence import from_raw, validate, unique_repair
from .models import WorkflowError

def enrich(resolved, timeout, cache_path, refresh_cache, today):
    from .providers import anilist_media_request, anilist_request, bangumi_request, media_to_resolved
    from .metadata import merge_resolved
    from http_transport import error_code
    identity = resolved.work_identity
    assert identity is not None
    if resolved.status == 'FINISHED' and resolved.completion.get('confirmed'):
        return resolved, 'retained_completion'
    base = copy.deepcopy(resolved)
    binding = resolved.anilist_id
    try:
        evidence = next((e for e in resolved.evidence if e.provider == 'anilist' and e.entry_id == str(binding)), None)
        if evidence is None:
            evidence = evidence_cache.read(cache_path, identity, 'anilist', binding) if binding and not refresh_cache else None
        hit = evidence is not None
        if evidence is None and binding:
            payload = anilist_media_request(binding, timeout).get('data', {}).get('Media')
            if not payload:
                raise WorkflowError('metadata', 'provider_entry_missing')
            evidence = from_raw('anilist', payload, identity.revision)
        if evidence is None:
            # Discovery without a historical binding needs source verification,
            # not a two-provider correction of a nonexistent binding.
            from .providers import resolve_title
            status, found = resolve_title(identity.title, timeout, today)
            if status == 'resolved' and found is not None and found.evidence:
                evidence = next((e for e in found.evidence if e.provider == 'anilist'), None)
                binding = found.anilist_id
            if evidence is None:
                return base, 'unavailable'
        validate(identity, evidence)
        if evidence.entry_id != str(binding):
            raise WorkflowError('metadata', 'binding_response_mismatch')
    except WorkflowError as conflict:
        candidates = []
        if resolved.official_identity_evidence is not None:
            candidates.append(resolved.official_identity_evidence)
        try:
            query = identity.title
            if identity.season and not any(c.isdigit() for c in query[-12:]):
                query = f'{query} Season {int(identity.season[1:])}'
            for raw in anilist_request(query, timeout).get('data', {}).get('Page', {}).get('media', []):
                candidates.append(from_raw('anilist', raw, identity.revision))
            for raw in bangumi_request(query, timeout).get('data', []):
                candidates.append(from_raw('bangumi', raw, identity.revision))
            proposal = unique_repair(identity, candidates)
            if 'anilist' not in proposal:
                raise WorkflowError('metadata', 'primary_binding_unverified', False,
                    tuple(proposal.values()), 'review_independent_identity_evidence')
        except (WorkflowError, OSError, ValueError, KeyError, TypeError) as repair_error:
            base.identity_conflicts = list(conflict.evidence) or [{'reasons': [conflict.code]}]
            base.stage_errors.append(repair_error.as_dict() if isinstance(repair_error, WorkflowError)
                else WorkflowError('metadata', error_code(repair_error), False, (), 'inspect_provider_transport').as_dict())
            return base, 'identity_conflict'
        base.repair_proposal = proposal
        base.anilist_id = proposal['anilist']['entry_id']
        if 'bangumi' in proposal:
            base.bangumi_id = proposal['bangumi']['entry_id']
        evidence = next(e for e in candidates if e.provider == 'anilist' and e.entry_id == str(base.anilist_id))
        hit = False
    except (OSError, ValueError, KeyError, TypeError) as exc:
        from .transport import MetadataTransportError
        if isinstance(exc, MetadataTransportError):
            base.stage_errors.append(exc.detail.as_dict())
            return base, 'unavailable'
        code = error_code(exc)
        base.stage_errors.append(WorkflowError('metadata', code, code == 'timeout', (),
            'request_approved_execution_context' if code == 'permission_denied' else 'inspect_provider_transport').as_dict())
        return base, 'unavailable'
    from dataclasses import replace
    evidence = replace(evidence, identity_revision=identity.revision)
    fresh, _ = media_to_resolved(identity.title, json.loads(evidence.payload_json), today)
    fresh.work_identity = identity
    fresh.evidence = (evidence,)
    result = merge_resolved(base, fresh)
    result.work_identity = identity
    result.evidence = (evidence,)
    result.repair_proposal = base.repair_proposal
    if not result.identity_conflicts:
        evidence_cache.write(cache_path, identity, evidence)
    return result, 'repair_proposed' if result.repair_proposal else 'hit' if hit else 'miss'
