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
        (self.directory / 'experiment.yaml').write_text(yaml.safe_dump({
            'baseline': {'config': 'default-config.yaml'},
            'tasks': {'inline': {'source': 'files', 'instruction': 'Inspect the controlled task.'}},
        }))

    def change(self, name, update):
        path = self.directory / name
        value = yaml.safe_load(path.read_text())
        update(value)
        path.write_text(yaml.safe_dump(value, sort_keys=False))

    def prepare(self):
        from dataclasses import replace
        from fruitfly_agent.lab.improvement.execution import builtin_executions, ExecutionRegistry
        from tests.support.task_execution import TaskRunnerFixture
        definition = builtin_executions().get('agent-task')
        executions = ExecutionRegistry((replace(definition, capabilities=TaskRunnerFixture.capabilities),))
        with patch('fruitfly_agent.experiments.composition.builtin_executions', return_value=executions), \
                patch('fruitfly_agent.experiments.validation.builtin_executions', return_value=executions), \
                patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
            return prepare_experiment(load_configuration(self.root), 'improvement', require_credentials=False)

    def test_component_search_and_feedback_are_consumed_and_grants_are_visible(self):
        self.change('experiment.yaml', lambda value: value.update(stopping={'max_rounds': 2},
            evidence={'read': {'default_characters': 8000}}))
        self.change('experiment.yaml', lambda value: value.setdefault('edit', {}).update({'layered-compaction': {
            'fields': ['parameters.settings.tail_tokens'],
            'bounds': {'parameters.settings.tail_tokens': {'minimum': 256, 'maximum': 16384}}}}))
        prepared = self.prepare()
        self.assertEqual(prepared.request.rounds, 2)
        self.assertEqual(prepared.config.evidence_settings['read']['default_characters'], 8000)
        self.assertIn('layered-compaction', prepared.request.component_ids)
        self.assertEqual(prepared.config.improvement.component_options['layered-compaction']['editable_fields'],
                         ['parameters.settings.tail_tokens'])
        self.assertNotIn('offline-placeholder', json.dumps(prepared.summary()))

    def test_referenced_component_and_comparison_changes_invalidate_prepared_inputs(self):
        from fruitfly_agent.lab.catalog import builtin_catalog
        from fruitfly_agent.lab.catalog.defaults import read_default
        catalog = builtin_catalog()
        for component, role in (('execution-policy', 'H'), ('improvement-evaluator', 'I')):
            path = self.directory / (component + '.yaml')
            path.write_text(yaml.safe_dump(read_default(catalog, component)[0].to_dict()))
            self.change('default-config.yaml', lambda value, component=component, role=role:
                value['profiles']['baseline'][role].update({component: {'file': component + '.yaml'}}))
        for name in ('execution-policy.yaml', 'improvement-evaluator.yaml', 'experiment.yaml'):
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
            ('improvement-evaluator', {'fields': ['parameters.max_model_calls']})):
            with self.subTest(name=name):
                (self.directory / 'experiment.yaml').write_text(original)
                self.change('experiment.yaml', lambda value: value.update(edit={name: grant}))
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_inspection_and_export_are_offline_and_preserve_sources(self):
        from fruitfly_agent.run.configuration.inspection import inspect_configuration
        from fruitfly_agent.run.configuration.export import export_configuration
        source = self.directory / 'default-config.yaml'
        destination = self.root / 'export'
        original = source.read_bytes()
        with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider')):
            inspected = inspect_configuration(source)
            preview = export_configuration(source, destination)
            self.assertEqual(preview['status'], 'preview')
            self.assertFalse(destination.exists())
            export_configuration(source, destination, apply=True)
            exported = inspect_configuration(destination / 'config.yaml')
        self.assertEqual(inspected['models'], exported['models'])
        self.assertEqual(source.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            export_configuration(source, destination, apply=True)
