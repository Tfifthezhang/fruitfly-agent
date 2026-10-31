"""User defaults for bounded searches, independent of frontends and task backends."""
from dataclasses import dataclass, field
from fruitfly_agent.improvement.contracts.plans import StageTimeouts


@dataclass(frozen=True)
class ImprovementSettings:
    strategy: str = 'simple'
    components: tuple[str, ...] = ()
    generator: str = 'agent-editor-v1'
    rounds: int = 1
    mode: str = 'parallel'
    width: int = 1
    feedback: str = 'auto'
    scope: str = 'task'
    direction: str = ''
    retain_experience: bool = False
    timeouts: StageTimeouts = field(default_factory=StageTimeouts)
    component_options: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.component_options, dict) or set(self.component_options) - set(self.components):
            raise ValueError('component_options must name selected components')
        from .strategies import builtin_strategies
        definition = builtin_strategies().get(self.strategy)
        if definition.validate_options is not None:
            definition.validate_options(self)
        if (len(set(self.components)) != len(self.components)
                or any(not isinstance(v, str) or not v.strip() for v in self.components)):
            raise ValueError('components must contain distinct registered component IDs')
        if self.feedback not in {'auto', 'behavior', 'scored'} or self.scope not in {'task', 'persistent'}:
            raise ValueError('invalid feedback or effect scope')
        if self.mode not in {'parallel', 'sequential'}:
            raise ValueError('invalid search mode')
        for name, maximum in (('rounds', 10), ('width', 10)):
            value = getattr(self, name)
            if type(value) is not int or value < 1 or maximum is not None and value > maximum:
                raise ValueError(name + ' exceeds its positive allocation bound')
        if isinstance(self.timeouts, dict):
            object.__setattr__(self, 'timeouts', StageTimeouts(**self.timeouts))
        if not isinstance(self.timeouts, StageTimeouts):
            raise ValueError('improvement requires stage times')
        if type(self.retain_experience) is not bool or not isinstance(self.direction, str) or len(self.direction) > 2000:
            raise ValueError('invalid retention or guidance')

@dataclass(frozen=True)
class TaskSetImprovementSettings(ImprovementSettings):
    pass
