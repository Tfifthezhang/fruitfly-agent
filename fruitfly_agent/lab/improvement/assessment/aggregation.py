"""Explicit weighted aggregation; no default notion of task quality."""
import math
from fruitfly_agent.improvement.contracts.live import Metric


class WeightedSum:
    def __init__(self, weights, *, name='utility'):
        self.weights, self.name = dict(weights), name
        if not self.weights or any(isinstance(w, bool) or not isinstance(w, (float, int)) or not math.isfinite(w) for w in self.weights.values()):
            raise ValueError('declare finite metric weights')

    def aggregate(self, assessment):
        values = {m.name: m.value for m in assessment.metrics}
        if any(isinstance(values.get(k), bool) or not isinstance(values.get(k), (float, int)) for k in self.weights):
            return Metric(self.name, None)
        return Metric(self.name, sum(self.weights[k] * values[k] for k in self.weights))
