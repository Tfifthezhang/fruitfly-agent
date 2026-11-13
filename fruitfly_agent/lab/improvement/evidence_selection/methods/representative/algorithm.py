"""Bound detailed investigation while preserving the full summary distribution."""
from collections import Counter
from dataclasses import asdict
from ...configuration import SelectionSettings
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash


class RepresentativeSelector:
    implementation_id = 'representative-evidence-v1'

    def __init__(self, settings=None):
        self.settings = settings or SelectionSettings()

    @property
    def identity(self):
        return content_hash(canonical_json({'implementation': self.implementation_id,
                                           'settings': asdict(self.settings)}))

    def select(self, summaries, *, resources=None):
        if len({r['run_id'] for r in summaries}) != len(summaries):
            raise ValueError('selection requires distinct execution identities')
        settings = self.settings
        signals = {}
        controls = []
        for row in summaries:
            reasons = []
            if row['status'] != 'completed':
                reasons.append('execution_' + row['status'])
            # An official observation is separate from process completion. Never
            # interpret an unknown scorer's numeric direction as task success.
            rewards = [o.get('value', {}).get('reward') for o in row.get('observations', ())
                       if o.get('name') == 'official_reward' and isinstance(o.get('value'), dict)]
            if any(type(v) in (int, float) and v <= 0 for v in rewards):
                reasons.append('official_failure')
            if row.get('elapsed_seconds') is not None and row['elapsed_seconds'] >= settings.slow_seconds:
                reasons.append('high_elapsed')
            if row.get('model_calls') is not None and row['model_calls'] >= settings.many_calls:
                reasons.append('many_model_calls')
            tools = row.get('counters', {}).get('tool_started')
            if tools is not None and tools >= settings.many_tools:
                reasons.append('many_tool_steps')
            if any(u.get('scope') == 'execution' and u.get('resource') in {'input_tokens', 'output_tokens'}
                   and u.get('used') is not None and u['used'] >= settings.high_tokens for u in row.get('usage', ())):
                reasons.append('high_token_usage')
            if row.get('diagnostics_complete') is not True:
                reasons.append('unknown_diagnostics')
            if (any(type(v) in (int, float) and v > 0 for v in rewards)
                    and not set(reasons) - {'unknown_diagnostics'}):
                controls.append(row)
            signals[row['run_id']] = reasons
        frequencies = Counter(s for reasons in signals.values() for s in reasons)
        chosen: list[dict] = []
        counts: Counter[str] = Counter()
        def add(row, reasons, limit):
            if len(chosen) >= limit or counts[row['task_id']] >= settings.max_per_task:
                return
            chosen.append({'run_id': row['run_id'], 'task_id': row['task_id'], 'reasons': reasons})
            counts[row['task_id']] += 1
        # Reserve successful controls, then round-robin tasks by rare signals.
        for row in sorted(controls, key=lambda r: (r['task_id'], r['run_id'])):
            add(row, ['successful_control', *signals[row['run_id']]], min(settings.controls, settings.max_cases))
        ranked = sorted((r for r in summaries if signals[r['run_id']]), key=lambda r: (
            min(frequencies[s] for s in signals[r['run_id']]), r['task_id'], r['run_id']))
        for task_round in range(settings.max_per_task):
            for row in ranked:
                if counts[row['task_id']] > task_round or any(c['run_id'] == row['run_id'] for c in chosen):
                    continue
                add(row, signals[row['run_id']], settings.max_cases)
        selected = {c['run_id'] for c in chosen}
        if resources is not None:
            for case in chosen:
                granted = resources.get(case['run_id'], ())
                focused_names = {'execution-facts.json', 'operations.json', 'termination.json',
                    'final-answer.json', 'task.json', 'model-usage.json', 'process.json', 'trajectory-status.json'}
                case['material_paths'] = [r.path for r in granted if settings.material_policy == 'all-granted'
                    or r.kind in {'trajectory', 'deliverable'} or r.path.rsplit('/', 1)[-1] in focused_names]
                case['omitted_materials'] = len(granted) - len(case['material_paths'])
        return {'selector_id': self.identity, 'implementation_id': self.implementation_id,
                'settings': asdict(settings), 'selected': chosen,
                'total_executions': len(summaries), 'signal_counts': dict(frequencies),
                'omitted_executions': len(summaries) - len(selected),
                'limits': ['Signals identify investigation leads, not causes.',
                           'No quality inference from receipt completion or low call counts.',
                           'Unselected originals require a new explicit investigation grant.']}
