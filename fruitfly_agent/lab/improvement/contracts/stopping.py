"""Shared immutable cycle state and attributable stop decisions."""
from dataclasses import dataclass
from typing import Protocol
from .assessment import Measurement
from .live import Assessment


@dataclass(frozen=True)
class SearchState:
    round_index: int
    rounds: int
    new_candidates: int
    repeated: bool
    requested_stop: bool
    measurements: tuple[Measurement, ...] = ()
    incumbent_run_id: str | None = None
    model_calls: int = 0
    executions: int = 0
    phase: str = 'round'
    consecutive_no_gain: int = 0
    consecutive_failures: int = 0
    elapsed_seconds: float = 0
    assurance: str = 'selected'
    assessments: tuple[Assessment, ...] = ()


@dataclass(frozen=True)
class StopDecision:
    reason: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('a stopping decision needs a reason')


class StopPolicy(Protocol):
    def decide(self, state: SearchState) -> StopDecision | str | None: ...


def stop_reason(decision):
    if decision is None:
        return None
    if isinstance(decision, StopDecision):
        return decision.reason
    if isinstance(decision, str) and decision:
        return decision
    raise ValueError('invalid stop decision')
