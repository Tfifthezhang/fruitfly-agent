"""Pure stop decisions; stopping never grants quality assurance."""
from dataclasses import dataclass
from typing import Protocol
from ..contracts.pipeline import Measurement


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


class StopPolicy(Protocol):
    def decide(self, state: SearchState) -> str | None: ...


class BoundedStopPolicy:
    def decide(self, state):
        if state.requested_stop:
            return 'generator_stopped'
        if not state.new_candidates:
            return 'no_candidate'
        if state.repeated:
            return 'repeated_candidates'
        if state.round_index + 1 >= state.rounds:
            return 'completed'
        return None
