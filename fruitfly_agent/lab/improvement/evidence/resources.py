"""Read-only artifact references avoid copying all task logs into editor memory."""
from . import EvidenceWorkspace
from ..contracts.validation import relative_path


class ReferenceWorkspace(EvidenceWorkspace):
    def __init__(self, *, artifacts, references, **kwargs):
        super().__init__(**kwargs)
        self.artifacts, self.references = artifacts, dict(references)
        for path in self.references:
            relative_path(path)
            if path in self.files or path.startswith('harness/'):
                raise ValueError('evidence reference conflicts with a workspace path')

    def paths(self):
        return tuple(sorted((*self.files, *self.references)))

    def read(self, path):
        relative_path(path)
        if path in self.references:
            reference = self.references[path]
            data = self.artifacts.read(reference)
            self.record('editor-read', path=path, artifact_id=reference)
            return data
        return super().read(path)
