"""Translate declared online stop conditions into scoped control requests."""
from dataclasses import dataclass
import math
from uuid import uuid4
from fruitfly_agent.improvement.contracts.live import ControlRequest
from fruitfly_agent.improvement.contracts.stopping import SearchState, StopDecision, stop_reason
from fruitfly_agent.improvement.contracts.versions import canonical_json


class StopExecutionPolicy:
    def __init__(self, policy, *, max_event_lag=0):
        self.policy, self.max_event_lag = policy, max_event_lag
    async def decide(self, assessment):
        state = SearchState(0, 1, 0, False, False, phase='execution', assessments=(assessment,))
        decision = self.policy.decide(state)
        if decision is None: return ()
        return (ControlRequest('control-' + uuid4().hex, 'stop', assessment.position,
            canonical_json({'reason': stop_reason(decision), 'assessment_id': assessment.assessment_id}), self.max_event_lag),)


@dataclass(frozen=True)
class MetricThreshold:
    assessor_id: str
    metric: str
    threshold: float
    direction: str = 'max'
    scope: str = 'execution'
    def __post_init__(self):
        if not self.assessor_id or not self.metric or not math.isfinite(self.threshold) or self.direction not in {'max', 'min'}:
            raise ValueError('invalid metric stopping condition')
    def decide(self, state):
        # The latest assessment for a scope supersedes provisional/failed history.
        values = [a for a in state.assessments if a.assessor_id == self.assessor_id and a.scope == self.scope]
        if not values or values[-1].status != 'final':
            return None
        a = values[-1]
        value = next((m.value for m in a.metrics if m.name == self.metric), None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if (value >= self.threshold if self.direction == 'max' else value <= self.threshold):
            return StopDecision('metric_threshold', (a.assessment_id,))
        return None

