"""Match explicit planned attempts; never choose an implicit intersection."""
from fruitfly_agent.improvement.contracts.observations import BatchManifest, MeasurementObservation
from typing import Any


def inventory(batch):
    manifests = [BatchManifest.from_dict(o) for o in batch.observations
                 if isinstance(o, dict) and o.get('kind') == 'batch_manifest']
    measurements = [MeasurementObservation.from_dict(o) for o in batch.observations
                    if isinstance(o, dict) and o.get('kind') == 'measurement']
    if not manifests:
        return {}, {}, {}, ['No attributed execution plan; reimport retained evidence.']
    manifest = manifests[0]
    origins = dict(manifest.origins)
    planned = {(origins.get(p.task_id, p.task_id), p.attempt): p.task_id for p in manifest.planned}
    if len(planned) != len(manifest.planned):
        raise ValueError('duplicate canonical task attempt')
    rows = {}
    metrics = {m.name for m in measurements}
    if len(metrics) > 1:
        raise ValueError('automatic comparison requires one declared primary metric; use measured_policy')
    for m in measurements:
        key = (origins.get(m.task_id, m.task_id), m.attempt)
        if key in rows:
            raise ValueError('multiple runs for one planned task attempt')
        rows[key] = m
    records = {r.run_id: r for r in batch.records}
    issues = ([] if manifest.scope_kind == 'declared' else
              ['Retained attempt numbering follows archive order; original attempt identity is unavailable.']
              if manifest.scope_kind == 'retained-planned' else
              ['Retained observed attempts do not reconstruct the original planned denominator or attempt numbering.'])
    return planned, rows, records, issues


def pair_batches(before, after, scope=None):
    a, b = inventory(before), inventory(after)
    if scope is None:
        if set(a[0]) != set(b[0]):
            raise ValueError('batch task-attempt scopes differ; select an explicit task_scope')
        keys = set(a[0])
    else:
        keys = set(inventory(scope)[0])
        if not keys or not keys <= set(a[0]) or not keys <= set(b[0]):
            raise ValueError('task_scope is not contained in both execution plans')
    result = []
    for origin, attempt in sorted(keys):
        key = (origin, attempt)
        sides: dict[str, dict[str, Any]] = {}
        for name, data in (('before', a), ('after', b)):
            m = data[1].get(key)
            r = data[2].get(m.run_id) if m else None
            outcome = m.semantics.outcome if m and m.eligible and r and r.status == 'completed' else 'unknown'
            sides[name] = {'run_id': r.run_id if r else None, 'status': r.status if r else 'missing',
                'outcome': outcome, 'value': m.value if m and m.eligible and r and r.status == 'completed' else None,
                'raw': m.raw_value if m else None, 'measurement': m.to_dict() if m else None,
                'model_calls': r.model_calls if r else None,
                'elapsed_seconds': m.elapsed_seconds if m else None,
                'cost_usd': m.cost_usd if m else None,
                'artifacts': [dict(path=x.path, artifact_id=x.artifact_id, media_type=x.media_type, kind=x.kind)
                              for x in r.artifacts] if r else []}
        x, y = (sides[s]['measurement'] for s in ('before', 'after'))
        mismatches, unknowns = [], []
        if a[3] or b[3]:
            unknowns.append('original_plan_or_attempt_identity')
        for field in ('name', 'unit', 'outcome_policy_id', 'scorer_id'):
            v, w = (x.get(field) if x else None), (y.get(field) if y else None)
            if v is None or w is None:
                unknowns.append(field)
            elif v != w:
                mismatches.append(field)
        for field in ('material', 'conditions', 'initial_state'):
            v = x['comparison'].get(field) if x else None
            w = y['comparison'].get(field) if y else None
            if v is None or w is None:
                unknowns.append(field)
            elif v != w:
                mismatches.append(field)
        if x and y and x['semantics']['direction'] != y['semantics']['direction']:
            mismatches.append('direction')
        elif not x or not y or x['semantics']['direction'] == 'unknown':
            unknowns.append('direction')
        result.append({'origin_id': origin, 'attempt': attempt, **sides,
            'comparability': 'mismatch' if mismatches else 'unknown' if unknowns else 'verified',
            'mismatches': mismatches, 'unknowns': unknowns})
    return result, {'before': len(a[0]) - len(keys), 'after': len(b[0]) - len(keys)}, a[3] + b[3]
