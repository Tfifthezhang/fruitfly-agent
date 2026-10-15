"""Batch trial receipts and injected executors for original or derived tasks."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from fruitfly_agent.core.config import AgentLoopConfig
from .search import TaskCase

TRIAL_SERVICES_COMPONENT = "optimization-trial-services"


@dataclass(frozen=True)
class TrialOutcome:
    output: str
    score: float
    feedback: str = ""

    def __post_init__(self):
        if (not isinstance(self.output, str) or not isinstance(self.feedback, str)
                or isinstance(self.score, bool) or not isinstance(self.score, (int, float))
                or not math.isfinite(self.score)):
            raise ValueError("trial outcomes require text and a finite non-boolean score")


class TrialExecutor(Protocol):
    """Host-injected executor; config.provider is budgeted and inputs exclude holdout answers from generation.

    Implementations own isolated environment reset/cleanup and must not mutate a
    production runtime. Benchmarks remain external implementations of this seam.
    """
    async def run(self, config: AgentLoopConfig, case: TaskCase, *, signal) -> TrialOutcome: ...


@dataclass(frozen=True)
class BatchObservation:
    evaluation_id: str
    candidate_id: str
    case_id: str
    stage: str
    repeat: int
    status: str
    score: float | None
    output: str
    feedback: str


@dataclass(frozen=True)
class BatchEvaluation:
    observations: tuple[BatchObservation, ...]
    score: float | None
