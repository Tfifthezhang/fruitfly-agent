"""Atomic, attributed working files independent of task success."""
from pathlib import Path
import fcntl
import json
import os
import tempfile
from fruitfly_agent.improvement.contracts.validation import identifier
from fruitfly_agent.improvement.contracts.versions import require_hash


class WorkProductStore:
    def __init__(self, root, artifacts, *, producer='parent', read_all=True, on_publish=None):
        identifier(producer)
        if Path(root).is_symlink():
            raise ValueError("work product root must not be a symlink")
        self.root, self.artifacts = Path(root).resolve(), artifacts
        self.producer, self.read_all = producer, read_all
        self.on_publish = on_publish

    def writer(self, producer):
        return type(self)(self.root, self.artifacts, producer=producer, read_all=False, on_publish=self.on_publish)

    def _safe(self):
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('work products cannot traverse symlinks')

    def has_products(self):
        self._safe()
        pattern = '*/*.json' if self.read_all else self.producer + '/*.json'
        return next(self.root.glob(pattern), None) is not None

    def entries(self):
        self._safe()
        rows = []
        for path in sorted(self.root.glob('*/*.json')):
            if not self.read_all and path.parent.name != self.producer:
                continue
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError('invalid work product locator')
            row = json.loads(path.read_text())
            self._validate(row, path.parent.name, path.stem)
            if row['producer'] != path.parent.name or row['name'] != path.stem:
                raise ValueError('work product identity mismatch')
            if self.read_all or row['producer'] == self.producer:
                rows.append(row)
        return rows

    @staticmethod
    def _validate(row, producer, name):
        if (not isinstance(row, dict) or set(row) != {'producer', 'name', 'revision', 'artifact_id', 'previous', 'characters'}
                or row['producer'] != producer or row['name'] != name
                or type(row['revision']) is not int or row['revision'] < 1
                or type(row['characters']) is not int or not 1 <= row['characters'] <= 120000
                or (row['previous'] is None) != (row['revision'] == 1)):
            raise ValueError('invalid work product revision')
        identifier(producer); identifier(name); require_hash(row['artifact_id'])
        if row['previous'] is not None:
            require_hash(row['previous'])

    def save(self, name, content, revision):
        identifier(name)
        if type(revision) is not int or revision < 0:
            raise ValueError('expected_revision must be a nonnegative integer')
        if not isinstance(content, str) or not content.strip() or len(content) > 120000:
            raise ValueError('work product text must contain 1..120000 characters')
        self._safe()
        directory = self.root / self.producer
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            raise ValueError('invalid work product producer')
        target = directory / (name + '.json')
        lock_path = directory / '.lock'
        if lock_path.is_symlink():
            raise ValueError('invalid work product lock')
        with lock_path.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if target.is_symlink():
                raise ValueError('invalid work product locator')
            current = json.loads(target.read_text()) if target.exists() else None
            if current is not None:
                self._validate(current, self.producer, name)
                self.artifacts.read_text(current["artifact_id"])
            if (current['revision'] if current else 0) != revision:
                raise ValueError('work product revision conflict; read the current revision before editing')
            reference = self.artifacts.put_text(content).artifact_id
            row = {'producer': self.producer, 'name': name, 'revision': revision + 1,
                   'artifact_id': reference, 'previous': self.artifacts.put_text(json.dumps(current)).artifact_id if current else None, 'characters': len(content)}
            descriptor, name = tempfile.mkstemp(prefix='.work-', dir=directory)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, 'w') as stream:
                    json.dump(row, stream); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, target)
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                temporary.unlink(missing_ok=True)
            receipt = {k: v for k, v in row.items() if k != 'previous'}
            receipt['manifest_id'] = self.artifacts.put_text(json.dumps(row)).artifact_id
            if self.on_publish is not None:
                self.on_publish(receipt)
            return receipt

    def read(self, producer, name, revision):
        identifier(producer); identifier(name)
        if not self.read_all and producer != self.producer:
            raise ValueError('work product is outside the reader grant')
        if type(revision) is not int or revision < 1:
            raise ValueError('work product revision must be positive')
        row = next((r for r in self.entries() if r['producer'] == producer and r['name'] == name), None)
        while row and row['revision'] != revision:
            prior = row['previous']
            expected = row['revision'] - 1
            row = json.loads(self.artifacts.read_text(prior)) if prior else None
            if row is not None:
                self._validate(row, producer, name)
                if row['revision'] != expected:
                    raise ValueError('invalid work product history')
        if row is None:
            raise ValueError('unknown work product revision')
        return self.artifacts.read_text(row['artifact_id'])
