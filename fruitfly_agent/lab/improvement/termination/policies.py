"""Pure configurable conditions. None never means quality assurance."""
from dataclasses import dataclass
import math
from ..contracts.stopping import StopDecision


def positive(value):
    if type(value) is not int or value < 1:
        raise ValueError('a positive integer limit is required')


@dataclass(frozen=True)
class IterationLimit:
    limit: int
    def __post_init__(self): positive(self.limit)
    def decide(self, state):
        return StopDecision('iteration_limit') if state.round_index + 1 >= self.limit else None


@dataclass(frozen=True)
class NoImprovement:
    patience: int
    def __post_init__(self): positive(self.patience)
    def decide(self, state):
        return StopDecision('no_improvement') if state.consecutive_no_gain >= self.patience else None


@dataclass(frozen=True)
class FailureLimit:
    limit: int
    def __post_init__(self): positive(self.limit)
    def decide(self, state):
        return StopDecision('failure_limit') if state.consecutive_failures >= self.limit else None


@dataclass(frozen=True)
class ResourceLimit:
    resource: str
    limit: float
    def __post_init__(self):
        if self.resource not in {'model_calls', 'executions', 'elapsed_seconds'} or not math.isfinite(self.limit) or self.limit <= 0:
            raise ValueError('invalid resource stop limit')
    def decide(self, state):
        return StopDecision('resource_limit.' + self.resource) if getattr(state, self.resource) >= self.limit else None


@dataclass(frozen=True)
class ScoreAtLeast:
    policy_id: str
    threshold: float
    assurance: str = 'verified'
    def __post_init__(self):
        if not self.policy_id or not math.isfinite(self.threshold) or self.assurance not in {'selected', 'verified'}:
            raise ValueError('invalid score stopping condition')
    def decide(self, state):
        if self.assurance == 'verified' and state.assurance != 'verified':
            return None
        values = [m for m in state.measurements if m.policy_id == self.policy_id and m.run_id == state.incumbent_run_id]
        if values and values[-1].score >= self.threshold:
            return StopDecision('goal_reached', (values[-1].run_id,))
        return None


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


class BoundedStopPolicy:
    """The established default search policy, with unchanged string results."""
    configuration: dict = {}
    def decide(self, state):
        if state.requested_stop: return 'generator_stopped'
        if not state.new_candidates: return 'no_candidate'
        if state.repeated: return 'repeated_candidates'
        if state.round_index + 1 >= state.rounds: return 'completed'
        return None
