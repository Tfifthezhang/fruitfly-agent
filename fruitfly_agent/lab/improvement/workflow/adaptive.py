"""Translate declared online stop conditions into scoped control requests."""
from dataclasses import asdict
from uuid import uuid4
from fruitfly_agent.improvement.contracts.live import ControlRequest
from fruitfly_agent.improvement.contracts.stopping import SearchState, stop_reason
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
