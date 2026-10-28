"""Public components contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol, Literal
from fruitfly_agent.improvement.contracts.validation import identifier, relative_path, bounded
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash

@dataclass(frozen=True)
class ComponentFile:
    path: str
    text: str

    def __post_init__(self):
        relative_path(self.path)
        bounded(self.text, 120_000, empty=True)


@dataclass(frozen=True)
class ComponentDocument:
    component_id: str
    kind: str
    role: Literal['H', 'S', 'I']
    schema: str
    files: tuple[ComponentFile, ...]

    def __post_init__(self):
        for value in (self.component_id, self.kind, self.schema):
            identifier(value)
        if self.role not in {'H', 'S', 'I'}:
            raise ValueError('component axis must be H, S or I')
        object.__setattr__(self, 'files', tuple(sorted(self.files, key=lambda f: f.path)))
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError('component file paths must be distinct')

    @property
    def document_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class HarnessSnapshot:
    components: tuple[ComponentDocument, ...]

    def __post_init__(self):
        object.__setattr__(self, 'components', tuple(sorted(self.components, key=lambda c: c.component_id)))
        if not self.components or len({c.component_id for c in self.components}) != len(self.components):
            raise ValueError('a harness needs distinct registered components')

    @property
    def snapshot_id(self):
        return content_hash(canonical_json(asdict(self)))

    def component(self, component_id):
        try:
            return next(c for c in self.components if c.component_id == component_id)
        except StopIteration as exc:
            raise ValueError('unregistered component: ' + component_id) from exc

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {'components'}:
            raise ValueError('invalid harness snapshot')
        return cls(tuple(ComponentDocument(**{**c, 'files': tuple(ComponentFile(**f) for f in c['files'])})
                         for c in value['components']))


class ComponentAdapter(Protocol):
    def snapshot(self) -> ComponentDocument: ...
    def validate(self, document: ComponentDocument) -> None: ...


@dataclass(frozen=True)
class ComponentBinding:
    component_id: str
    kind: str
    key: str
    text: str

    def __post_init__(self):
        identifier(self.component_id)
        if self.kind not in {'prompt', 'artifact', 'configuration'} or self.kind in {'artifact', 'configuration'} and not self.key:
            raise ValueError('unsupported component publication binding')
        bounded(self.text, empty=True)


class CandidateBuilder(Protocol):
    def build(self, snapshot: HarnessSnapshot, *, destination: object) -> object: ...


class CandidateRuntime(Protocol):
    capabilities: frozenset[str]
    async def aclose(self) -> None: ...


class ActivationHost(Protocol):
    async def prepare(self, snapshot: HarnessSnapshot) -> CandidateRuntime: ...
    async def activate(self, runtime: CandidateRuntime, *, expected_version: str) -> None: ...

