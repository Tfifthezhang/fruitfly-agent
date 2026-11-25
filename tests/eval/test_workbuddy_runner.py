"""Official-shaped execution results flow from the real adapter into import/compare."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_eval.benchmarks.workbuddy import WorkBuddyCodeAdapter
from fruitfly_eval.benchmarks.harbor import harbor_descriptor
from fruitfly_eval.catalog import BenchmarkCatalog
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.execution import execute_request
from fruitfly_eval.harbor.material import tree_identity
from fruitfly_eval.improvement.history import import_history
from fruitfly_eval.workbuddy.configuration import runner_identity
from fruitfly_eval.workbuddy.hooks import WorkBuddyEvidencePlugin
from fruitfly_eval.workbuddy.runner import job_configuration
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.assessment.methods.measured.policy import compare_batches
from tests.support.workbuddy import fixture, Engine


class WorkBuddyRunnerTests(unittest.TestCase):
    def test_official_task_cannot_reuse_another_selected_tasks_attribution(self):
        from fruitfly_eval.workbuddy.results import read_results
        from fruitfly_eval.improvement.measurement_context import FILENAME
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / 'job'; trial = job / 'trial'; trial.mkdir(parents=True)
            (job / 'result.json').write_text('{}')
            (trial / 'result.json').write_text(json.dumps({'task_name': 'second'}))
            (trial / FILENAME).write_text(json.dumps({'origin_id': 'code:first', 'attempt': 0,
                'scorer_id': 'sha256:' + 'a' * 64, 'comparison': {
                    **{key: 'sha256:' + 'a' * 64 for key in ('material', 'conditions', 'initial_state')},
                    'source': 'Frozen fixture'}}))
            with self.assertRaisesRegex(ValueError, 'attribution differ'):
                read_results(job / 'result.json', {'dataset': 'code', 'tasks': [
                    {'name': 'first', 'id': 'first'}, {'name': 'second', 'id': 'second'}]}, {},
                    config_path=root / 'config', models_path=root / 'models')

    def test_native_model_configuration_and_official_results_enter_measured_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            host = fixture(root)
            client = Engine()
            runner_python = root / 'controller/bin/python'
            runner_python.parent.mkdir(parents=True)
            runner_python.write_text('fixture interpreter')
            runner_python.with_name('harbor').write_text('fixture CLI')
            settings = SimpleNamespace(python=runner_python, checkout=root / 'workbuddy')
            dataset = host.task_directory
            tasks = []
            for path in sorted((dataset / 'tasks').iterdir()):
                tasks.append({'id': path.name, 'name': 'workbuddy/' + path.name, 'path': str(path),
                    'sha256': tree_identity(path), 'configuration': {'environment': {'docker_image': 'fixture/code:v1'}}})
            receipt = {'id': 'prepared-fixture', 'dataset': 'wb-bench-code-v1.0', 'tasks': tasks,
                'runner': runner_identity(root / 'workbuddy'), 'engine': {'sha256': 'fixture-engine'},
                'bench': {'timeout_multiplier': 2.5, 'environment': {}},
                'dataset_material': {'root': str(dataset)}, 'runtime': {'source': str(root),
                    'host': host.identity(), 'mounts': [], 'installation': {'version': '0.1'}}}
            adapter = WorkBuddyCodeAdapter()
            adapter.descriptor = harbor_descriptor(benchmark_id='fixture-wb', label='Fixture', description='Fixture',
                dataset='wb-bench-code-v1.0', version='1.0', smoke_task='first')
            request = EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'fixture-wb', 'variant': 'full'}})
            rewards = iter((0, 1))
            def execute(command, *, environment, job_root, **kwargs):
                import yaml
                job = yaml.safe_load((job_root / 'harbor-job.yaml').read_text())
                self.assertEqual(job['agents'][0]['import_path'], 'fruitfly_eval.workbuddy.agent:WorkBuddyFruitFlyAgent')
                self.assertEqual(job['retry'], {'max_retries': 0})
                self.assertIn('EXPERIMENT_TEST_KEY', job['agents'][0]['kwargs']['secret_names'])
                self.assertNotIn('offline-placeholder', json.dumps(job))
                effective = yaml.safe_load((job_root / 'config.yaml').read_text())
                self.assertIn('H', effective['profiles'][effective['default_profile']])
                job_dir = job_root / 'workbuddy'
                job_dir.mkdir()
                hooks = WorkBuddyEvidencePlugin()
                callbacks = {}
                class Job:
                    def __init__(self): self.job_dir = job_dir
                    def on_agent_started(self, f): callbacks['agent_start'] = f
                    def on_agent_ended(self, f): callbacks['agent_end'] = f
                    def on_trial_ended(self, f): callbacks['end'] = f
                    def on_trial_cancelled(self, f): callbacks['cancel'] = f
                    def on_trial_started(self, f): callbacks['start'] = f
                asyncio.run(hooks.on_job_start(Job()))
                reward = next(rewards)
                for index, task in enumerate(tasks):
                    name = 'trial-' + str(index)
                    trial = job_dir / name
                    event = SimpleNamespace(config=SimpleNamespace(trials_dir=job_dir, trial_name=name,
                        task=SimpleNamespace(get_local_path=lambda p=task['path']: Path(p))))
                    asyncio.run(callbacks['start'](event))
                    agent = trial / 'agent'; agent.mkdir()
                    (agent / 'session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Implement ' + task['name']}}) + '\n')
                    (trial / 'result.json').write_text(json.dumps({'id': name, 'task_name': task['name'],
                        'verifier_result': {'rewards': {'reward': reward}}}))
                (job_dir / 'result.json').write_text(json.dumps({'n_total_trials': len(tasks)}))
                return 0, ''
            artifacts = MemoryArtifacts()
            batches = []
            with patch.object(WorkBuddyCodeAdapter, 'preflight', return_value=SimpleNamespace(available=True)), \
                 patch('fruitfly_eval.workbuddy.runner.WorkBuddyPreparation.load', return_value=receipt), \
                 patch('fruitfly_eval.workbuddy.runner.WorkBuddyPreparation.inspect', return_value={'available': True}), \
                 patch('fruitfly_eval.workbuddy.runner.engine', return_value=client), \
                 patch('fruitfly_eval.workbuddy.runner.settings', return_value=settings), \
                 patch('fruitfly_eval.workbuddy.runner.run_harbor_job', side_effect=execute):
                for side in ('before', 'after'):
                    report, store = execute_request(request, output_root=root / side,
                        catalog=BenchmarkCatalog((adapter,)), host_config_path=str(host.path))
                    self.assertEqual(report.status, 'completed')
                    batches.append(import_history(store.path, artifacts))
            compared = compare_batches(*batches, ['before', 'after'])
            self.assertEqual(compared['coverage']['planned'], 2)
            self.assertEqual(compared['metrics']['after']['confirmed_successes'], 2)
            self.assertEqual(compared['comparability'], 'verified')
            self.assertEqual(compared['conclusion'], 'better')
            self.assertEqual(compared['usage']['comparison_model_calls'], 0)
