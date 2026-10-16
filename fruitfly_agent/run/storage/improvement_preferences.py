"""Workspace-local job preferences; never part of runtime or candidate identity."""
import hashlib
import json
from pathlib import Path
import os
import tempfile


class ImprovementPreferences:
    def __init__(self, workspace: Path, scope: str):
        root = workspace.resolve()
        self.path = root / '.fruitfly/improvement/preferences' / (hashlib.sha256(scope.encode()).hexdigest() + '.json')
        if not self.path.resolve().is_relative_to(root):
            raise ValueError('improvement preferences must stay inside the workspace')

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or any(not isinstance(row, dict) or
                    not isinstance(row.get('method'), str) or not isinstance(row.get('parameters'), dict)
                    for row in value.values()):
                return {}
            return value
        except (OSError, ValueError):
            return {}

    def save(self, values):
        # Recheck relocation before writing, including newly created parent symlinks.
        root = self.path.parents[3]
        if not self.path.resolve().is_relative_to(root):
            raise ValueError('improvement preferences must stay inside the workspace')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix='.preferences-')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(values, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
