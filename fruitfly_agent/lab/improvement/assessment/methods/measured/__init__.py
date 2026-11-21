"""Deterministic comparison of explicitly paired research receipts."""
from math import fsum, isfinite
from typing import Any

from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash, require_hash


def compare_measured(before, after, manifest, input_ids):
    fields = {'pairs', 'metric', 'scorer_id', 'outcome_policy_id', 'direction',
              'minimum_gain', 'maximum_regression_rate'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('invalid measured comparison manifest fields')
    direction = manifest['direction']
    minimum_gain = manifest['minimum_gain']
    maximum_regression = manifest['maximum_regression_rate']
    metric = manifest['metric']
    for key in ('scorer_id', 'outcome_policy_id'):
        require_hash(manifest[key])
    if (direction not in {'max', 'min'} or not isinstance(metric, str) or not metric
            or not _number(minimum_gain) or minimum_gain < 0
            or not _number(maximum_regression) or not 0 <= maximum_regression <= 1):
        raise ValueError('invalid measured objective')
    pairs = manifest['pairs']
    if not isinstance(pairs, list) or not pairs:
        raise ValueError('measured comparison requires planned pairs')
    for pair in pairs:
        if (not isinstance(pair, dict) or set(pair) != {'task_id', 'attempt', 'before', 'after'}
                or not isinstance(pair['task_id'], str) or not pair['task_id']
                or type(pair['attempt']) is not int or pair['attempt'] < 0
                or any(value is not None and (not isinstance(value, str) or not value)
                       for value in (pair['before'], pair['after']))):
            raise ValueError('invalid planned comparison pair')
    keys = {(p['task_id'], p['attempt']) for p in pairs}
    if len(keys) != len(pairs):
        raise ValueError('duplicate planned comparison pair')

    sides = {}
    issues = []
    for side, batch in (('before', before), ('after', after)):
        records = {r.run_id: r for r in batch.records}
        expected = [p[side] for p in pairs if p[side] is not None]
        if len(set(expected)) != len(expected):
            raise ValueError('comparison manifest reuses a run')
        if set(records) - set(expected) or {t.task_id for t in batch.tasks} - {key for key, _ in keys}:
            issues.append(side + ' contains undeclared tasks or runs')
        observations = {}
        for item in batch.observations:
            if isinstance(item, dict) and item.get('name') == metric:
                run_id = item.get('run_id')
                if run_id in observations:
                    raise ValueError('duplicate objective observation for ' + str(run_id))
                observations[run_id] = item
        sides[side] = records, observations

    rows: list[dict[str, Any]] = []
    sign = 1 if direction == 'max' else -1
    for pair in sorted(pairs, key=lambda p: (p['task_id'], p['attempt'])):
        row = dict(pair)
        pair_records = []
        for side, (runs, observations) in sides.items():
            receipt = runs.get(pair[side])
            observation = observations.get(pair[side], {}) if receipt else {}
            if receipt and receipt.task_id != pair['task_id']:
                raise ValueError('planned task differs from execution receipt')
            semantics = observation.get('semantics', {})
            raw = observation.get('value')
            attributed = (observation.get('scorer_id') == manifest['scorer_id']
                          and observation.get('outcome_policy_id') == manifest['outcome_policy_id']
                          and type(observation.get('attempt')) is int
                          and observation.get('attempt') == pair['attempt']
                          and semantics.get('scope') == 'execution')
            eligible = receipt and receipt.status == 'completed' and attributed and observation.get('eligible') is True
            row[side] = {'run_id': pair[side], 'status': receipt.status if receipt else 'missing',
                         'attributed': attributed,
                         'scorer_id': observation.get('scorer_id'),
                         'outcome_policy_id': observation.get('outcome_policy_id'),
                         'source_identity': observation.get('source_identity'),
                         'raw': raw, 'value': raw if eligible and _number(raw) else None,
                         'outcome': semantics.get('outcome', 'unknown') if eligible else 'unknown',
                         'model_calls': receipt.model_calls if receipt else None,
                         'material_id': receipt.material_id if receipt else None,
                         'initial_state_id': receipt.initial_state_id if receipt else None,
                         'conditions_id': receipt.conditions_id if receipt else None}
            pair_records.append(receipt)
        base, candidate = pair_records
        comparable = (base is not None and candidate is not None and
                      (base.material_id, base.initial_state_id, base.conditions_id) ==
                      (candidate.material_id, candidate.initial_state_id, candidate.conditions_id))
        row['comparable'] = comparable
        pair_values = row['before']['value'], row['after']['value']
        row['gain'] = sign * (pair_values[1] - pair_values[0]) if comparable and None not in pair_values else None
        rows.append(row)

    gains = [r['gain'] for r in rows if r['gain'] is not None]
    retained = sum(r['before']['outcome'] == r['after']['outcome'] == 'met' for r in rows if r['gain'] is not None)
    regressions = sum(r['before']['outcome'] == 'met' and r['after']['outcome'] == 'unmet'
                      for r in rows if r['gain'] is not None)
    denominator = retained + regressions
    regression_rate = regressions / denominator if denominator else None
    average = fsum(gains) / len(gains) if gains else None
    if (average is None or issues or len(gains) != len(rows)
            or any(r[side]['outcome'] == 'unknown' for r in rows for side in sides)):
        conclusion = 'insufficient'
    elif (regression_rate is not None and regression_rate > maximum_regression) or average < 0:
        conclusion = 'worse'
    elif average > 0 and average >= minimum_gain:
        conclusion = 'better'
    else:
        conclusion = 'tied'
    coverage = {'planned': len(rows), 'paired': len(gains), 'issues': issues}
    absolute = {}
    for side in sides:
        cells = [r[side] for r in rows]
        observed = sum(c['status'] != 'missing' for c in cells)
        errors = sum(c['status'] in {'error', 'cancelled', 'timeout'} for c in cells)
        values = [c['value'] for c in cells if c['value'] is not None]
        met = sum(c['outcome'] == 'met' for c in cells)
        outcomes = met + sum(c['outcome'] == 'unmet' for c in cells)
        coverage[side] = {'observed': observed, 'measured': len(values), 'known_outcomes': outcomes,
                          'execution_errors': errors, 'error_rate': errors / observed if observed else None}
        absolute[side] = {'mean': fsum(values) / len(values) if values else None,
                          'successes': met, 'success_rate': met / outcomes if outcomes else None}
    return {
        'method': 'measured', 'policy_id': content_hash(canonical_json(manifest)), 'inputs': list(input_ids),
        'coverage': coverage, 'absolute': absolute,
        'usage': {'comparison_model_calls': 0},
        'assurance': 'paired-measurement' if conclusion != 'insufficient' else 'insufficient',
        'conclusion': conclusion, 'mean_gain': average,
        'wins': sum(g > 0 for g in gains), 'losses': sum(g < 0 for g in gains),
        'retained_successes': retained, 'regressions': regressions,
        'regression_denominator': denominator, 'regression_rate': regression_rate, 'pairs': rows,
    }


def _number(value):
    return type(value) in (int, float) and isfinite(value)
