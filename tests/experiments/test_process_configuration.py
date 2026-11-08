"""File settings freeze process feedback and exploration without real models."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment, application_factory
from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from tests.support.experiments import workspace, Rule
from tests.support.faux_provider import FauxProvider
from tests.support.task_packs import install, package


class ProcessConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_invalid_process_dependencies_fail_during_provider_free_check(self):
        cases = (
            {'process_assessment': {'assessors': 'completed-model-v1'}},
            {'process_assessment': {'assessors': ['unknown']}},
            {'process_assessment': {'assessors': ['completed-model-v1'], 'max_model_calls': 0}},
            {'process_assessment': {'assessors': ['execution-facts-v1']}, 'exploration': {'policy': 'process-guided'}},
            {'process_assessment': {'required': True}},
            {'process_assessment': {'unknown': True}},
            {'exploration': {'policy': 'unknown'}},
        )
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider created')):
            for sections in cases:
                with self.subTest(sections=sections):
                    workspace(self.root, **sections)
                    with self.assertRaises(ValueError):
                        prepare_experiment(load_configuration(self.root), 'improvement')

    def test_evidence_settings_and_exploration_are_frozen(self):
        workspace(self.root)
        old = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertNotIn('process_assessment', old.summary())
        self.assertEqual(old.summary()['execution']['max_tool_calls_per_turn'], 512)
        workspace(self.root, evidence={'read': {'default_characters': 8000}})
        new = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertNotEqual(old.summary(), new.summary())
        self.assertEqual(new.summary()['evidence_settings']['read']['default_characters'], 8000)
