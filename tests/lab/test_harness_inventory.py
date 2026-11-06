"""Configured owners, execution support and edit permission remain distinct."""

from fruitfly_agent.lab.catalog import FeatureNode
from dataclasses import replace
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock

from fruitfly_agent.lab.catalog import (builtin_catalog, resolve_harness, ComponentSpec,
    MechanismDefinition, MechanismDescriptor, MechanismContribution, MechanismEffects, MechanismSelection)
from fruitfly_agent.lab.catalog.adapters.parameters import ParameterTarget
from fruitfly_agent.runtime_spec import HarnessProfile, execution_kwargs


class HarnessInventoryTests(unittest.TestCase):
    def test_disabled_owners_have_no_editable_state_or_tool_components(self):
        catalog = builtin_catalog()
        profile = HarnessProfile('baseline', mechanisms=(MechanismSelection('local-env'),))
        inventory = resolve_harness(profile, catalog)
        self.assertEqual(inventory.tools, ())
        self.assertFalse(any(c.role == 'S' or c.kind == 'tool-guidance' for c in inventory.components))
        for name in ('skill-document', 'tool-guidance.read'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'absent'):
                inventory.select((name,), frozenset({'execution-config'}), frozenset({'H', 'S'}))

    def test_enabled_state_and_tools_are_discovered_without_running_installers(self):
        catalog = builtin_catalog()
        selections = tuple(MechanismSelection(name) for name in ('local-env', 'read-tool', 'skills'))
        inventory = resolve_harness(HarnessProfile('baseline', mechanisms=selections), catalog)
        self.assertEqual(inventory.tools, ('read',))
        self.assertEqual({c.component_id for c in inventory.components if c.role == 'S'}, {'skill-library'})
        with self.assertRaisesRegex(ValueError, 'backend'):
            inventory.select(('read-tool',), frozenset(), frozenset({'I'}))
        selected = inventory.select(('base_prompt',), frozenset(), frozenset({'H'}))
        self.assertEqual([c.component_id for c in selected], ['base_prompt'])

    def test_new_owner_uses_generic_declarations_without_cli_or_tool_name_branches(self):
        installer = Mock(side_effect=AssertionError('installer ran during discovery'))
        definition = MechanismDefinition(MechanismDescriptor('fixture-owner', 'Fixture owner',
            'Provide an arbitrary offline fixture component.', contributions=(MechanismContribution('online', 'context', 'augmentation'),),
            effects=MechanismEffects(tools=('fixture-operation',))), installer,
            implementation_path=__file__, documentation_path='tests/lab/README.md',
            component_specs=lambda parameters, enabled: (ComponentSpec('fixture-state', 'S'),) if enabled else (), feature_path=(FeatureNode('fixture', 'Fixture'),))
        catalog = builtin_catalog().extended((definition,))
        enabled = resolve_harness(HarnessProfile('baseline', mechanisms=(MechanismSelection('fixture-owner'),)), catalog)
        disabled = resolve_harness(HarnessProfile('baseline'), catalog)
        self.assertIn('base_prompt', {c.component_id for c in enabled.components})
        self.assertNotIn('tool-catalog', {c.component_id for c in enabled.components})
        self.assertFalse(any(c.component_id.startswith('tool-guidance.') for c in enabled.components))
        self.assertIn('fixture-state', {c.component_id for c in enabled.components})
        self.assertNotIn('fixture-state', {c.component_id for c in disabled.components})
        from fruitfly_agent.lab.catalog import LabCatalog
        tool_only = replace(definition, component_specs=None)
        with self.assertRaisesRegex(ValueError, 'no optimization component'):
            resolve_harness(HarnessProfile('baseline', mechanisms=(MechanismSelection('fixture-owner'),)),
                LabCatalog((tool_only,)))
        installer.assert_not_called()

    def test_owner_parameter_grants_respect_fields_ranges_and_protected_values(self):
        target=ParameterTarget(builtin_catalog().get('bash-tool'), {}, {'default_timeout_seconds'})
        field='parameters.settings.default_timeout_seconds'
        options={'editable_fields':[field],'bounds':{field:{'minimum':1,'maximum':1200}}}
        target.validate_options(options)
        value=json.loads(target.snapshot().text);value['settings']['default_timeout_seconds']=2
        target.validate_change(json.dumps(value),options)
        value['settings']['default_timeout_seconds']=1250
        with self.assertRaisesRegex(ValueError,'bounds'):target.validate_change(json.dumps(value),options)
        value=json.loads(target.snapshot().text);value['settings']['output_characters']=200
        with self.assertRaisesRegex(ValueError,'fixed'):target.validate_change(json.dumps(value),options)
        for field in ('parameters.settings.max_active_commands','parameters.settings.output_characters'):
            with self.assertRaises(ValueError):target.validate_options({'editable_fields':[field]})
