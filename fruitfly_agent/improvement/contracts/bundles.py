"""Portable typed activity outputs, independent of filesystem layout."""
from dataclasses import dataclass, asdict
from .tasks import Resource
from .versions import content_hash, canonical_json, require_hash


@dataclass(frozen=True)
class ResearchBundle:
    kind: str
    producer: str
    outputs: tuple[Resource, ...]
    inputs: tuple[str, ...] = ()
    configuration_id: str = ''
    dependencies: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in {'eval', 'import', 'organize', 'assess', 'propose', 'execute', 'compare'}:
            raise ValueError('unknown research bundle kind')
        for field in ('outputs', 'inputs', 'dependencies'):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if len({r.path for r in self.outputs}) != len(self.outputs):
            raise ValueError('bundle outputs require distinct paths')
        for reference in (*self.dependencies, *((self.configuration_id,) if self.configuration_id else ())):
            require_hash(reference)

    def to_dict(self):
        return asdict(self)

    @property
    def primary_path(self):
        return {'organize': 'view.json', 'propose': 'proposal.json',
            'compare': 'comparison.json'}.get(self.kind, 'batch.json')

    @property
    def identity(self):
        return content_hash(canonical_json(self.to_dict()))

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, 'outputs': tuple(Resource(**r) for r in value['outputs'])})
