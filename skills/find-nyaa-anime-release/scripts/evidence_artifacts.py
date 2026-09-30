"""Owned temporary evidence: bounded output paths and reference-aware cleanup.

Only indexed files below the evidence root can ever be removed. State, receipts,
external input files and artifacts referenced by uncommitted operations are excluded.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import uuid
import time
from runtime_paths import DEFAULT_STATE
from anime_release.storage import atomic_json, file_lock


def root(state=DEFAULT_STATE):
    return Path(state).resolve().parent / '.cache' / 'evidence'


def _inside(path, base):
    return path != base and path.is_relative_to(base)


def new_workspace(state=DEFAULT_STATE):
    base = root(state)
    path = base / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:12])
    path.mkdir(parents=True, exist_ok=False)
    atomic_json(path / '.run.json', {'kind':'watch-evidence-run', 'state':str(Path(state).resolve())})
    return path


def output_path(path, state=DEFAULT_STATE):
    path = Path(path).expanduser()
    if not path.is_absolute() or path.resolve().parent == Path(DEFAULT_STATE).resolve().parent.parent:
        # A bare output name is a scratch artifact, never a file in Download.
        if '..' in path.parts:
            raise ValueError('evidence_output_parent_traversal')
        path = root(state) / 'scratch' / datetime.now().strftime('%Y%m%d') / path.name
    return path.resolve()


def input_path(path, state=DEFAULT_STATE):
    path = Path(path).expanduser()
    if path.is_file():
        return path.resolve()
    # Compatibility for callers using the same bare name after output redirection.
    if not path.is_absolute() or path.parent.resolve() == Path(DEFAULT_STATE).resolve().parent.parent:
        candidates = list((root(state) / 'scratch').glob('*/' + path.name))
        if len(candidates) == 1:
            return candidates[0].resolve()
        if len(candidates) > 1:
            raise ValueError('ambiguous_artifact_path_use_returned_output_path')
    return path.resolve()


def _owner(path, state):
    base = root(state).resolve()
    path = path.resolve()
    if not _inside(path, base):
        return None
    for parent in path.parents:
        if parent == base:
            break
        if (parent / '.run.json').is_file():
            return parent
    return path.parent


def register(path, state=DEFAULT_STATE):
    path = Path(path).resolve()
    owner = _owner(path, state)
    if owner is None:
        return
    base = root(state)
    with file_lock(base / '.artifacts.lock'):
        index = owner / '.artifacts.json'
        data = json.loads(index.read_text(encoding='utf-8')) if index.exists() else {'files':[]}
        relative = str(path.relative_to(owner))
        if relative not in data['files']:
            data['files'].append(relative)
        atomic_json(index, data)


def _paths(value, base):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'review_path','detail_report','torrent_path'} and isinstance(item,str):
                p = Path(item)
                found.add((p if p.is_absolute() else base / p).resolve())
            elif key == 'listing_reports' and isinstance(item,list):
                for text in item:
                    if isinstance(text,str):
                        p = Path(text); found.add((p if p.is_absolute() else base / p).resolve())
            else:
                found.update(_paths(item,base))
    elif isinstance(value,list):
        for item in value:
            found.update(_paths(item,base))
    return found


def cleanup(repo, *, review=None, run=None, expired=False):
    base = root(repo.path).resolve()
    if not base.is_dir():
        return {'deleted':0, 'retained':0}
    deleted = retained = 0
    # State lock prevents preparing a delivery while its inputs are being removed.
    with file_lock(repo.path.with_suffix(repo.path.suffix + '.lock')), file_lock(base / '.artifacts.lock'):
        state = repo.read()
        protected = set()
        pending_without_paths = False
        for show in state['shows']:
            for operation in show.get('operations',{}).values():
                if not operation.get('committed'):
                    refs = _paths(operation,base)
                    protected.update(refs)
                    pending_without_paths |= not bool(refs)
        if pending_without_paths:
            return {'deleted':0, 'retained':'pending_operation_without_paths'}
        targets = set()
        owner = None
        if review:
            review = input_path(review,repo.path)
            if review.is_file():
                targets.add(review)
                targets.update(_paths(json.loads(review.read_text(encoding='utf-8-sig')), review.parent))
                owner = _owner(review,repo.path)
                if owner and not (owner / '.run.json').is_file():
                    owner = None  # shared scratch directory: delete only review dependencies
        if run:
            owner = Path(run).resolve()
            if not _inside(owner,base) or not (owner / '.run.json').is_file():
                raise ValueError('cleanup_requires_owned_run')
        for index in list(base.rglob('.artifacts.json')):
            if index.is_symlink() or not _inside(index.resolve(),base):
                continue
            data = json.loads(index.read_text(encoding='utf-8'))
            remaining = []
            for name in data['files']:
                lexical = index.parent / name
                path = lexical.resolve()
                if lexical.is_symlink() or not _inside(path,index.parent.resolve()) or not _inside(path,base):
                    remaining.append(name); retained += 1; continue
                if not path.exists():
                    continue
                requested = path in targets or owner is not None and _inside(path,owner)
                stale = expired and time.time() - path.stat().st_mtime > 48 * 3600
                if path in protected or not (requested or stale):
                    remaining.append(name); retained += 1; continue
                # Leave everything in a run alone when another operation needs it.
                run_owner = _owner(path,repo.path)
                if run_owner and (run_owner / '.run.json').is_file() and any(_inside(p,run_owner) for p in protected):
                    remaining.append(name); retained += 1; continue
                path.unlink()
                deleted += 1
            if remaining:
                atomic_json(index, {'files':remaining})
            else:
                index.unlink()
                marker = index.parent / '.run.json'
                if marker.is_file() and set(index.parent.iterdir()) == {marker}:
                    marker.unlink()
                if not any(index.parent.iterdir()):
                    index.parent.rmdir()
        # A no-results run may have created a directory but no evidence files.
        for marker in list(base.glob('*/.run.json')):
            folder = marker.parent.resolve()
            if marker.is_symlink() or not _inside(folder,base):
                continue
            ended = owner == folder
            stale = expired and time.time() - marker.stat().st_mtime > 48 * 3600
            if (ended or stale) and set(folder.iterdir()) == {marker}:
                marker.unlink()
                folder.rmdir()
    return {'deleted':deleted, 'retained':retained}


def collect_expired(state=DEFAULT_STATE):
    from watch_v3.store import StateRepository
    try:
        return cleanup(StateRepository(state), expired=True)
    except (OSError,ValueError,KeyError,RuntimeError):
        # Artifact housekeeping must never turn accepted delivery into a failure.
        return {'status':'cleanup_pending'}
