"""Measured reports preserve planned scopes, attribution and error semantics."""
from dataclasses import replace
import csv
import io
import unittest

from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.observations import BatchManifest, PlannedAttempt, MeasurementObservation
from fruitfly_agent.improvement.contracts.research import ObservationSemantics, ResearchBatch
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.versions import content_hash
from fruitfly_agent.lab.improvement.assessment.methods.measured.policy import compare_batches
from fruitfly_agent.lab.improvement.assessment.methods.measured.reporting import exports


def batch(states, *, prefix='before', attempts=1):
    tasks = tuple(TaskMaterial('task-' + str(i), 'Work ' + str(i)) for i in range(len(states)))
    identity = content_hash('fixed conditions')
    plan = BatchManifest(tuple(PlannedAttempt(t.task_id, a) for t in tasks for a in range(attempts)))
    records, observations = [], [plan.to_dict()]
    for task, status in zip(tasks, states):
        for attempt in range(attempts):
            if status == 'M':
                continue
            run = prefix + '-' + task.task_id + '-' + str(attempt)
            records.append(ExecutionRecord(run, task.task_id, task.material_id, content_hash(prefix), identity,
                identity, 'error' if status == 'E' else 'completed', model_calls=2))
            observations.append(MeasurementObservation(run, task.task_id, attempt, 'reward',
                1 if status in {'P', 'E'} else 0, status != 'E',
                ObservationSemantics({'P': 'met', 'F': 'unmet', 'E': 'unknown'}[status], 'higher'),
                identity, identity, content_hash(run), raw_value=1 if status == 'E' else None,
                error={'type': 'AgentTimeoutError'} if status == 'E' else None, elapsed_seconds=10,
                comparison={'material': task.material_id, 'conditions': identity, 'initial_state': identity,
                            'source': 'Frozen test backend'}, cost_usd=.1).to_dict())
    return ResearchBatch(tasks, tuple(records), tuple(observations))


class ComparisonReportTests(unittest.TestCase):
    def test_frozen_source_loads_comparison_defaults_without_checkout_fallback(self):
        import tempfile
        import subprocess
        import sys
        from pathlib import Path
        from fruitfly_agent.run.storage.snapshots import capture_source_tree
        source = capture_source_tree(Path(__file__).resolve().parents[2])
        self.assertIn('fruitfly_agent/lab/improvement/assessment/methods/measured/defaults.yaml',
                      {f.path for f in source.files})
        with tempfile.TemporaryDirectory() as directory:
            frozen = Path(directory)
            for entry in source.files:
                destination = frozen / entry.path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(entry.content)
            code = '''import sys, pathlib
sys.path.insert(0, sys.argv[1])
from fruitfly_agent.lab.improvement.assessment.registration import normalize
import fruitfly_agent.lab.improvement.assessment.registration as owner
assert pathlib.Path(owner.__file__).is_relative_to(sys.argv[1])
settings = normalize({})['settings']
assert settings['method'] == 'measured'
assert settings['bootstrap_resamples'] == 2000
'''
            result = subprocess.run([sys.executable, '-I', '-c', code, str(frozen)],
                cwd=frozen, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed37_keeps_error_recoveries_and_valid_grading_separate(self):
        before = batch('F' * 6 + 'E' * 31)
        after = batch('PFFEEE' + 'P' * 4 + 'F' * 3 + 'E' * 24, prefix='after')
        result = compare_batches(before, after, ['before', 'after'])
        a, b = result['metrics']['before'], result['metrics']['after']
        self.assertEqual(a['confirmed_successes'], 0)
        self.assertEqual(b['confirmed_successes'], 5)
        self.assertEqual(a['grading_coverage']['numerator'], 6)
        self.assertEqual(b['grading_coverage']['numerator'], 10)
        self.assertEqual(a['error_rate']['numerator'], 31)
        self.assertEqual(b['error_rate']['numerator'], 27)
        self.assertEqual(result['metrics']['transitions']['unknown->met'], 4)
        self.assertIsNone(result['metrics']['success_retention']['value'])
        self.assertAlmostEqual(result['gain_pp'], 500 / 37)
        self.assertEqual(b['cost_usd']['known_count'], 37)
        self.assertEqual(result['usage']['comparison_model_calls'], 0)
        self.assertEqual(result['confidence_interval'], compare_batches(before, after, [])['confidence_interval'])

    def test_missing_attempt_does_not_shrink_the_denominator(self):
        result = compare_batches(batch('PF'), batch('PM', prefix='after'), [])
        data = result['metrics']['after']
        self.assertEqual(data['planned'], 2)
        self.assertEqual(data['observed'], 1)
        self.assertIsNone(data['end_to_end_pass_rate']['value'])
        self.assertEqual(result['data_status'], 'partial')
        self.assertIsNone(result['confidence_interval'])

    def test_missing_former_success_keeps_retention_unknown(self):
        result = compare_batches(batch('PP'), batch('PM', prefix='after'), [])
        retention = result['metrics']['success_retention']
        self.assertEqual(retention['denominator'], 2)
        self.assertEqual(retention['known_count'], 1)
        self.assertIsNone(retention['value'])
        self.assertIsNone(result['metrics']['success_regression']['value'])

    def test_usage_totals_exclude_turn_subtotals_and_keep_tool_coverage(self):
        from fruitfly_agent.improvement.contracts.tasks import Resource
        before = batch('FF')
        before = replace(before, records=tuple(replace(r, artifacts=(
            Resource('execution-facts.json', content_hash(r.run_id), 'application/json', 'diagnostic'),))
            for r in before.records))
        def read(resource):
            return {'usage': [{'resource': 'input_tokens', 'scope': 'execution', 'used': 10},
                             {'resource': 'input_tokens', 'scope': 'turn', 'used': 999}],
                    'counters': [['tool_attempts', 4], ['tool_errors', 1]]}
        report = compare_batches(before, batch('PP', prefix='after'), [], read=read)
        metrics = report['metrics']['before']
        self.assertEqual(metrics['usage']['input_tokens']['total'], 20)
        self.assertEqual(metrics['tool_error_rate']['value'], .25)
        self.assertEqual(report['metrics']['after']['tool_error_rate']['value'], None)

    def test_explicit_subset_and_mismatched_conditions(self):
        before, after = batch('FFFF'), batch('PP', prefix='after')
        with self.assertRaisesRegex(ValueError, 'task-attempt scopes differ'):
            compare_batches(before, after, [])
        result = compare_batches(before, after, [], scope=after)
        self.assertEqual(result['coverage']['excluded'], {'before': 2, 'after': 0})
        observations = list(after.observations)
        observations[1] = {**observations[1], 'comparison': {
            **observations[1]['comparison'], 'conditions': content_hash('different')}}
        result = compare_batches(before, replace(after, observations=tuple(observations)), [], scope=after)
        self.assertEqual(result['comparability'], 'mismatch')
        self.assertEqual(result['conclusion'], 'insufficient')
        self.assertEqual(result['observed_effect'], 'improved')

    def test_repeated_attempts_are_grouped_by_task_and_exports_share_results(self):
        result = compare_batches(batch('FF', attempts=3), batch('PP', prefix='after', attempts=3), [])
        self.assertEqual(result['confidence_interval']['tasks'], 2)
        self.assertEqual(result['coverage']['planned'], 6)
        self.assertEqual(result['conclusion'], 'better')
        output = exports(result)
        metric = next(r for r in csv.DictReader(io.StringIO(output['metrics.csv'][0]))
                      if r['side'] == 'after' and r['metric'] == 'end_to_end_pass_rate')
        self.assertEqual(float(metric['value']), 1)
        self.assertEqual(int(metric['denominator']), 6)
        self.assertEqual(len(output['tasks.csv'][0].splitlines()), 7)

    def test_unknown_provenance_does_not_hide_descriptive_results(self):
        before, after = batch('FF'), batch('PP', prefix='after')
        after = replace(after, observations=(after.observations[0], *(
            {**o, 'comparison': {}, 'scorer_id': None} for o in after.observations[1:])))
        result = compare_batches(before, after, [])
        self.assertEqual(result['comparability'], 'unknown')
        self.assertEqual(result['conclusion'], 'insufficient')
        self.assertEqual(result['metrics']['after']['confirmed_successes'], 2)
