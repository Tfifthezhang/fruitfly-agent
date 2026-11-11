"""Immutable partial results discoverable independently of final stage success."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from fruitfly_agent.improvement.contracts.organization import OrganizationPart
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash


class OrganizationPartStore:
    def __init__(self, directory, artifacts):
        if Path(directory).is_symlink():
            raise ValueError('organization part directory must not be a symlink')
        self.directory, self.artifacts = Path(directory).resolve(), artifacts
        package = Path(__file__).resolve().parents[2]
        identities = [(p.relative_to(package).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(package.rglob('*')) if p.is_file() and not p.is_symlink()
            and (p.suffix == '.py' or p.name == 'defaults.yaml') and '__pycache__' not in p.parts]
        self.implementation_id = content_hash(canonical_json(identities))

    def _safe(self):
        if any(p.is_symlink() for p in (self.directory, *self.directory.parents)):
            raise ValueError('organization part store cannot traverse symlinks')

    def entries(self):
        self._safe()
        entries = []
        for path in sorted(self.directory.glob('*.json')):
            reference = 'sha256:' + path.stem
            require_hash(reference)
            if path.is_symlink() or json.loads(path.read_text()) != {'artifact_id': reference}:
                raise ValueError('invalid organization part locator')
            entries.append(reference)
        return tuple(entries)

    def read(self, reference):
        require_hash(reference)
        return OrganizationPart.from_dict(json.loads(self.artifacts.read_bytes(reference)))

    def save(self, part):
        if not isinstance(part, OrganizationPart):
            raise TypeError('organization part store requires a validated part')
        reference = self.artifacts.put_bytes(canonical_json(part.to_dict()).encode()).artifact_id
        self._safe()
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (reference[7:] + '.json')
        data = canonical_json({'artifact_id': reference})
        descriptor, name = tempfile.mkstemp(prefix='.part-', dir=self.directory)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or target.read_text() != data:
                    raise ValueError('organization part locator changed')
        finally:
            temporary.unlink(missing_ok=True)
        return reference
