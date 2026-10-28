"""Content-addressed file changes with explicit parent and ownership checks."""
from dataclasses import dataclass
from fruitfly_agent.improvement.contracts.components import ComponentFile
from fruitfly_agent.improvement.contracts.validation import relative_path
from fruitfly_agent.improvement.contracts.versions import content_hash, require_hash


@dataclass(frozen=True)
class FileChange:
    path: str
    before: str | None
    after: str | None

    def __post_init__(self):
        relative_path(self.path)
        for value in (self.before, self.after):
            if value is not None: require_hash(value)
        if self.before == self.after:
            raise ValueError('file change must add, replace, or remove content')


@dataclass(frozen=True)
class ChangeSet:
    component_id: str
    parent_document_id: str
    changes: tuple[FileChange, ...]

    def __post_init__(self):
        require_hash(self.parent_document_id)
        object.__setattr__(self, 'changes', tuple(self.changes))
        if not self.changes or len({c.path for c in self.changes}) != len(self.changes):
            raise ValueError('declare distinct nonempty file changes')

    def apply(self, document, artifacts):
        from dataclasses import replace
        if document.component_id != self.component_id or document.document_id != self.parent_document_id:
            raise ValueError('component change parent differs')
        files = {f.path: f.text for f in document.files}
        for change in self.changes:
            before = content_hash(files[change.path]) if change.path in files else None
            if before != change.before:
                raise ValueError('file change precondition differs')
            if change.after is None:
                files.pop(change.path)
            else:
                body = artifacts.read(change.after)
                text = body.decode('utf-8')
                if content_hash(text) != change.after:
                    raise ValueError('file change artifact differs')
                files[change.path] = text
        return replace(document, files=tuple(ComponentFile(k, v) for k, v in files.items()))
