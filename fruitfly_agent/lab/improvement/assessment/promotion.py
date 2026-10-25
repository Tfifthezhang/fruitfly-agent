"""Compare candidates only on an identical declared batch and conditions."""
from ..contracts.evaluation import CandidateComparison


def compare_candidates(before, after, settings):
    if (before.batch != after.batch or before.conditions_id != after.conditions_id
            or before.assessment.aggregation != after.assessment.aggregation
            or before.assessment.weights != after.assessment.weights):
        raise ValueError('candidate comparison needs identical tasks, attempts and conditions')
    a, b = before.assessment.score, after.assessment.score
    result, gain = 'insufficient', None
    if a is not None and b is not None:
        gain = b - a
        result = 'better' if gain > settings.minimum_gain else 'worse' if gain < -settings.minimum_gain else 'tied'
        allowed = settings.max_collection_regression
        if allowed is not None:
            old, new = dict(before.assessment.collections), dict(after.assessment.collections)
            if set(old) != set(new):
                result = 'insufficient'
            elif any(new[key] < old[key] - allowed for key in old):
                result = 'worse'
    return CandidateComparison(before.evaluation_id, after.evaluation_id, before.batch.batch_id, result, gain)
