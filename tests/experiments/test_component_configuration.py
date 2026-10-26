"""Slim experiments consume the same H/S/I config as ordinary Run."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from fruitfly_agent.experiments.scaffolding import initialize_workspace
from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment


class ComponentExperimentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        initialize_workspace(self.root)
        self.directory = self.root / '.fruitfly'

    def change(self, name, update):
        path = self.directory / name
        value = yaml.safe_load(path.read_text())
        update(value)
        path.write_text(yaml.safe_dump(value, sort_keys=False))

    def prepare(self):
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
            return prepare_experiment(load_configuration(self.root), 'improvement', require_credentials=False)

    def test_component_search_and_feedback_are_consumed_and_grants_are_visible(self):
        self.change('components/I/improvement-search.yaml', lambda value: value['parameters'].update(rounds=2))
        self.change('components/I/improvement-feedback.yaml', lambda value: value['parameters'].update(
            process_assessment={'assessors': ['execution-facts-v1']}))
        self.change('experiment.yaml', lambda value: value['edit'].update({'execution-policy': {
            'fields': ['parameters.max_tool_calls_per_turn'],
            'bounds': {'parameters.max_tool_calls_per_turn': {'minimum': 32, 'maximum': 128}}}}))
        prepared = self.prepare()
        self.assertEqual(prepared.request.depth, 2)
        self.assertEqual(prepared.config.process_assessment.assessors, ('execution-facts-v1',))
        self.assertIn('execution-policy', prepared.request.component_ids)
        self.assertEqual(prepared.config.improvement.component_options['execution-policy']['editable_fields'],
                         ['max_tool_calls_per_turn'])
        self.assertNotIn('offline-placeholder', json.dumps(prepared.summary()))

    def test_referenced_component_and_comparison_changes_invalidate_prepared_inputs(self):
        for name in ('components/H/execution-policy.yaml', 'components/I/improvement-search.yaml', 'comparison.yaml'):
            with self.subTest(name=name):
                prepared = self.prepare()
                path = self.directory / name
                path.write_text(path.read_text() + '\n')
                with self.assertRaisesRegex(ValueError, 'changed'):
                    prepared.verify_sources()

    def test_unknown_or_unauthorized_field_grants_and_outside_bounds_fail_offline(self):
        original = (self.directory / 'experiment.yaml').read_text()
        for name, grant in (
            ('base_prompt', {'fields': ['models.executor']}),
            ('execution-policy', {'fields': ['parameters.max_turns'], 'bounds': {'parameters.max_turns': {'minimum': 100}}}),
            ('improvement-feedback', {'fields': ['parameters.process_assessment.max_model_calls']})):
            with self.subTest(name=name):
                (self.directory / 'experiment.yaml').write_text(original)
                self.change('experiment.yaml', lambda value: value.update(edit={name: grant}))
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_inspection_and_conversion_are_offline_and_preserve_sources(self):
        from fruitfly_agent.run.configuration.inspection import inspect_configuration
        from fruitfly_agent.run.configuration.conversion import convert_configuration
        source = self.directory / 'default-config.yaml'
        destination = self.root / 'export'
        original = source.read_bytes()
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
            inspected = inspect_configuration(source)
            preview = convert_configuration(source, destination)
            self.assertEqual(preview['status'], 'preview')
            self.assertFalse(destination.exists())
            convert_configuration(source, destination, apply=True)
            exported = inspect_configuration(destination / 'config.yaml')
        self.assertEqual(inspected['models'], exported['models'])
        self.assertEqual(source.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            convert_configuration(source, destination, apply=True)
