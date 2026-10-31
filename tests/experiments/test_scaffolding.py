"""Fresh workspaces need no private project state, models or task downloads."""
import builtins
from contextlib import redirect_stderr, redirect_stdout
import io
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.cli import main
from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.scaffolding import initialize_workspace, workspace_templates


class ScaffoldingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_native_init_and_check_work_without_eval_or_providers(self):
        original_import = builtins.__import__

        def without_eval(name, *args, **kwargs):
            if name == 'fruitfly_eval' or name.startswith('fruitfly_eval.'):
                raise AssertionError('native init imported Eval')
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with patch('builtins.__import__', side_effect=without_eval), \
             patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('model')), \
             patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'offline-placeholder'}, clear=True), \
             redirect_stdout(output):
            self.assertEqual(main(['--cwd', str(self.root), 'init', '--json']), 0)
            initialized = json.loads(output.getvalue())
            self.assertEqual(len(initialized['created']), len(workspace_templates()) + 1)
            self.assertEqual(initialized['preserved'], [])
            output.seek(0); output.truncate()
            self.assertEqual(main(['improvement', 'check', '--cwd', str(self.root), '--json']), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary['model_roles'], dict.fromkeys(('executor', 'editor', 'assessor'), 'deepseek-flash-openai'))
        self.assertNotIn('offline-placeholder', output.getvalue())
        self.assertEqual((self.root / '.fruitfly/secrets.env').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / '.fruitfly').stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.root / '.fruitfly/config.yaml').exists())
        self.assertFalse((self.root / '.fruitfly/experiments/runs').exists())

    def test_benchmark_init_uses_catalog_and_works_from_another_process_directory(self):
        from fruitfly_eval.benchmarks.terminal_bench_4 import TerminalBench4Adapter
        from fruitfly_eval.contracts import EvaluationRequest
        from fruitfly_eval.harbor.host import HostConfig
        output = io.StringIO()
        with patch.object(TerminalBench4Adapter, 'preflight', side_effect=AssertionError('preflight')), \
             patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('model')), \
             redirect_stdout(output):
            self.assertEqual(main(['init', '--cwd', str(self.root), '--source', 'task-set',
                '--benchmark', 'terminal-bench-4', '--json']), 0)
        config = load_configuration(self.root)
        self.assertEqual(config.task['source'], 'task-set')
        self.assertEqual(config.multi_task.execution.concurrency, 1)
        row = config.task['collections'][0]
        request = EvaluationRequest.read(config.resolve(row['request']))
        self.assertEqual(request.benchmark.benchmark_id, 'terminal-bench-4')
        self.assertEqual(request.runtime.working_directory, '.')
        self.assertEqual(request.execution.attempts, 1)
        self.assertEqual(request.execution.concurrency, 1)
        with patch.dict(os.environ, {'FRUITFLY_EVAL_PYTHON_ROOT': '/opt/fixture-python',
                                   'FRUITFLY_EVAL_VENV': '/opt/fixture-agent'}, clear=True):
            host = HostConfig.read(self.root, config.resolve(row['host']))
            self.assertEqual(host.cache, self.root / '.fruitfly/eval-cache')
            with patch('fruitfly_eval.api.prepare_evaluation', return_value={'task_count': 1}) as prepare, \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--cwd', str(self.root), 'eval', 'prepare', '--tasks-only']), 0)
            actual_request = prepare.call_args.args[0]
            self.assertEqual(actual_request.runtime.working_directory, str(self.root))
            self.assertEqual(Path(actual_request.runtime.config_path), self.root / '.fruitfly/default-config.yaml')
        self.assertEqual(len(json.loads(output.getvalue())['created']),
                         len(workspace_templates(source='task-set', benchmark='terminal-bench-4')) + 1)

    def test_generated_task_set_checks_with_prepared_material_from_another_directory(self):
        from fruitfly_eval.improvement.configuration import resolve_benchmark
        from dataclasses import replace
        initialize_workspace(self.root, source='task-set', benchmark='terminal-bench-4')
        config = load_configuration(self.root)
        collection = config.task['collections'][0]
        instruction = self.root / 'prepared-task'
        instruction.mkdir()
        (instruction / 'instruction.md').write_text('Offline fixture task, without private grading.')
        project = Path(__file__).resolve().parents[2]
        source_files = [(str(path.relative_to(project)), hashlib.sha256(path.read_bytes()).hexdigest())
            for package in ('fruitfly_agent', 'fruitfly_eval') for path in (project / package).rglob('*.py')]
        resource = 'fruitfly_agent/run/configuration/templates/components/H/execution-policy.yaml'
        source_files.append((resource, hashlib.sha256((project / resource).read_bytes()).hexdigest()))
        prepared = {'id': 'offline-prepared-fixture',
            'tasks': [{'id': 'terminal-bench/interleaved-vigenere', 'path': str(instruction)}],
            'runtime': {'installation': {'files': source_files}}}
        output = io.StringIO()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'offline-placeholder',
                'FRUITFLY_EVAL_PYTHON_ROOT': '/opt/fixture-python',
                'FRUITFLY_EVAL_VENV': '/opt/fixture-agent'}, clear=True), \
             patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('model')), \
             patch('fruitfly_eval.improvement.task_sets.load_preparation', return_value=prepared), \
             redirect_stdout(output):
            resolve_benchmark(replace(config, task={k: v for k, v in collection.items() if k != 'id'})).stage_host()
            self.assertNotEqual(Path.cwd().resolve(), self.root)
            self.assertEqual(main(['--cwd', str(self.root), 'improvement', 'check', '--json']), 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary['task_set']['collections'][0]['tasks'], 1)
            self.assertEqual(summary['multi_task']['execution']['concurrency'], 1)
            self.assertIn('base_prompt', summary['request']['component_ids'])
            self.assertIn('working-memory-reduction', summary['request']['component_ids'])
            self.assertNotIn('improvement-editor', summary['request']['component_ids'])
            self.assertEqual(summary['execution']['max_tool_calls_per_turn'], 64)
            # Relative paths must still be inside the declared experiment workspace.
            request_path = config.resolve(collection['request'])
            request = json.loads(request_path.read_text())
            request['runtime']['working_directory'] = '..'
            request_path.write_text(json.dumps(request))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--cwd', str(self.root), 'improvement', 'check']), 2)

    def test_catalog_id_is_data_and_unknown_ids_or_invalid_flags_write_nothing(self):
        for source, benchmark, variant in (('task-set', 'swe-bench', 'smoke'),
                                           ('task-set', 'terminal-bench', 'full')):
            request = json.loads(workspace_templates(source=source, benchmark=benchmark, variant=variant)['eval-request.json'])
            self.assertEqual(request['benchmark'], {'id': benchmark, 'variant': variant})
        for options in ({'source': 'task-set'}, {'source': 'task-set', 'benchmark': 'not-registered'},
                        {'source': 'files', 'benchmark': 'terminal-bench-4'}, {'source': 'files', 'variant': 'full'},
                        {'source': 'task-set', 'benchmark': 'terminal-bench-4', 'variant': 'unknown'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                initialize_workspace(self.root, **options)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_collision_or_repeated_init_never_overwrites_or_adds_partial_files(self):
        directory = self.root / '.fruitfly'
        directory.mkdir()
        existing = directory / 'default-config.yaml'
        existing.write_text('user settings and comments\n')
        with self.assertRaisesRegex(ValueError, 'will not overwrite'):
            initialize_workspace(self.root)
        self.assertEqual(list(directory.iterdir()), [existing])
        self.assertEqual(existing.read_text(), 'user settings and comments\n')
        existing.unlink()
        initialize_workspace(self.root)
        before = {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'will not overwrite'):
            initialize_workspace(self.root)
        self.assertEqual(before, {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*') if p.is_file()})

    def test_existing_daily_files_and_secret_are_preserved_without_reading_secret(self):
        directory = self.root / '.fruitfly'
        directory.mkdir()
        for name in ('config.yaml', 'models.yaml', 'secrets.env'):
            (directory / name).write_text('existing offline fixture\n')
        secret = directory / 'secrets.env'
        secret.chmod(0o600)
        original = secret.stat()
        result = initialize_workspace(self.root)
        self.assertEqual(result['preserved'], [str(directory / 'models.yaml'), str(secret)])
        self.assertEqual(len(result['created']), len(workspace_templates()) - 1)
        self.assertEqual(secret.stat(), original)
        for name in ('config.yaml', 'models.yaml', 'secrets.env'):
            self.assertEqual((directory / name).read_text(), 'existing offline fixture\n')

    def test_daily_and_experiment_select_distinct_models_from_existing_shared_catalog(self):
        from fruitfly_agent.run.configuration.profile import load_harness_config
        from fruitfly_agent.run.configuration.resolution import model_catalog_path, resolve_profile_models
        directory = self.root / '.fruitfly'
        directory.mkdir()
        models = directory / 'models.yaml'
        spec = {'sdk': 'openai', 'protocol': 'responses', 'model': 'offline-model',
                'api_key_env': 'OFFLINE_KEY', 'context_window': 16000}
        models.write_text('# Keep my model catalog comments.\n' + yaml.safe_dump({
            'models': {'daily-model': spec, 'experiment-model': {**spec, 'model': 'offline-experiment'}}}))
        original = models.read_bytes()
        daily = directory / 'config.yaml'
        daily.write_text(yaml.safe_dump({'default_profile': 'daily', 'profiles': {'daily': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'daily-model'}},
            'H': {}, 'S': {}, 'I': {}}}}))
        daily_bytes = daily.read_bytes()
        result = initialize_workspace(self.root)
        self.assertIn(str(models), result['preserved'])
        baseline = directory / 'default-config.yaml'
        config = yaml.safe_load(baseline.read_text())
        self.assertEqual(config['profiles']['baseline']['models']['catalog'], 'models.yaml')
        config['profiles']['baseline']['models']['roles'] = dict.fromkeys(
            ('executor', 'editor', 'assessor'), 'experiment-model')
        baseline.write_text(yaml.safe_dump(config))
        daily_profile = load_harness_config(daily).select()
        baseline_profile = load_harness_config(baseline).select()
        self.assertEqual(model_catalog_path(daily_profile, daily), models)
        self.assertEqual(model_catalog_path(baseline_profile, baseline), models)
        self.assertEqual(resolve_profile_models(daily_profile, daily)[1], 'daily-model')
        self.assertEqual(resolve_profile_models(baseline_profile, baseline)[1], 'experiment-model')
        self.assertEqual(models.read_bytes(), original)
        self.assertEqual(daily.read_bytes(), daily_bytes)

    def test_shared_catalog_must_be_regular_and_failure_preserves_existing_files(self):
        directory = self.root / '.fruitfly'
        directory.mkdir()
        models = directory / 'models.yaml'
        models.symlink_to(self.root / 'absent-models.yaml')
        with self.assertRaisesRegex(ValueError, 'models.yaml must be a regular file'):
            initialize_workspace(self.root)
        self.assertEqual(list(directory.iterdir()), [models])
        models.unlink()
        models.mkdir()
        with self.assertRaisesRegex(ValueError, 'models.yaml must be a regular file'):
            initialize_workspace(self.root)
        self.assertEqual(list(directory.iterdir()), [models])

    def test_write_failure_keeps_reused_catalog_and_secret_intact(self):
        directory = self.root / '.fruitfly'
        directory.mkdir()
        for name in ('models.yaml', 'secrets.env'):
            (directory / name).write_text('existing offline fixture\n')
        original_open = os.open
        def fail_on_experiment(path, *args, **kwargs):
            if Path(path).name == 'experiment.yaml':
                raise OSError('offline simulated failure')
            return original_open(path, *args, **kwargs)
        with patch('fruitfly_agent.experiments.scaffolding.os.open', side_effect=fail_on_experiment):
            with self.assertRaisesRegex(OSError, 'simulated failure'):
                initialize_workspace(self.root)
        self.assertEqual({p.name for p in directory.iterdir()}, {'models.yaml', 'secrets.env'})
        for path in directory.iterdir():
            self.assertEqual(path.read_text(), 'existing offline fixture\n')

    def test_symlink_targets_and_nonfile_secrets_fail_before_writes(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        state = self.root / '.fruitfly'
        state.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'real workspace directory'):
            initialize_workspace(self.root)
        self.assertEqual(list(elsewhere.iterdir()), [])
        state.unlink(); state.mkdir()
        target = state / 'experiment.yaml'
        target.symlink_to(elsewhere / 'missing.yaml')
        with self.assertRaisesRegex(ValueError, 'will not overwrite'):
            initialize_workspace(self.root)
        target.unlink()
        (state / 'secrets.env').mkdir()
        with self.assertRaisesRegex(ValueError, 'regular file'):
            initialize_workspace(self.root)
        self.assertEqual([p.name for p in state.iterdir()], ['secrets.env'])

    def test_write_failure_rolls_back_only_created_files(self):
        original_open = os.open

        def fail_on_experiment(path, *args, **kwargs):
            if Path(path).name == 'experiment.yaml':
                raise OSError('offline simulated failure')
            return original_open(path, *args, **kwargs)

        with patch('fruitfly_agent.experiments.scaffolding.os.open', side_effect=fail_on_experiment):
            with self.assertRaisesRegex(OSError, 'simulated failure'):
                initialize_workspace(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cli_reports_configuration_errors_without_creating_run_records(self):
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--cwd', str(self.root), 'init', '--source', 'task-set']), 2)
            self.assertEqual(main(['--cwd', str(self.root), '--config', 'custom.yaml', 'init']), 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_public_examples_match_installed_templates_and_request_contract(self):
        project = Path(__file__).resolve().parents[2]
        templates = workspace_templates()
        expected = {
            'default-config.yaml': 'examples/configuration/default-config.example.yaml',
            'models.yaml': 'examples/configuration/models.example.yaml',
            'experiment.yaml': 'examples/experiments/native.example.yaml',
        }
        for name, path in expected.items():
            self.assertEqual(templates[name], (project / path).read_text())
        benchmark = workspace_templates(source='task-set', benchmark='terminal-bench-4')
        self.assertEqual(benchmark['experiment.yaml'], (project / 'examples/experiments/benchmark-smoke.example.yaml').read_text())
        self.assertEqual(benchmark['eval-host.yaml'], (project / 'examples/configuration/eval-host.example.yaml').read_text())
        self.assertEqual(json.loads(benchmark['eval-request.json']),
            json.loads((project / 'examples/experiments/tb4-smoke-request.example.json').read_text()))
