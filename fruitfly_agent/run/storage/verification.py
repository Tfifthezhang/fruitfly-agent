"""Durable one-use verification claims; uncertain work remains consumed."""
import fcntl
import json
import os
from pathlib import Path
import tempfile
import re


class VerificationUseStore:
    def __init__(self, path):
        self.path = Path(path)

    def claim(self, source_id, maximum):
        if (not isinstance(source_id, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', source_id)
                or type(maximum) is not int or maximum < 1):
            raise ValueError('invalid verification use claim')
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('verification ledger cannot contain symlinks')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix('.lock')
        if lock_path.is_symlink():
            raise ValueError('verification lock cannot be a symlink')
        with lock_path.open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            value = json.loads(self.path.read_text()) if self.path.exists() else {'schema_version': 1, 'uses': {}}
            if set(value) != {'schema_version', 'uses'} or value['schema_version'] != 1 or not isinstance(value['uses'], dict):
                raise ValueError('invalid verification ledger')
            count = value['uses'].get(source_id, 0)
            if type(count) is not int or count < 0 or count >= maximum:
                raise ValueError('independent verification use limit exhausted; provide new material')
            value['uses'][source_id] = count + 1
            fd, name = tempfile.mkstemp(prefix='.verification-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(value, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.path)
            finally:
                Path(name).unlink(missing_ok=True)

    def remaining(self, source_id, maximum):
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('verification ledger cannot contain symlinks')
        value = json.loads(self.path.read_text()) if self.path.exists() else {'schema_version': 1, 'uses': {}}
        if set(value) != {'schema_version', 'uses'} or value['schema_version'] != 1 or not isinstance(value['uses'], dict):
            raise ValueError('invalid verification ledger')
        count = value['uses'].get(source_id, 0)
        if type(count) is not int or count < 0:
            raise ValueError('invalid verification use count')
        return max(0, maximum - count)
