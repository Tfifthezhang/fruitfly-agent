"""Public assessment contracts; no external effects."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol
from fruitfly_agent.improvement.contracts.validation import identifier, relative_path, bounded
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash
import math
from typing import Literal, TYPE_CHECKING
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
if TYPE_CHECKING:
    from fruitfly_agent.improvement.contracts.pipeline import ImprovementOutcome


class AssessmentUnavailable(RuntimeError):
    """Required completed assessment could not establish an attributable judgment."""

@dataclass(frozen=True)
class Measurement:
    run_id: str
    policy_id: str
    score: float
    feedback: str = ''

    def __post_init__(self):
        identifier(self.run_id)
        identifier(self.policy_id)
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
            raise ValueError('measurements require a finite score')
        bounded(self.feedback, 4000, empty=True)


@dataclass(frozen=True)
class SelectionDecision:
    run_id: str
    reason: str
    assurance: Literal['selected', 'verified'] = 'selected'
    evidence_ids: tuple[str, ...] = ()
    comparison_id: str = ''

    def __post_init__(self):
        identifier(self.run_id)
        object.__setattr__(self, 'evidence_ids', tuple(self.evidence_ids))
        for value in self.evidence_ids:
            require_hash(value)
        if self.comparison_id:
            require_hash(self.comparison_id)
        bounded(self.reason, 4000)
        if self.assurance not in {'selected', 'verified'}:
            raise ValueError('selection assurance must be explicit')


class Selector(Protocol):
    async def select(self, task: TaskMaterial, records: tuple[ExecutionRecord, ...]) -> SelectionDecision: ...


class MeasurementSource(Protocol):
    async def measure(self, task: TaskMaterial, record: ExecutionRecord) -> Measurement | None: ...


class VerificationPolicy(Protocol):
    async def verify(self, outcome: ImprovementOutcome) -> SelectionDecision | None: ...

