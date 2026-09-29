"""JSON storage primitives shared by migration, commands and journals."""
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

class StateFileError(RuntimeError):
    pass

_LOCKS = {}
_GUARD = threading.Lock()
_HELD = threading.local()

@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _GUARD:
        local = _LOCKS.setdefault(str(path.resolve()).casefold(), threading.RLock())
    with local:
        key = str(path.resolve()).casefold()
        held = getattr(_HELD, 'paths', set())
        if key in held:
            yield
            return
        _HELD.paths = held | {key}
        try:
            with _os_lock(path):
                yield
        finally:
            _HELD.paths = held

@contextmanager
def _os_lock(path):
    with path.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

def read_json(path):
    path = Path(path)
    if not path.exists():
        return {'version': 2, 'shows': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or not isinstance(data.get('shows', []), list):
            raise ValueError('state must contain an object list')
        if not all(isinstance(show, dict) for show in data.get('shows', [])):
            raise ValueError('invalid tracking record')
        if data.get('version', 1) not in {1, 2}:
            raise ValueError('unsupported state version')
        return data
    except (OSError, ValueError, UnicodeError) as exc:
        raise StateFileError(f'追番状态文件无法读取，已保留原文件：{path}（{exc}）') from exc

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
        prefix=path.name + '.', suffix='.tmp', delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
