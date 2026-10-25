"""Declared multi-metric comparison; incomplete evidence never becomes success."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Objective:
    metric: str
    direction: str = 'max'
    minimum_gain: float = 0

    def __post_init__(self):
        if self.direction not in {'min', 'max'} or not math.isfinite(self.minimum_gain) or self.minimum_gain < 0:
            raise ValueError('invalid comparison objective')


class LexicographicComparison:
    def __init__(self, objectives, *, statuses=('final',), scope='execution'):
        self.objectives, self.statuses, self.scope = tuple(objectives), tuple(statuses), scope
        if not self.objectives:
            raise ValueError('comparison requires declared objectives')

    def compare(self, before, after):
        if (before.status not in self.statuses or after.status not in self.statuses
                or before.scope != self.scope or after.scope != self.scope
                or before.assessor_id != after.assessor_id):
            return 'insufficient'
        a, b = ({m.name: m.value for m in assessment.metrics} for assessment in (before, after))
        for objective in self.objectives:
            x, y = a.get(objective.metric), b.get(objective.metric)
            if (isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float))
                    or not isinstance(y, (int, float))):
                return 'insufficient'
            gain = (y - x) * (1 if objective.direction == 'max' else -1)
            if abs(gain) > objective.minimum_gain:
                return 'better' if gain > 0 else 'worse'
        return 'tied'
