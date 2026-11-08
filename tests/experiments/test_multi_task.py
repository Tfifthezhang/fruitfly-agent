"""Actual Application task-set searches keep daily files and private material isolated."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from tests.support.experiments import workspace, Rule
from tests.support.task_packs import install
from tests.support.model_evaluation import RoleProvider


class BatchRule(Rule):
    supports_task_sets = True


class MultiTaskExperimentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from tests.support.task_execution import collection_registry
        self.enterContext(patch('fruitfly_agent.experiments.task_sets.registry_for', side_effect=collection_registry))


    def test_joint_check_is_provider_free_and_rejects_unsupported_parallelism(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'fixture', 'pack': 'project'}]},
                multi_task={'execution': {'candidate_concurrency': 2}})
            with self.assertRaisesRegex(ValueError, 'trial contains unknown fields'):
                load_configuration(root)

    def test_joint_check_preserves_material_and_supports_explicit_large_finite_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); install(root)
            workspace(root, task={'source': 'task-set', 'collections': [{'id': 'daily', 'source': 'fixture', 'pack': 'project'}]},
                improvement={'timeouts': {'editor_seconds': 20000, 'execution_seconds': 2000, 'evaluator_seconds': 1200}})
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                prepared = prepare_experiment(load_configuration(root), 'improvement')
            self.assertEqual(prepared.request.timeouts['editor_seconds'], 20000)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
