"""Shared generation accounting and pure stop decisions for both RSI drivers."""
from dataclasses import dataclass
import time
from typing import Protocol

from fruitfly_agent.improvement.contracts.stopping import SearchState, StopPolicy, stop_reason
from fruitfly_agent.improvement.contracts.assessment import Measurement


class AllocationView(Protocol):
    used: dict[str, int]


@dataclass
class EvolutionController:
    stop_policy: StopPolicy | None = None
    consecutive_no_gain: int = 0
    consecutive_failures: int = 0
    started_at: float = 0
    budget: AllocationView | None = None

    def __post_init__(self):
        self.started_at = self.started_at or time.monotonic()

    def finish(self, *, steps, limit, outcome, score=None, policy_id='', run_id='generation', assurance='selected'):
        adopted = outcome == 'adopted'
        self.consecutive_no_gain = 0 if adopted else self.consecutive_no_gain + 1
        self.consecutive_failures = self.consecutive_failures + 1 if outcome.endswith('failed') else 0
        if self.stop_policy is None:
            return None
        measurements = (Measurement(run_id, policy_id, score),) if score is not None else ()
        state = SearchState(steps - 1, limit, int(adopted), False, False, measurements, run_id,
            model_calls=self.budget.used['model'] if self.budget is not None else 0,
            executions=self.budget.used['execution'] if self.budget is not None else 0,
            phase='generation', consecutive_no_gain=self.consecutive_no_gain,
            consecutive_failures=self.consecutive_failures, elapsed_seconds=time.monotonic() - self.started_at,
            assurance=assurance)
        return stop_reason(self.stop_policy.decide(state))
