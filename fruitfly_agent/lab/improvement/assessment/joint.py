"""Explicit joint development utility; raw task scores retain their own policies."""
from statistics import mean
from ..contracts.evaluation import JointAssessment


def assess_batch(snapshot, batch, trials, settings):
    entries = {e.key: e for e in snapshot.entries}
    expected = {(key, attempt) for key in batch.task_keys for attempt in range(batch.attempts)}
    found = {}
    for trial in trials:
        key = (trial.task_key, trial.attempt)
        if key not in expected or key in found:
            raise ValueError('unexpected or duplicate task attempt')
        entry = entries[trial.task_key]
        record, measurement = trial.record, trial.measurement
        if record is not None and (record.task_id != entry.task.task_id or record.material_id != entry.task.material_id):
            raise ValueError('trial material differs from frozen task entry')
        if (not trial.error and record is not None and record.status == 'completed' and measurement is not None
                and measurement.run_id == record.run_id and measurement.policy_id == entry.objective.policy_id):
            found[key] = entry.objective.normalize(measurement.score)
    complete = set(found) == expected
    tasks = tuple((key, mean(found[(key, attempt)] for attempt in range(batch.attempts)))
        for key in batch.task_keys if all((key, attempt) in found for attempt in range(batch.attempts)))
    groups: dict[str, list[float]] = {}
    for key, value in tasks:
        groups.setdefault(entries[key].collection_id, []).append(value)
    collections = tuple((key, mean(values)) for key, values in sorted(groups.items()))
    weights = dict(settings.weights)
    unknown = set(weights) - {e.collection_id for e in snapshot.entries}
    if unknown:
        raise ValueError('joint weights cite unknown collections')
    score = None
    if complete:
        if settings.aggregation == 'task-macro':
            score = mean(v for key, v in tasks)
        else:
            score = sum(v * weights.get(key, 1) for key, v in collections) / sum(weights.get(key, 1) for key, v in collections)
    return JointAssessment(score, collections, tasks, len(expected), len(found), settings.aggregation, settings.weights)
