"""Disposable discovery metadata; admission always validates the actual Session."""
from __future__ import annotations

from dataclasses import asdict, replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable

from fruitfly_agent.interactive import ResumableSession


def _fingerprint(path: Path) -> list[int]:
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def _locked(path: Path) -> bool:
    try:
        with path.with_suffix(path.suffix + '.lock').open('rb') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
    except FileNotFoundError:
        pass
    return False


class SessionIndex:
    """Cache only stable unlocked snapshots, never live writer availability."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def discover(self, path: Path, scan: Callable[[], ResumableSession | None]) -> ResumableSession | None:
        fingerprint = _fingerprint(path)
        target = self.directory / (hashlib.sha256(os.fsencode(path)).hexdigest() + '.json')
        hit = False
        result = None
        try:
            cached = json.loads(target.read_text())
            if cached['fingerprint'] == fingerprint and cached['schema_version'] == 1:
                value = cached['session']
                if value is not None:
                    result = ResumableSession(**value)
                    if (result.path != str(path) or type(result.available) is not bool
                            or any(type(getattr(result, k)) is not int or getattr(result, k) < 0
                                   for k in ('message_count', 'user_turns'))
                            or not isinstance(result.modified_at, (int, float))
                            or any(not isinstance(getattr(result, k), str) for k in
                                   ('path', 'profile', 'model', 'prompt_label', 'prompt_hash', 'reason', 'title'))):
                        raise ValueError('invalid cached session metadata')
                hit = True
        except (OSError, ValueError, TypeError, KeyError):
            pass
        if not hit:
            result = scan()
            if (_fingerprint(path) == fingerprint and not _locked(path)
                    and (result is None or result.available)):
                self._save(target, {'schema_version': 1, 'fingerprint': fingerprint,
                    'session': asdict(result) if result is not None else None})
        if result is not None and _locked(path):
            return replace(result, available=False, reason='session is locked by another process')
        return result

    def _save(self, target: Path, value: dict) -> None:
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix='.index-', dir=self.directory)
            temporary = Path(name)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, target)
        except (OSError, ValueError):
            pass  # An optional cache cannot prevent discovery.
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
