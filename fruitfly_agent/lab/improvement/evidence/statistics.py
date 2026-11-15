"""Deterministic distributions over supplied facts with explicit known denominators."""
from collections import Counter
from fruitfly_agent.improvement.contracts.research import ObservationSemantics


def declared_outcomes(row):
    return tuple(ObservationSemantics(**o['semantics']).outcome
        for o in row.get('observations', ())
        if isinstance(o, dict) and 'semantics' in o
        and ObservationSemantics(**o['semantics']).scope == 'execution')


def batch_statistics(rows, observations):
    population = len(rows)
    def distribution(values):
        values = list(values)
        known = [value for value in values if value is not None]
        return {'population_count': len(values), 'known_count': len(known),
            'unknown_count': len(values) - len(known),
            'counts': dict(sorted(Counter(str(v) for v in known).items()))}
    counters = sorted({key for row in rows for key in row.get('counters', {})})
    cross = Counter((row['status'], row.get('termination_reason', 'unknown'),
        '|'.join(sorted(set(declared_outcomes(row)))) or 'unknown') for row in rows)
    return {'population_count': population,
        'execution_status': distribution(row['status'] for row in rows),
        'termination_reason': distribution(row.get('termination_reason') for row in rows),
        'counters': {key: distribution(row.get('counters', {}).get(key) for row in rows) for key in counters},
        'outcomes': distribution('|'.join(sorted(set(declared_outcomes(row))))
            if set(declared_outcomes(row)) - {'unknown'} else None for row in rows),
        'cross_counts': [{'status': key[0], 'termination_reason': key[1], 'outcome': key[2], 'count': count}
            for key, count in sorted(cross.items())],
        'batch_observations': [o for o in observations if isinstance(o, dict) and not o.get('run_id')],
        'semantics': {'missing': 'Unknown, never zero.',
            'outcome': 'Only source-declared semantics; no inference from values or completion.',
            'coverage': 'Supplied summaries, not original reading or causal proof.',
            'counter_scope': 'Execution totals only; nested durations and token scopes are not summed.'}}
