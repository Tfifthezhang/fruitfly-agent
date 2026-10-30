"""Shared immutable cycle state and attributable stop decisions."""
from dataclasses import dataclass
from typing import Protocol
from fruitfly_agent.improvement.contracts.assessment import Measurement
from fruitfly_agent.improvement.contracts.live import Assessment


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


from dataclasses import asdict, is_dataclass
from .versions import canonical_json

def policy_spec(policy):
    """Freeze policy parameters, not only their class name, before paid work."""
    if policy is None:
        return None
    config: object
    if hasattr(policy, 'policies'):
        config = [policy_spec(p) for p in policy.policies]
    elif is_dataclass(policy) and not isinstance(policy, type):
        config = asdict(policy)
    else:
        config = getattr(policy, 'configuration', None)
        if config is None:
            raise ValueError('frozen custom stop policies require a configuration identity')
    value = {'implementation': getattr(policy, 'implementation_id', type(policy).__module__ + '.' + type(policy).__qualname__),
             'configuration': config}
    canonical_json(value)
    return value

