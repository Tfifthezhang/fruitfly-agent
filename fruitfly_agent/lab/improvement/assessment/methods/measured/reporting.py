"""Readable exports of one computed result; no second metric calculation."""
import csv
import io


def exports(result):
    lines = ['# Measured comparison', '', 'Conclusion: ' + result['conclusion'],
             '', 'This report does not activate a candidate.', '']
    metrics = io.StringIO(); table = csv.writer(metrics)
    table.writerow(['side', 'metric', 'value', 'numerator', 'denominator'])
    for side, data in result.get('metrics', {}).items():
        if side not in {'before', 'after'}:
            continue
        lines += ['## ' + side, '']
        for name in ('end_to_end_pass_rate', 'grading_coverage', 'conditional_pass_rate', 'error_rate', 'tool_error_rate'):
            metric = data[name]
            table.writerow([side, name, metric['value'], metric['numerator'], metric['denominator']])
            lines.append(f"- {name}: {metric['value']} ({metric['numerator']}/{metric['denominator']})")
        lines.append('')
        for name in ('official_score', 'agent_seconds', 'model_calls', 'cost_usd'):
            metric = data[name]
            table.writerow([side, name, metric.get('mean', metric.get('total')), '',
                            metric.get('known_count')])
            lines.append(f'- {name}: {metric}')
        table.writerow([side, 'cost_per_success_usd', data['cost_per_success_usd'], '', ''])
        lines.append('')
    if 'gain_pp' in result:
        lines += ['Gain (percentage points): ' + str(result['gain_pp']),
                  'Paired task interval: ' + str(result['confidence_interval']),
                  'Outcome transitions: ' + str(result['metrics']['transitions']),
                  'Status transitions: ' + str(result['metrics']['status_transitions']), '']
    lines += ['## Evidence limits', '', *('- ' + x for x in result.get('limits', []))]
    if 'comparability' in result:
        lines += ['', 'Comparability: ' + result['comparability'],
                  'Data status: ' + result['data_status'],
                  'Excluded: ' + str(result['coverage']['excluded'])]
    tasks = io.StringIO(); writer = csv.writer(tasks)
    writer.writerow(['task', 'attempt', 'before_run', 'after_run', 'before_status', 'after_status',
                     'before_outcome', 'after_outcome', 'comparability', 'delivery_gain'])
    for row in result.get('pairs', []):
        writer.writerow([row.get('origin_id', row.get('task_id')), row['attempt'],
            row['before']['run_id'], row['after']['run_id'], row['before']['status'], row['after']['status'],
            row['before']['outcome'], row['after']['outcome'], row.get('comparability', row.get('comparable')),
            row.get('delivery_gain', row.get('gain'))])
    return {'summary.md': ('\n'.join(lines) + '\n', 'text/markdown'),
            'metrics.csv': (metrics.getvalue(), 'text/csv'), 'tasks.csv': (tasks.getvalue(), 'text/csv')}
