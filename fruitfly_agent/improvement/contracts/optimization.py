"""Owner-declared optimization surfaces, independent of search algorithms."""
from dataclasses import dataclass, asdict
from typing import Literal, Protocol, runtime_checkable
import hashlib
import re
from fruitfly_agent.core.config import AgentLoopConfig

from .components import ComponentDocument


@dataclass(frozen=True)
class OptimizationSpec:
    role: str
    representation: str
    operations: frozenset[str] = frozenset({'replace'})
    update: str = 'offline'
    boundary: str = 'task'
    state: str = 'frozen'
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self):
        choices = {
            'role': {'H', 'S', 'I'},
            'representation': {'parameters', 'text', 'documents', 'structure', 'learning-state'},
            'update': {'offline', 'within-task', 'between-tasks', 'between-generations'},
            'boundary': {'request', 'turn', 'task', 'generation'},
            'state': {'frozen', 'trial-local', 'retained'},
        }
        for field, allowed in choices.items():
            if getattr(self, field) not in allowed:
                raise ValueError('invalid optimization ' + field)
        for field in ('operations', 'required_capabilities'):
            value = getattr(self, field)
            if isinstance(value, str):
                raise ValueError(field + ' must be a collection')
            object.__setattr__(self, field, frozenset(value))
        if not self.operations or self.operations - {'set', 'replace', 'add', 'remove', 'reorder', 'update-state'}:
            raise ValueError('invalid optimization operations')
        if any(not isinstance(v, str) or not v for v in self.required_capabilities):
            raise ValueError('invalid optimization capability')

    def admit(self, *, role, capabilities, boundaries, updates):
        if (role != self.role or self.required_capabilities - set(capabilities)
                or self.boundary not in boundaries or self.update not in updates):
            raise ValueError('execution does not support this optimization surface')


class OptimizationAdapter(Protocol):
    optimization: OptimizationSpec
    def snapshot(self) -> ComponentDocument: ...
    def validate(self, document: ComponentDocument) -> None: ...


@dataclass(frozen=True)
class TargetBinding:
    kind: Literal['prompt', 'artifact', 'components', 'configuration']
    key: str = ''

    def __post_init__(self):
        if self.kind not in {'prompt', 'artifact', 'components', 'configuration'} or (self.kind in {'artifact', 'configuration'} and not self.key):
            raise ValueError('invalid target binding')


@dataclass(frozen=True)
class TargetSnapshot:
    target_id: str
    text: str
    binding: TargetBinding
    schema: str = 'text-v1'
    role: str = 'H'
    components: tuple['TargetSnapshot', ...] = ()

    def __post_init__(self):
        if self.role not in {'H', 'S', 'I'}:
            raise ValueError('target role must be H, S or I')
        if not isinstance(self.target_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.target_id):
            raise ValueError('target identity must be a stable identifier')
        if not isinstance(self.text, str) or not isinstance(self.binding, TargetBinding):
            raise TypeError('target requires text and a typed binding')
        object.__setattr__(self, 'components', tuple(self.components))
        if self.binding.kind == 'components':
            if (not self.components or any(p.components for p in self.components)
                    or len({p.target_id for p in self.components}) != len(self.components)
                    or len({p.binding for p in self.components}) != len(self.components)):
                raise ValueError('component targets need distinct flat registered bindings')
        elif self.components:
            raise ValueError('only a component binding can contain component snapshots')

    @property
    def content_hash(self):
        return 'sha256:' + hashlib.sha256(self.text.encode('utf-8')).hexdigest()

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError('invalid target snapshot')
        return cls(**{**data, 'binding': TargetBinding(**data['binding']),
                      'components': tuple(cls.from_dict(p) for p in data['components'])})


@runtime_checkable
class TextProjection(Protocol):
    """Text codec and runtime projection used by a typed optimization adapter."""
    optimization: OptimizationSpec
    def snapshot(self) -> TargetSnapshot: ...
    def validate(self, text: str) -> None: ...
    def prepare_trial(self, config: AgentLoopConfig, text: str) -> AgentLoopConfig: ...
