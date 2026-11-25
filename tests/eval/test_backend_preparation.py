"""Independent preparation owners share Eval entry points without Harbor dispatch."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_eval.backends import preparation_backend
from fruitfly_eval.benchmarks.base import BenchmarkDescriptor, BenchmarkVariant, PreflightResult
from fruitfly_eval.catalog import BenchmarkCatalog
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.service import prepare_evaluation, check_evaluation, stop_evaluation
from fruitfly_eval.task_selection import list_prepared_tasks
from fruitfly_eval.execution import execute_request


class FixturePreparation:
    def __init__(self):
        self.calls = []
        self.receipt = {'id': 'fixture-plan', 'tasks': [{'id': 'first'}, {'id': 'second'}]}

    def read_host(self, workspace, path):
        self.calls.append(('host', workspace, path))
        return SimpleNamespace(path=path)

    def prepare(self, request, descriptor, host, *, package, tasks_only, progress):
        self.calls.append(('prepare', tasks_only, package))
        return {'task_count': 2}

    def inspect(self, request, descriptor, host, *, receipt=None):
        self.calls.append(('inspect', receipt))
        return {'available': True}

    def load(self, host, descriptor, variant):
        return self.receipt


class FixtureAdapter:
    descriptor = BenchmarkDescriptor('fixture', 'Fixture', 'Independent backend', '1', '1',
        (BenchmarkVariant('full', 'Full', 'All fixture tasks'),), (), 'fixture/tasks', {}, 'fixture')

    def __init__(self):
        self.preparation = FixturePreparation()
        self.host_path = None

    def configure_host(self, path):
        self.host_path = path

    def preflight(self, variant):
        return PreflightResult(False, ({'id': 'fixture', 'ok': False, 'detail': 'offline'},))

    def run(self, **kwargs):
        raise AssertionError('no external execution authorized')


class BackendPreparationTests(unittest.TestCase):
    def test_stop_dispatches_only_to_the_recorded_backend_control(self):
        import json
        from unittest.mock import Mock
        adapter = FixtureAdapter()
        adapter.control = SimpleNamespace(stop=Mock(return_value={'state': 'finished'}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            evaluation = root / 'owned'
            evaluation.mkdir()
            (evaluation / 'request.json').write_text(json.dumps({'benchmark': {'id': 'fixture', 'variant': 'full'}}))
            result = stop_evaluation('owned', output_root=root, catalog=BenchmarkCatalog((adapter,)))
            self.assertEqual(result['state'], 'finished')
            adapter.control.stop.assert_called_once_with(evaluation)
            del adapter.control
            with self.assertRaisesRegex(ValueError, 'scoped execution control'):
                stop_evaluation('owned', output_root=root, catalog=BenchmarkCatalog((adapter,)))

    def test_independent_backend_prepares_checks_and_lists_selected_tasks(self):
        adapter = FixtureAdapter()
        catalog = BenchmarkCatalog((adapter,))
        request = EvaluationRequest.from_dict({'benchmark': {'id': 'fixture', 'variant': 'full',
                                               'task_names': ['second']}})
        with patch('fruitfly_eval.harbor.host.HostConfig.read', side_effect=AssertionError('Harbor accessed')), \
             patch('fruitfly_eval.installation.resolve_installation', side_effect=AssertionError('unneeded install')):
            self.assertEqual(prepare_evaluation(request, catalog=catalog, tasks_only=True), {'task_count': 2})
            checked = check_evaluation(request, catalog=catalog)
            self.assertTrue(checked['available'])
            self.assertEqual(checked['task_names'], ['second'])
            with patch('fruitfly_eval.task_selection.builtin_catalog', return_value=catalog):
                listed = list_prepared_tasks(request, host_config_path='independent.yaml')
            self.assertEqual(listed['tasks'], [{'id': 'second'}])
        self.assertEqual(adapter.preparation.receipt['tasks'], [{'id': 'first'}, {'id': 'second'}])
        self.assertEqual(adapter.preparation.calls[-1][-1], 'independent.yaml')

    def test_missing_capability_and_unknown_selection_reject_before_execution(self):
        with self.assertRaisesRegex(ValueError, 'preparation capabilities'):
            preparation_backend(SimpleNamespace())
        adapter = FixtureAdapter()
        request = EvaluationRequest.from_dict({'benchmark': {'id': 'fixture', 'variant': 'full',
                                               'task_names': ['missing']}})
        checked = check_evaluation(request, catalog=BenchmarkCatalog((adapter,)))
        self.assertFalse(checked['available'])
        self.assertIn('outside', checked['checks'][0]['detail'])

    def test_host_configuration_is_a_capability_not_a_backend_type(self):
        adapter = FixtureAdapter()
        with tempfile.TemporaryDirectory() as directory:
            report, _ = execute_request(EvaluationRequest.from_dict({'benchmark': {
                'id': 'fixture', 'variant': 'full'}}), output_root=Path(directory),
                catalog=BenchmarkCatalog((adapter,)), host_config_path='independent.yaml')
        self.assertEqual(adapter.host_path, 'independent.yaml')
        self.assertEqual(report.status, 'blocked')
