"""Measured outcomes, missingness and accounting keep distinct denominators."""
from collections import Counter
from statistics import mean


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def delivery(cell):
    if cell['status'] == 'missing':
        return None
    if cell['outcome'] == 'met':
        return 1
    if cell['outcome'] == 'unmet' or cell['status'] in {'error', 'cancelled', 'timeout'}:
        return 0
    return None


def side_metrics(rows, side, read=None):
    cells = [r[side] for r in rows]
    observed = sum(c['status'] != 'missing' for c in cells)
    known = sum(c['outcome'] in {'met', 'unmet'} for c in cells)
    successes = sum(c['outcome'] == 'met' for c in cells)
    deliveries = [delivery(c) for c in cells]
    by_task: dict[str, list] = {}
    for row, value in zip(rows, deliveries):
        by_task.setdefault(row['origin_id'], []).append(value)
    complete = all(v is not None for v in deliveries) and bool(cells)
    elapsed = [c['elapsed_seconds'] for c in cells if c['elapsed_seconds'] is not None]
    calls = [c['model_calls'] for c in cells if c['model_calls'] is not None]
    accounting: dict[str, list] = {}
    counters: dict[str, list] = {}
    for cell in cells:
        resources = [r for r in cell['artifacts'] if r['path'] == 'execution-facts.json']
        if read is None or not resources:
            continue
        from fruitfly_agent.improvement.contracts.tasks import Resource
        facts = read(Resource(**resources[0]))
        for item in facts.get('usage', []):
            if item['scope'] == 'execution' and item.get('used') is not None:
                accounting.setdefault(item['resource'], []).append(item['used'])
        for name, value in facts.get('counters', []):
            if value is not None:
                counters.setdefault(name, []).append(value)
    def totals(values):
        return {'known_total': sum(values), 'known_count': len(values), 'population': len(cells),
                'total': sum(values) if len(values) == len(cells) and cells else None}
    cost = totals([c['cost_usd'] for c in cells if c['cost_usd'] is not None])
    tool_attempts, tool_errors = counters.get('tool_attempts', []), counters.get('tool_errors', [])
    tool_rate = ratio(sum(tool_errors), sum(tool_attempts))
    tool_rate['known_count'] = min(len(tool_attempts), len(tool_errors))
    if not cells or len(tool_attempts) != len(cells) or len(tool_errors) != len(cells):
        tool_rate['value'] = None
    return {'planned': len(cells), 'observed': observed,
        'confirmed_successes': successes,
        'end_to_end_pass_rate': {**ratio(successes, len(cells)),
            'value': mean(mean(v) for v in by_task.values()) if complete else None,
            'aggregation': 'task-macro', 'complete': complete},
        'grading_coverage': ratio(sum(c['value'] is not None for c in cells), len(cells)),
        'known_outcomes': known, 'conditional_pass_rate': ratio(successes, known),
        'official_score': {'mean': mean(c['value'] for c in cells if c['value'] is not None)
            if any(c['value'] is not None for c in cells) else None,
            'known_count': sum(c['value'] is not None for c in cells)},
        'error_rate': ratio(sum(c['status'] in {'error', 'cancelled', 'timeout'} for c in cells), observed),
        'errors': dict(Counter((c['measurement'].get('error') or {}).get('type', c['status'])
            for c in cells if c['status'] in {'error', 'cancelled', 'timeout'} and c['measurement'])),
        'agent_seconds': totals(elapsed), 'model_calls': totals(calls),
        'usage': {k: totals(v) for k, v in accounting.items()},
        'counters': {k: totals(v) for k, v in counters.items()},
        'cost_usd': cost, 'tool_error_rate': tool_rate,
        'cost_per_success_usd': cost['total'] / successes
            if complete and successes and cost['total'] is not None else None}


def summarize(rows, read=None):
    transitions: Counter[str] = Counter()
    retained = regressed = before_met = retention_known = 0
    status_transitions: Counter[str] = Counter()
    for row in rows:
        a, b = row['before'], row['after']
        transitions[a['outcome'] + '->' + b['outcome']] += 1
        status_transitions[a['status'] + '->' + b['status']] += 1
        x, y = delivery(a), delivery(b)
        row['delivery_gain'] = y - x if x is not None and y is not None else None
        if a['outcome'] == 'met':
            before_met += 1
            retention_known += y is not None
            retained += b['outcome'] == 'met'
            regressed += y == 0
    retention, regression = ratio(retained, before_met), ratio(regressed, before_met)
    for metric in (retention, regression):
        metric['known_count'] = retention_known
        if retention_known != before_met:
            metric['value'] = None
    numeric = [r['after']['value'] - r['before']['value'] for r in rows
               if r['before']['value'] is not None and r['after']['value'] is not None
               and r['comparability'] != 'mismatch']
    return {'before': side_metrics(rows, 'before', read), 'after': side_metrics(rows, 'after', read),
            'transitions': dict(transitions), 'status_transitions': dict(status_transitions),
            'paired_score_difference': {'mean': mean(numeric) if numeric else None,
                                        'known_count': len(numeric), 'population': len(rows)},
            'success_retention': retention, 'success_regression': regression}
