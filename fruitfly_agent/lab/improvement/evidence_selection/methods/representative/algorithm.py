"""Bound detailed investigation while preserving the full summary distribution."""
from collections import Counter
from dataclasses import asdict
from ...configuration import SelectionSettings
from ..focused import trajectory_material
from ....evidence.statistics import declared_outcomes
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
            outcomes = declared_outcomes(row)
            if 'unmet' in outcomes:
                reasons.append('outcome_unmet')
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
            if ('met' in outcomes
                    and not set(reasons) - {'unknown_diagnostics'}):
                controls.append(row)
            signals[row['run_id']] = reasons
        frequencies = Counter(s for reasons in signals.values() for s in reasons)
        chosen: list[dict] = []
        counts: Counter[str] = Counter()
        def add(row, reasons, limit):
            if len(chosen) >= limit or counts[row['task_id']] >= settings.max_per_task:
                return False
            chosen.append({'run_id': row['run_id'], 'task_id': row['task_id'], 'reasons': reasons})
            counts[row['task_id']] += 1
            return True
        # Known outcome controls remain distinct from unscored contrasting cases.
        control_label = 'successful_control'
        if not controls and any(signals.values()):
            controls = [row for row in summaries if row['status'] == 'completed'
                and not set(declared_outcomes(row)) - {'unknown'} and not signals[row['run_id']]]
            control_label = 'contrasting_control'
        # Reserve controls, then cover distinct execution/outcome strata before filling.
        for row in sorted(controls, key=lambda r: (r['task_id'], r['run_id'])):
            add(row, [control_label, *signals[row['run_id']]], min(settings.controls, settings.max_cases))
        ranked = sorted((r for r in summaries if signals[r['run_id']] or settings.sampling_policy == 'all'), key=lambda r: (
            min((frequencies[s] for s in signals[r['run_id']]), default=0), r['task_id'], r['run_id']))
        if settings.sampling_policy == 'balanced':
            covered = {(r['status'], tuple(sorted(set(declared_outcomes(r)))))
                for r in summaries if any(c['run_id'] == r['run_id'] for c in chosen)}
            for row in ranked:
                stratum = (row['status'], tuple(sorted(set(declared_outcomes(row)))))
                if stratum not in covered:
                    if add(row, signals[row['run_id']], settings.max_cases):
                        covered.add(stratum)
        for task_round in range(settings.max_per_task):
            for row in ranked:
                if counts[row['task_id']] > task_round or any(c['run_id'] == row['run_id'] for c in chosen):
                    continue
                add(row, signals[row['run_id']], settings.max_cases)
        selected = {c['run_id'] for c in chosen}
        by_run = {row['run_id']: row for row in summaries}
        control_cases = [case for case in chosen if any(reason in case['reasons']
            for reason in ('successful_control', 'contrasting_control'))]
        for case in chosen:
            row = by_run[case['run_id']]
            identity_fields = ('harness_id', 'conditions_id', 'initial_state_id')
            comparable = [control['run_id'] for control in control_cases if control['run_id'] != case['run_id']
                and all(bool(row.get(field)) and row.get(field) == by_run[control['run_id']].get(field)
                    for field in identity_fields)]
            case['control_run_ids'] = comparable
            case['comparison_basis'] = ('shared_recorded_harness_conditions_state' if comparable else 'not_established')
        if resources is not None:
            for case in chosen:
                granted = resources.get(case['run_id'], ())
                focused_names = {'execution-facts.json', 'operations.json', 'termination.json',
                    'final-answer.json', 'task.json', 'model-usage.json', 'process.json', 'trajectory-status.json',
                    'overview.json', 'coverage.json', 'sources.json', 'events.json', 'history.json', 'outcome.json'}
                case['material_paths'] = [r.path for r in granted if settings.material_policy == 'all-granted'
                    or trajectory_material(r) or (settings.material_policy == 'focused' and
                    (r.path.startswith('diagnostics/configuration/') or r.kind == 'deliverable'
                     or r.path.rsplit('/', 1)[-1] in focused_names))]
                case['omitted_materials'] = len(granted) - len(case['material_paths'])
        return {'selector_id': self.identity, 'implementation_id': self.implementation_id,
                'settings': asdict(settings), 'selected': chosen,
                'total_executions': len(summaries), 'signal_counts': dict(frequencies),
                'signal_meanings': {'outcome_unmet': 'A source explicitly declares unmet acceptance.',
                    'successful_control': 'A source declares met acceptance; process signals remain separate.',
                    'contrasting_control': 'Completed unscored comparison; success is unknown.',
                    'unknown_diagnostics': 'Diagnostics are missing or incomplete, not a demonstrated defect.'},
                'omitted_executions': len(summaries) - len(selected),
                'limits': ['Signals identify investigation leads, not causes.',
                           'No quality inference from receipt completion or low call counts.',
                           'Unselected originals require a new explicit investigation grant.']}
