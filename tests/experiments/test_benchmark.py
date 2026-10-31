"""Optional benchmark composition derives bounded hosts without Docker or models."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment
from fruitfly_agent.experiments.cli import main
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.experiments.operations.evaluate import run
from fruitfly_eval.improvement.configuration import resolve_benchmark
from fruitfly_eval.harbor.host import HostConfig
from tests.support.experiments import workspace


class BenchmarkEntryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.config_path = workspace(self.root, task={'source': 'eval', 'request': '../request.json', 'host': '../host.yaml'})
        self.request = self.root / 'request.json'
        self.request.write_text(json.dumps({'runtime': {'working_directory': str(self.root)},
            'benchmark': {'id': 'terminal-bench-4', 'variant': 'smoke'}}))
        self.host = self.root / 'host.yaml'
        self.host.write_text(yaml.safe_dump({'cache': 'cache',
            'agent': {'python': '/opt/runtime/bin/python', 'mounts': [{'source': 'runtime', 'target': '/opt/runtime'}]},
            'environment': {'agent': {'LANG': 'C.UTF-8'}}}))

    def test_derived_host_keeps_paths_and_source_bytes_and_is_shared_by_check_and_run(self):
        config = load_configuration(self.root)
        original = self.host.read_bytes()
        benchmark = resolve_benchmark(config)
        self.assertFalse(benchmark.generated_host.exists())
        with self.assertRaisesRegex(ValueError, 'prepare'):
            benchmark.require_host()
        benchmark.stage_host()
        actual = HostConfig.read(self.root, benchmark.require_host())
        self.assertEqual(actual.agent_env, {'LANG': 'C.UTF-8'})
        self.assertEqual(actual.mounts[0].source, self.root / 'runtime')
        self.assertEqual(actual.cache, self.root / 'cache')
        self.assertEqual(self.host.read_bytes(), original)
        again = resolve_benchmark(config)
        self.assertEqual(again.require_host(), benchmark.generated_host)

    def test_tasks_only_preparation_needs_no_agent_configuration_or_credentials(self):
        (self.root / '.fruitfly/default-config.yaml').unlink()
        (self.root / '.fruitfly/secrets.env').unlink()
        with patch('fruitfly_eval.api.prepare_evaluation', return_value={'task_count': 1}) as prepare, redirect_stdout(io.StringIO()):
            code = main(['--cwd', str(self.root), 'eval', 'prepare', '--tasks-only'])
        self.assertEqual(code, 0)
        self.assertTrue(prepare.call_args.kwargs['tasks_only'])
        self.assertIn('experiments/prepared', str(prepare.call_args.kwargs['host_config_path']))

    def test_explicit_request_supports_material_preparation_without_experiment_file(self):
        self.config_path.unlink()
        (self.root / '.fruitfly/eval-request.json').write_bytes(self.request.read_bytes())
        (self.root / '.fruitfly/eval-host.yaml').write_bytes(self.host.read_bytes())
        with patch('fruitfly_eval.api.prepare_evaluation', return_value={'task_count': 1}) as prepare, redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--cwd', str(self.root), '--request', str(self.request), 'eval', 'prepare', '--tasks-only']), 0)
        self.assertEqual(prepare.call_args.args[0].benchmark.benchmark_id, 'terminal-bench-4')

    def test_eval_ignores_editor_model_selection_and_never_calls_search(self):
        data = yaml.safe_load(self.config_path.read_text())
        data['comparison']['inline']['scope'] = 'persistent'
        system_path = self.root / '.fruitfly/default-config.yaml'
        system = yaml.safe_load(system_path.read_text())
        system['profiles']['baseline']['models']['roles']['editor'] = 'editor'
        system_path.write_text(yaml.safe_dump(system))
        self.config_path.write_text(yaml.safe_dump(data))
        config = load_configuration(self.root)
        resolve_benchmark(config).stage_host()
        with patch('fruitfly_eval.api.check_evaluation', return_value={'available': True}):
            prepared = prepare_experiment(config, 'eval')
        self.assertEqual(prepared.model_roles, {'executor': 'executor'})
        records = RunRecords(self.root)
        record = records.create('eval', prepared.summary())
        report = SimpleNamespace(evaluation_id='evaluation', status='completed')
        with patch('fruitfly_eval.api.run_evaluation', return_value=(report, SimpleNamespace(path=self.root / 'report'))) as execute:
            result = run(prepared, record, records, lambda event: None)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(execute.call_args.kwargs['output_root'], self.root / '.fruitfly/eval')
        self.assertFalse((self.root / '.fruitfly/improvement/jobs').exists())

    def test_search_rejects_multiple_attempts_and_tasks_before_model_work(self):
        data = json.loads(self.request.read_text())
        data['execution'] = {'attempts': 2}
        self.request.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'one attempt'):
            prepare_experiment(load_configuration(self.root), 'improvement', require_prepared=False)
        data['execution'] = {'attempts': 1}
        self.request.write_text(json.dumps(data))
        resolve_benchmark(load_configuration(self.root)).stage_host()
        with patch('fruitfly_eval.api.check_evaluation', return_value={'available': True, 'task_count': 2}):
            with self.assertRaisesRegex(ValueError, 'one prepared task'):
                prepare_experiment(load_configuration(self.root), 'improvement')

    def test_benchmark_reward_cannot_start_rsi_and_insufficient_search_budget_fails_early(self):
        with self.assertRaisesRegex(ValueError, 'independent verifier'):
            prepare_experiment(load_configuration(self.root), 'rsi', require_prepared=False)
        data = yaml.safe_load(self.config_path.read_text())
        data['budget'] = {'max_model_calls': 80}
        self.config_path.write_text(yaml.safe_dump(data))
        with self.assertRaisesRegex(ValueError, 'unknown fields'):
            prepare_experiment(load_configuration(self.root), 'improvement', require_prepared=False)
