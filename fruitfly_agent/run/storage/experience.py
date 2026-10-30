"""Append attributed experience with explicit optimistic snapshot checks."""
import json
import os
from pathlib import Path
import tempfile
import re

from fruitfly_agent.lab.improvement.api import entry_to_dict, entry_from_dict, experience_id
from fruitfly_agent.improvement.contracts.versions import StateSnapshot, SnapshotFile


class ExperienceStore:
    def __init__(self, path):
        self.path = Path(path)

    def snapshot(self):
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('experience store cannot be a symlink')
        if not self.path.exists():
            return ()
        value = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or set(value) != {'schema_version', 'entries'} or value['schema_version'] != 1:
            raise ValueError('invalid experience store')
        entries = tuple(entry_from_dict(v) for v in value['entries'])
        if len({e.entry_id for e in entries}) != len(entries):
            raise ValueError('duplicate experience identities')
        return entries

    def freeze(self):
        entries = self.snapshot()
        # Empty libraries have no learning state to restore. A populated library
        # is captured verbatim with the same schema used by commit().
        files = () if not entries else (SnapshotFile('.fruitfly/improvement/experience.json',
            json.dumps({'schema_version': 1, 'entries': [entry_to_dict(e) for e in entries]}, ensure_ascii=False)),)
        return StateSnapshot(files, roots=('.fruitfly/improvement/experience.json',))

    def commit(self, entries, *, expected_snapshot):
        current = self.snapshot()
        if experience_id(current) != expected_snapshot:
            raise ValueError('experience snapshot changed before commit')
        merged = {e.entry_id: e for e in current}
        for entry in entries:
            if entry.entry_id in merged and merged[entry.entry_id] != entry:
                raise ValueError('experience identity already has different contents')
            merged[entry.entry_id] = entry
        values = tuple(merged.values())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.experience-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'schema_version': 1, 'entries': [entry_to_dict(e) for e in values]}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
        return experience_id(values)

    def pending_path(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', job_id):
            raise ValueError('invalid pending experience job')
        path = self.path.parent / 'experience-pending' / (job_id + '.json')
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('pending experience cannot contain symlinks')
        return path

    def stage(self, job_id, entries, *, expected_snapshot):
        if experience_id(self.snapshot()) != expected_snapshot:
            raise ValueError('experience snapshot changed before staging')
        path = self.pending_path(job_id)
        value = {'schema_version': 1, 'job_id': job_id, 'initial_snapshot': expected_snapshot,
                 'status': 'pending', 'entries': [entry_to_dict(e) for e in entries]}
        if path.exists():
            if self.read_pending(job_id) != value:
                raise ValueError('pending experience identity already has different contents or a review')
            return
        self.write_pending(path, value)

    def write_pending(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def pending(self):
        directory = self.path.parent / 'experience-pending'
        if not directory.exists():
            return ()
        result = []
        for path in sorted(directory.glob('*.json')):
            value = self.read_pending(path.stem)
            if value['status'] == 'pending':
                result.append(value)
        return tuple(result)

    def read_pending(self, job_id):
        value = json.loads(self.pending_path(job_id).read_text())
        if (not isinstance(value, dict) or set(value) != {'schema_version', 'job_id', 'initial_snapshot', 'status', 'entries'}
                or value['schema_version'] != 1 or value['job_id'] != job_id
                or value['status'] not in {'pending', 'committed', 'rejected'}):
            raise ValueError('invalid pending experience record')
        tuple(entry_from_dict(v) for v in value['entries'])
        return value

    def review(self, job_id, action):
        value = self.read_pending(job_id)
        if action not in {'commit', 'reject'} or value['status'] != 'pending':
            raise ValueError('only pending experience can be committed or rejected')
        if action == 'commit':
            entries = tuple(entry_from_dict(v) for v in value['entries'])
            current = self.snapshot()
            # Reconcile a crash after the library commit but before review status.
            if not entries or not all(entry in current for entry in entries):
                self.commit(entries, expected_snapshot=value['initial_snapshot'])
        value['status'] = 'committed' if action == 'commit' else 'rejected'
        self.write_pending(self.pending_path(job_id), value)
        return value['status']
