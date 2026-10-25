"""Offline checks reject impossible edit scopes before constructing a Provider."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment
from tests.support.experiments import workspace


class HarnessValidationTests(unittest.TestCase):
    def test_absent_components_are_rejected_before_provider_construction(self):
        for name in ('tool-guidance.read', 'skill-document', 'learned-memory'):
            with self.subTest(component=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace(root, improvement={'components': [name]})
                with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                    with self.assertRaisesRegex(ValueError, 'absent'):
                        prepare_experiment(load_configuration(root), 'improvement')

    def test_inventory_reports_enabled_state_without_granting_permission_to_modify_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            path = root / '.fruitfly/default-config.yaml'
            data = yaml.safe_load(path.read_text())
            data['profiles']['baseline']['mechanisms'] = [{'id': 'learned-memory'}]
            path.write_text(yaml.safe_dump(data))
            summary = prepare_experiment(load_configuration(root), 'improvement').summary()
            memory = next(c for c in summary['harness']['editable_components'] if c['id'] == 'learned-memory')
            self.assertTrue(memory['available'])
            self.assertFalse(memory['selected'])
            self.assertEqual(summary['request']['component_ids'], ['base_prompt'])

    def test_execution_options_are_checked_and_included_in_resolved_experiment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root, improvement={'components': ['execution-policy'], 'component_options': {
                'execution-policy': {'editable_fields': ['max_tool_calls_per_turn'],
                                     'bounds': {'max_tool_calls_per_turn': {'minimum': 32, 'maximum': 256}}}}})
            summary = prepare_experiment(load_configuration(root), 'improvement').summary()
            self.assertEqual(summary['execution']['max_tool_calls_per_turn'], 64)
            self.assertIn('execution-config', summary['harness']['backend_capabilities'])
            selected = [c['id'] for c in summary['harness']['editable_components'] if c['selected']]
            self.assertEqual(selected, ['execution-policy'])
