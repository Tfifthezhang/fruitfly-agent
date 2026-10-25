"""Public execution contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from .validation import identifier, relative_path, bounded
from .versions import canonical_json, content_hash, require_hash
from typing import Literal
from .tasks import Resource, TaskMaterial
from .components import HarnessSnapshot
from .plans import RunPlan

@dataclass(frozen=True)
class ExecutionRecord:
    run_id: str
    task_id: str
    material_id: str
    harness_id: str
    initial_state_id: str
    conditions_id: str
    status: Literal['completed', 'error', 'cancelled', 'budget_exhausted']
    output: str = ''
    artifacts: tuple[Resource, ...] = ()
    model_calls: int | None = None

    def __post_init__(self):
        for value in (self.run_id, self.task_id):
            identifier(value)
        for value in (self.material_id, self.harness_id, self.initial_state_id, self.conditions_id):
            require_hash(value)
        if self.status not in {'completed', 'error', 'cancelled', 'budget_exhausted'}:
            raise ValueError('invalid execution status')
        bounded(self.output, 120_000, empty=True)
        object.__setattr__(self, 'artifacts', tuple(self.artifacts))
        if self.model_calls is not None and (type(self.model_calls) is not int or self.model_calls < 0):
            raise ValueError('invocation usage must be known nonnegative or absent')


class TaskRunner(Protocol):
    capabilities: frozenset[str]
    async def execute(self, plan: RunPlan, task: TaskMaterial, harness: HarnessSnapshot) -> ExecutionRecord: ...

