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
    def test_default_discovery_excludes_tool_parameters_but_explicit_grants_remain_legal(self):
        from dataclasses import replace
        from fruitfly_agent.lab.improvement.execution import builtin_executions, ExecutionRegistry
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            experiment = workspace(root)
            path = root / '.fruitfly/default-config.yaml'
            data = yaml.safe_load(path.read_text())
            for name in ('local-env', 'bash-tool'):
                data['profiles']['baseline']['H'][name] = {'inline': {
                    'id': name, 'implementation': name, 'role': 'H', 'parameters': {}}}
            path.write_text(yaml.safe_dump(data))
            document = yaml.safe_load(experiment.read_text())
            document.pop('edit')
            experiment.write_text(yaml.safe_dump(document))
            definition = builtin_executions().get('agent-task')
            executions = ExecutionRegistry((replace(definition, capabilities=definition.capabilities | {'tool:bash', 'configuration-materialization'}),))
            with patch('fruitfly_agent.experiments.composition.builtin_executions', return_value=executions), \
                    patch('fruitfly_agent.experiments.validation.builtin_executions', return_value=executions), \
                    patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                prepared = prepare_experiment(load_configuration(root), 'improvement')
                self.assertNotIn('tool-catalog', prepared.request.component_ids)
                self.assertNotIn('bash-tool', prepared.request.component_ids)
                row = next(c for c in prepared.harness['editable_components'] if c['id'] == 'bash-tool')
                self.assertTrue(row['available'])
                self.assertFalse(row['default_selected'])
                document['edit'] = {'bash-tool': {'fields': ['parameters.settings.default_timeout_seconds']}}
                experiment.write_text(yaml.safe_dump(document))
                explicit = prepare_experiment(load_configuration(root), 'improvement')
                self.assertEqual(explicit.request.component_ids, ('bash-tool',))

    def test_absent_components_are_rejected_before_provider_construction(self):
        for name in ('tool-guidance.read', 'skill-document'):
            with self.subTest(component=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace(root, improvement={'components': [name]})
                with patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('Provider constructed')):
                    with self.assertRaisesRegex(ValueError, 'unknown mechanism|absent'):
                        prepare_experiment(load_configuration(root), 'improvement')

    def test_inventory_reports_enabled_state_without_granting_permission_to_modify_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            path = root / '.fruitfly/default-config.yaml'
            data = yaml.safe_load(path.read_text())
            for name in ('local-env', 'read-tool', 'skills'):
                data['profiles']['baseline']['H'][name] = {'default': True}
            data['profiles']['baseline']['S']['skill-library'] = {'default': True}
            path.write_text(yaml.safe_dump(data))
            summary = prepare_experiment(load_configuration(root), 'improvement').summary()
            memory = next(c for c in summary['harness']['editable_components'] if c['id'] == 'skill-library')
            self.assertFalse(memory['available'], 'the selected backend cannot materialize retained content')
            self.assertFalse(memory['selected'])
            self.assertEqual(summary['request']['component_ids'], ['base_prompt'])

    def test_execution_policy_cannot_be_granted_for_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root, improvement={'components':['execution-policy']})
            with self.assertRaisesRegex(ValueError, 'not editable|absent|unknown|grant|surface|component'):
                prepare_experiment(load_configuration(root), 'improvement')
