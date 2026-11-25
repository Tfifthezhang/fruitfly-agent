"""Deterministic paired task bootstrap; repeated attempts are not new tasks."""
import random
from statistics import mean


def paired_interval(rows, repetitions, seed):
    groups: dict[str, list[float]] = {}
    for row in rows:
        if row['delivery_gain'] is None:
            return None
        groups.setdefault(row['origin_id'], []).append(row['delivery_gain'])
    if len(groups) < 2:
        return None
    values = [mean(v) for v in groups.values()]
    rng = random.Random(seed)
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(repetitions))
    return {'method': 'paired-task-bootstrap', 'confidence': .95,
            'lower': samples[int(.025 * (repetitions - 1))],
            'upper': samples[int(.975 * (repetitions - 1))],
            'tasks': len(values), 'resamples': repetitions, 'seed': seed,
            'scope': 'Conditional on the selected tasks; not independent evolution or unseen-task evidence.'}
