"""Durable research activities. Quality observations never control readiness."""
from dataclasses import asdict, dataclass, field
from typing import Protocol
from .tasks import Resource
from .validation import identifier
from .versions import canonical_json, content_hash


class UnresolvedActivity(RuntimeError):
    """An external effect may still be running; its intent must remain unresolved."""


@dataclass(frozen=True)
class ActivitySpec:
    kind: str
    implementation_id: str
    inputs: tuple[Resource, ...] = ()
    parameters: dict = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()

    def __post_init__(self):
        identifier(self.kind)
        identifier(self.implementation_id)
        object.__setattr__(self, 'inputs', tuple(self.inputs))
        object.__setattr__(self, 'dependencies', tuple(self.dependencies))
        if len({r.path for r in self.inputs}) != len(self.inputs):
            raise ValueError('activity inputs require distinct paths')
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError('activity dependencies must be distinct')
        for value in self.dependencies:
            identifier(value)
        # Detach caller-owned data. Parameters declare only this activity's actual
        # dependencies, never the enclosing job ID or unrelated role settings.
        import json
        object.__setattr__(self, 'parameters', json.loads(canonical_json(self.parameters)))

    @property
    def identity(self):
        return content_hash(canonical_json(asdict(self)))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, 'inputs': tuple(Resource(**v) for v in value.get('inputs', ()))})


@dataclass(frozen=True)
class ActivityResult:
    outputs: tuple[Resource, ...] = ()
    content_status: str = 'accepted'
    detail: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'outputs', tuple(self.outputs))
        if self.content_status not in {'accepted', 'rejected', 'unavailable', 'not_requested'}:
            raise ValueError('invalid research content status')
        if len({r.path for r in self.outputs}) != len(self.outputs):
            raise ValueError('activity outputs require distinct paths')
        if not isinstance(self.detail, str):
            raise ValueError('activity detail must be text')

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, 'outputs': tuple(Resource(**v) for v in value.get('outputs', ()))})


class ResearchJournal(Protocol):
    def events(self) -> tuple[dict, ...]: ...
    def append(self, event: dict) -> None: ...
