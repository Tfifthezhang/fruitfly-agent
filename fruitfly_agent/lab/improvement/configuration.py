"""User defaults for bounded searches, independent of frontends and task backends."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImprovementSettings:
    strategy: str = 'simple'
    components: tuple[str, ...] = ('base_prompt',)
    generator: str = 'agent-editor-v1'
    rounds: int = 1
    mode: str = 'parallel'
    width: int = 1
    feedback: str = 'auto'
    scope: str = 'task'
    direction: str = ''
    retain_experience: bool = False
    max_model_calls: int = 256
    max_executions: int = 16
    operation_timeout: float = 1200
    timeout_seconds: float = 3600
    component_options: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.component_options, dict) or set(self.component_options) - set(self.components):
            raise ValueError('component_options must name selected components')
        from .strategies import builtin_strategies
        definition = builtin_strategies().get(self.strategy)
        if definition.validate_options is not None:
            definition.validate_options(self)
        if (not self.components or len(set(self.components)) != len(self.components)
                or any(not isinstance(v, str) or not v.strip() for v in self.components)):
            raise ValueError('components must contain distinct registered component IDs')
        if self.feedback not in {'auto', 'behavior', 'scored'} or self.scope not in {'task', 'persistent'}:
            raise ValueError('invalid feedback or effect scope')
        if self.mode not in {'parallel', 'sequential'}:
            raise ValueError('invalid search mode')
        for name, maximum in (('rounds', 10), ('width', 10), ('max_model_calls', self.allocation_maximum('model')), ('max_executions', self.allocation_maximum('execution'))):
            value = getattr(self, name)
            if type(value) is not int or value < 1 or maximum is not None and value > maximum:
                raise ValueError(name + ' exceeds its positive allocation bound')
        from math import isfinite
        for name in ('operation_timeout', 'timeout_seconds'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value <= 0:
                raise ValueError(name + ' must be finite and positive')
        if self.operation_timeout > 14400:
            raise ValueError('operation_timeout exceeds 14400 seconds')
        if type(self.retain_experience) is not bool or not isinstance(self.direction, str) or len(self.direction) > 2000:
            raise ValueError('invalid retention or guidance')

    def allocation_maximum(self, resource):
        return 10000 if resource == 'model' else 1000


@dataclass(frozen=True)
class TaskSetImprovementSettings(ImprovementSettings):
    def allocation_maximum(self, resource):
        return None
