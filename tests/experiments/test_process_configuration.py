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
from fruitfly_agent.experiments.operations.improve import run
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
        self.assertEqual(old.summary()['execution']['max_tool_calls_per_turn'], 64)
        workspace(self.root, assessment={'evidence': {'page_characters': 8000}}, exploration={'policy': 'process-guided'})
        new = prepare_experiment(load_configuration(self.root), 'improvement')
        self.assertNotEqual(old.summary(), new.summary())
        self.assertEqual(new.summary()['exploration']['policy'], 'process-guided')

    async def test_cli_composition_drives_all_zero_search_with_a_separate_assessor_and_isolated_defaults(self):
        pack = package()
        install(self.root, pack)
        workspace(self.root, task={'source': 'files', 'pack': pack['id']},
            models={'assessor': 'assessor'}, improvement={'rounds': 2},
            exploration={'policy': 'process-guided'})
        provider = FauxProvider()
        def answer(view, signal=None):
            if view.model == 'offline-assessor':
                from tests.support.model_evaluation import judgment
                text = judgment(view).text
            else:
                text = 'wrong'
            async def stream(): yield StreamDone(AssistantMessage(content=[TextBlock(text)], stop_reason='stop'))
            return AssistantMessageEventStream(stream())
        provider.script = [answer] * 16
        registry = Mock(); registry.create.return_value = provider
        prepared = prepare_experiment(load_configuration(self.root), 'improvement')
        records = RunRecords(self.root)
        record = records.create('improvement', prepared.summary())
        original = prepared.config_path.read_bytes()
        def build(prepared, runtime_path):
            factory = application_factory(prepared, runtime_path, provider_registry=registry)
            generators = GeneratorRegistry(); generators.register('agent-editor-v1', Rule)
            return type(factory)(cwd=self.root, environment=prepared.environment, config_path=str(runtime_path),
                provider_registry=registry, improvement_bindings=replace(factory.improvement_bindings, generators=generators))
        with patch('fruitfly_agent.experiments.operations.improve.application_factory', side_effect=build):
            result = await run(prepared, record, records, lambda event: None)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['usage'], {'model': 9, 'execution': 3})
        self.assertEqual(prepared.config_path.read_bytes(), original)
        outcome = json.loads(next((self.root / '.fruitfly/improvement/jobs').glob('*/result.json')).read_text())
        self.assertEqual(outcome['selected']['run_id'], outcome['records'][-1]['run_id'])
        self.assertEqual(outcome['exploration'][0]['run_id'], outcome['records'][1]['run_id'])
        self.assertIn('Exploration seed', result['links'])
        self.assertEqual(sum(c['model'] == 'offline-assessor' for c in provider.calls), 6)
