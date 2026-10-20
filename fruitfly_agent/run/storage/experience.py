"""Append attributed experience with explicit optimistic snapshot checks."""
import json
import os
from pathlib import Path
import tempfile

from fruitfly_agent.lab.improvement.api import entry_to_dict, entry_from_dict, experience_id
from fruitfly_agent.lab.algorithms.targets import StateSnapshot, SnapshotFile


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
