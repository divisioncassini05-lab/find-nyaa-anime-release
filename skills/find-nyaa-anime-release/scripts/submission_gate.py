"""Process-local proof of validation, shared by every supported add transport.

This is an API invariant, not a sandbox against code modifying this module.
Serialized reports and caller-constructed objects never constitute permission.
"""
import hashlib
import json
import threading
import weakref


class ValidationRequired(ValueError):
    pass


class SubmissionPermit:
    __slots__ = ('__weakref__',)

    def __deepcopy__(self, memo):
        return self


_issued = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def _issue(info_hash, candidate_id, source_url, policy, review_digest, detail_digest):
    """Internal validator boundary; never exposed by a CLI or JSON deserializer."""
    if not (info_hash and candidate_id and source_url and policy and review_digest and detail_digest):
        raise ValidationRequired('validated_submission_required')
    permit = SubmissionPermit()
    binding = dict(info_hash=info_hash.lower(), candidate_id=str(candidate_id),
                   source_url=source_url, policy=policy, review_digest=review_digest,
                   detail_digest=detail_digest)
    # Store an immutable snapshot; changing an input dictionary cannot change it.
    with _lock:
        _issued[permit] = json.dumps(binding, sort_keys=True, ensure_ascii=False)
    return permit


def require(permit, info_hash, source_url=None):
    with _lock:
        value = _issued.get(permit) if isinstance(permit, SubmissionPermit) else None
    if value is None:
        raise ValidationRequired('validated_submission_required')
    binding = json.loads(value)
    if binding['info_hash'] != (info_hash or '').lower() or (
            source_url is not None and source_url != binding['source_url']):
        raise ValidationRequired('validated_submission_mismatch')
    return binding


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
