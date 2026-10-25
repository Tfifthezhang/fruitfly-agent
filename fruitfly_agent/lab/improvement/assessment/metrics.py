"""Incremental process/resource measurements without task-specific quality weights."""
from ..contracts.live import Assessment, Metric


class ProcessMetrics:
    assessor_id = 'execution-metrics-v1'

    def __init__(self):
        self.counts = {}
        self.last = {}

    def observe(self, event):
        p = event.position
        key = p.execution_id, p.version_id, p.segment_id
        if p.sequence == self.last.get(key, 0):
            return
        if p.sequence < self.last.get(key, 0):
            raise ValueError('process events must be strictly ordered')
        self.last[key] = p.sequence
        counts = self.counts.setdefault(key, {'tool_calls': 0, 'tool_errors': 0, 'model_calls': 0,
            'observable': False, 'input_tokens': 0, 'output_tokens': 0, 'responses': 0, 'usage_complete': True})
        if event.kind == 'started':
            counts['observable'] = bool(event.payload.get('process_events'))
        if event.kind == 'tool-finished':
            counts['tool_calls'] += 1
            counts['tool_errors'] += int(event.payload.get('is_error', False))
        if event.kind == 'model-request':
            counts['model_calls'] += 1
        if event.kind == 'model-response':
            counts['responses'] += 1
            values = [event.payload.get(name) for name in ('input_tokens', 'output_tokens')]
            if event.payload.get('usage_reported') and all(type(v) is int and v >= 0 for v in values):
                counts['input_tokens'] += values[0]
                counts['output_tokens'] += values[1]
            else:
                counts['usage_complete'] = False
        if event.kind == 'finished' and type(event.payload.get('model_calls')) is int:
            counts['model_calls'] = event.payload['model_calls']

    async def assess(self, event):
        self.observe(event)
        p = event.position
        counts = self.counts[p.execution_id, p.version_id, p.segment_id]
        final = event.kind in {'finished', 'failed', 'cancelled'}
        values = [Metric(name, value if counts['observable'] or name == 'model_calls' and
            type(event.payload.get('model_calls')) is int else None, 'count')
            for name, value in counts.items() if name in {'tool_calls', 'tool_errors', 'model_calls'}]
        complete = counts['observable'] and counts['usage_complete'] and counts['responses'] == counts['model_calls']
        values.extend(Metric(name, counts[name] if complete else None, 'tokens') for name in ('input_tokens', 'output_tokens'))
        values.append(Metric('elapsed_seconds', event.payload.get('elapsed_seconds'), 'seconds'))
        return Assessment(p, self.assessor_id, tuple(values),
            status='final' if final else 'provisional', scope='execution' if final else 'prefix')
