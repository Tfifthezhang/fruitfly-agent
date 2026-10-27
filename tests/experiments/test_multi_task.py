"""Actual Application task-set searches keep daily files and private material isolated."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.operations.improve import run
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.lab.improvement.api import GeneratorRegistry
from fruitfly_agent.run import RunApplicationFactory
from tests.support.experiments import workspace, Rule
from tests.support.task_packs import install
from tests.support.faux_provider import FauxProvider


class BatchRule(Rule):
    supports_task_sets = True


class MultiTaskExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_task_set_runs_through_normal_application_and_retains_every_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'files', 'pack': 'project'}]})
            prepared = prepare_experiment(load_configuration(root), 'improvement')
            records = RunRecords(root)
            record = records.create('improvement', prepared.summary())
            provider = FauxProvider()
            for text in ('wrong', 'A', 'wrong', 'B'): provider.respond_text(text)
            registry = Mock(); registry.create.return_value = provider
            def builder(prepared, path):
                initial = application_factory(prepared, path, provider_registry=registry)
                generators = GeneratorRegistry(); generators.register(BatchRule.generator_id, BatchRule)
                return RunApplicationFactory(cwd=root, config_path=str(path), environment=prepared.environment,
                    provider_registry=registry, improvement_bindings=replace(initial.improvement_bindings, generators=generators))
            original = prepared.config_path.read_bytes()
            with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=builder):
                result = await run(prepared, record, records, lambda event: None)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['usage'], {'model': 4, 'execution': 4})
            self.assertEqual(prepared.config_path.read_bytes(), original)
            self.assertIn('Official evaluation', record['links'])
            job = root / record['links']['Component job']
            output = json.loads((job / 'result.json').read_text())
            self.assertEqual(output['selected']['assessment']['score'], 1)
            self.assertTrue(list((job / 'executions').glob('*.json')))
            self.assertTrue(list((job / 'evaluations').glob('*.json')))
            self.assertTrue(list((job / 'comparisons').glob('*.json')))
            self.assertFalse(any('UNSEEN_INPUT' in call['messages'][0].content or 'SECRET_ANSWER' in call['system_prompt'] for call in provider.calls))

    def test_joint_check_is_provider_free_and_rejects_unsupported_parallelism(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'files', 'pack': 'project'}]},
                multi_task={'execution': {'candidate_concurrency': 2}})
            with self.assertRaisesRegex(ValueError, 'trial contains unknown fields'):
                load_configuration(root)

    def test_joint_check_preserves_material_and_supports_explicit_large_finite_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'files', 'pack': 'project'}]},
                improvement={'max_model_calls': 20000, 'max_executions': 2000})
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                prepared = prepare_experiment(load_configuration(root), 'improvement')
            self.assertEqual(prepared.request.max_model_calls, 20000)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
