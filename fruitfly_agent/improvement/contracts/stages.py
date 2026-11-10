"""Named immutable inputs for independently invoked research stages."""
from dataclasses import dataclass, fields
from typing import Any
from .tasks import Resource


@dataclass(frozen=True, kw_only=True)
class StageInputs:
    """Bind logical roles explicitly; ordering never assigns resource meaning."""
    harness: Resource | None = None
    batches: tuple[Resource, ...] = ()
    evidence: tuple[Resource, ...] = ()
    assessments: tuple[Resource, ...] = ()
    context: tuple[Resource, ...] = ()

    def __post_init__(self):
        if self.harness is not None and not isinstance(self.harness, Resource):
            raise TypeError('harness must be a Resource')
        for name in ('batches', 'evidence', 'assessments', 'context'):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, Resource) for value in values):
                raise TypeError(name + ' must contain Resources')
            object.__setattr__(self, name, values)

    def validate_for(self, stage):
        requirements = {
            'organize': ('batches',),
            'assess': ('batches',),
            'propose': ('harness', 'batches'),
            'execute': ('harness',),
            'compare': ('batches',),
        }
        if stage not in requirements:
            raise ValueError('unsupported resource-consuming stage: ' + str(stage))
        for name in requirements[stage]:
            if not getattr(self, name):
                raise ValueError(stage + ' requires ' + name)
        if stage == 'compare' and len(self.batches) < 2:
            raise ValueError('compare requires at least two batches')
        return self

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError('unknown stage input fields')
        parameters: dict[str, Any] = {name: (Resource(**items) if name == 'harness' and items is not None
            else None if name == 'harness' else tuple(Resource(**item) for item in items))
            for name, items in value.items()}
        return cls(**parameters)
