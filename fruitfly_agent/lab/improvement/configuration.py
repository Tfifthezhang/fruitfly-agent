"""User defaults for bounded searches, independent of frontends and task backends."""
from dataclasses import dataclass, field
from fruitfly_agent.improvement.contracts.plans import StageTimeouts


@dataclass(frozen=True)
class ImprovementSettings:
    components: tuple[str, ...] = ()
    generator: str = 'agent-editor-v1'
    scope: str = 'task'
    direction: str = ''
    timeouts: StageTimeouts = field(default_factory=StageTimeouts)
    component_options: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.component_options, dict) or set(self.component_options) - set(self.components):
            raise ValueError('component_options must name selected components')
        if (len(set(self.components)) != len(self.components)
                or any(not isinstance(v, str) or not v.strip() for v in self.components)):
            raise ValueError('components must contain distinct registered component IDs')
        if self.scope not in {'task', 'persistent'}:
            raise ValueError('invalid feedback or effect scope')
        if isinstance(self.timeouts, dict):
            object.__setattr__(self, 'timeouts', StageTimeouts(**self.timeouts))
        if not isinstance(self.timeouts, StageTimeouts):
            raise ValueError('improvement requires stage times')
        if not isinstance(self.direction, str) or len(self.direction) > 2000:
            raise ValueError('invalid stage guidance')

@dataclass(frozen=True)
class TaskSetImprovementSettings(ImprovementSettings):
    pass
