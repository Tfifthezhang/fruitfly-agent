"""Public plans contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Protocol
from fruitfly_agent.improvement.contracts.validation import identifier, relative_path, bounded
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash
import math
from typing import Literal
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import SystemVersion

@dataclass(frozen=True)
class StageTimeouts:
    editor_seconds: float = 1200
    execution_seconds: float = 3600
    evaluator_seconds: float = 1200

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('stage times must be finite positive seconds')


@dataclass(frozen=True)
class RunPlan:
    job_id: str
    parent: SystemVersion
    component_ids: tuple[str, ...]
    generator_id: str = 'agent-editor-v1'
    mode: Literal['parallel', 'sequential'] = 'parallel'
    width: int = 1
    depth: int = 1
    purpose: Literal['task', 'persistent'] = 'task'
    feedback: Literal['behavior', 'scored'] = 'behavior'
    timeouts: StageTimeouts = field(default_factory=StageTimeouts)
    direction: str = ''
    strategy_id: str = 'harness2'
    retain_experience: bool = True
    component_options: dict = field(default_factory=dict)
    component_description_id: str = ''

    def __post_init__(self):
        if self.component_description_id:
            require_hash(self.component_description_id)
        if not isinstance(self.component_options, dict) or set(self.component_options) - set(self.component_ids):
            raise ValueError('component options must name selected components')
        identifier(self.job_id)
        identifier(self.generator_id)
        identifier(self.strategy_id)
        if type(self.retain_experience) is not bool:
            raise ValueError('retain_experience must be boolean')
        object.__setattr__(self, 'component_ids', tuple(self.component_ids))
        if not self.component_ids or len(set(self.component_ids)) != len(self.component_ids):
            raise ValueError('declare a distinct nonempty component scope')
        for component_id in self.component_ids:
            identifier(component_id)
        if self.mode not in {'parallel', 'sequential'} or self.purpose not in {'task', 'persistent'}:
            raise ValueError('invalid improvement mode or purpose')
        if self.feedback not in {'behavior', 'scored'}:
            raise ValueError('invalid feedback capability')
        for value, maximum in ((self.width, 10), (self.depth, 10)):
            if type(value) is not int or value < 1 or maximum is not None and value > maximum:
                raise ValueError('improvement allocation exceeds its bound')
        if isinstance(self.timeouts, dict):
            object.__setattr__(self, 'timeouts', StageTimeouts(**self.timeouts))
        if not isinstance(self.timeouts, StageTimeouts):
            raise ValueError('plan requires stage times')
        bounded(self.direction, 2000, empty=True)

    @property
    def conditions_id(self):
        return content_hash(canonical_json(asdict(self)))


@dataclass(frozen=True)
class TaskSetRunPlan(RunPlan):
    """Bind task-set comparison conditions to the common phase-time plan."""
    task_set_conditions: str = ''

    def __post_init__(self):
        super().__post_init__()
        if self.task_set_conditions:
            require_hash(self.task_set_conditions)


@dataclass(frozen=True)
class ExperienceEntry:
    entry_id: str
    task_id: str
    cue: str
    lesson: str
    evidence_ids: tuple[str, ...]
    harness: HarnessSnapshot
    limitations: str = ''

    def __post_init__(self):
        identifier(self.entry_id)
        identifier(self.task_id)
        bounded(self.cue, 2000)
        bounded(self.lesson, 6000)
        bounded(self.limitations, 4000, empty=True)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        if not self.evidence_ids:
            raise ValueError('retained lessons need execution evidence')

