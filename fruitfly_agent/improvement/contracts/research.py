"""Serializable research revisions; current configuration extends immutable history."""
from dataclasses import dataclass, field
import json
from .versions import canonical_json, content_hash


@dataclass(frozen=True)
class ResearchRevision:
    configuration: dict = field(default_factory=dict)
    parent: str = ''
    direction: str = ''

    def __post_init__(self):
        object.__setattr__(self, 'configuration', json.loads(canonical_json(self.configuration)))
        if not isinstance(self.direction, str) or len(self.direction) > 16000:
            raise ValueError('research direction must be bounded text')
        if self.parent:
            from .versions import require_hash
            require_hash(self.parent)

    @property
    def identity(self):
        return content_hash(canonical_json({'configuration': self.configuration,
            'parent': self.parent, 'direction': self.direction}))


@dataclass(frozen=True)
class ResearchBatch:
    tasks: tuple
    records: tuple
    observations: tuple = ()

    def __post_init__(self):
        from .organization import OrganizationRequest
        for name in ('tasks', 'records', 'observations'):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        OrganizationRequest(self.tasks, self.records)
        canonical_json(self.observations)

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        from .tasks import TaskMaterial, Resource
        from .execution import ExecutionRecord
        if set(value) != {'tasks', 'records', 'observations'}:
            raise ValueError('research batch requires tasks, records and observations')
        tasks = tuple(TaskMaterial(**{**t, 'inputs': tuple(Resource(**r) for r in t['inputs'])}) for t in value['tasks'])
        records = tuple(ExecutionRecord(**{**r, 'artifacts': tuple(Resource(**a) for a in r['artifacts'])}) for r in value['records'])
        return cls(tasks, records, tuple(value['observations']))
