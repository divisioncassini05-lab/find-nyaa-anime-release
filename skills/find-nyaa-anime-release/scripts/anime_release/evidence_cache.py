"""Cache raw evidence only, isolated by provider, binding and identity revision."""
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from .models import MetadataEvidence
from .storage import atomic_json

def key(identity, provider, entry_id):
    raw = json.dumps([identity.track_id, identity.revision, identity.season, identity.part, provider, str(entry_id)])
    return hashlib.sha256(raw.encode()).hexdigest()

def path_for(root, identity, provider, entry_id):
    return Path(str(root) + '.evidence-v2') / (key(identity, provider, entry_id) + '.json')

def read(root, identity, provider, entry_id):
    try:
        saved = json.loads(path_for(root, identity, provider, entry_id).read_text(encoding='utf-8'))
        if saved['expires_at'] <= time.time():
            return None
        evidence = saved['evidence']
        evidence['titles'] = tuple(evidence['titles'])
        result = MetadataEvidence(**evidence)
        if result.provider != provider or result.entry_id != str(entry_id) or result.identity_revision != identity.revision:
            return None
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return None

def write(root, identity, evidence):
    atomic_json(path_for(root, identity, evidence.provider, evidence.entry_id),
                {'expires_at': time.time() + 1800, 'evidence': asdict(evidence)})
