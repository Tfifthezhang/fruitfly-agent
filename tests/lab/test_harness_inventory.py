"""Configured owners, execution support and edit permission remain distinct."""
from dataclasses import replace
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock

from fruitfly_agent.lab.catalog import (builtin_catalog, resolve_harness, ComponentSpec,
    MechanismDefinition, MechanismDescriptor, MechanismContribution, MechanismEffects, MechanismSelection)
from fruitfly_agent.lab.execution_policy import ExecutionPolicyTarget
from fruitfly_agent.runtime_spec import HarnessProfile, execution_kwargs


class HarnessInventoryTests(unittest.TestCase):
    def test_disabled_owners_have_no_editable_state_or_tool_components(self):
        catalog = builtin_catalog()
        profile = HarnessProfile('baseline', mechanisms=(MechanismSelection('local-env'),))
        inventory = resolve_harness(profile, catalog)
        self.assertEqual(inventory.tools, ())
        self.assertFalse(any(c.role == 'S' or c.kind == 'tool-guidance' for c in inventory.components))
        for name in ('learned-memory', 'skill-document', 'tool-guidance.read'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'absent'):
                inventory.select((name,), frozenset({'execution-config'}), frozenset({'H', 'S'}))

    def test_enabled_state_and_tools_are_discovered_without_running_installers(self):
        catalog = builtin_catalog()
        selections = tuple(MechanismSelection(name) for name in ('local-env', 'read-tool', 'skill-document', 'learned-memory'))
        inventory = resolve_harness(HarnessProfile('baseline', mechanisms=selections), catalog)
        self.assertEqual(inventory.tools, ('read',))
        self.assertEqual({c.component_id for c in inventory.components if c.role == 'S'}, {'skill-document', 'learned-memory'})
        with self.assertRaisesRegex(ValueError, 'backend'):
            inventory.select(('tool-guidance.read',), frozenset(), frozenset({'H'}))
        selected = inventory.select(('base_prompt',), frozenset(), frozenset({'H'}))
        self.assertEqual([c.component_id for c in selected], ['base_prompt'])

    def test_new_owner_uses_generic_declarations_without_cli_or_tool_name_branches(self):
        installer = Mock(side_effect=AssertionError('installer ran during discovery'))
        definition = MechanismDefinition(MechanismDescriptor('fixture-owner', 'Fixture owner',
            'Provide an arbitrary offline fixture component.', contributions=(MechanismContribution('online', 'context', 'augmentation'),),
            effects=MechanismEffects(tools=('fixture-operation',))), installer,
            implementation_path=__file__, documentation_path='tests/lab/README.md',
            component_specs=lambda parameters, enabled: (ComponentSpec('fixture-state', 'S'),) if enabled else ())
        catalog = builtin_catalog().extended((definition,))
        enabled = resolve_harness(HarnessProfile('baseline', mechanisms=(MechanismSelection('fixture-owner'),)), catalog)
        disabled = resolve_harness(HarnessProfile('baseline'), catalog)
        self.assertIn('tool-guidance.fixture-operation', {c.component_id for c in enabled.components})
        self.assertIn('fixture-state', {c.component_id for c in enabled.components})
        self.assertNotIn('fixture-state', {c.component_id for c in disabled.components})
        installer.assert_not_called()

    def test_execution_policy_respects_field_permissions_ranges_and_other_owners(self):
        config = SimpleNamespace(**execution_kwargs({'max_tool_calls_per_turn': 256}))
        target = ExecutionPolicyTarget(config)
        options = {'editable_fields': ['max_tool_calls_per_turn'],
                   'bounds': {'max_tool_calls_per_turn': {'minimum': 64, 'maximum': 512}}}
        target.validate_options(options)
        value = json.loads(target.snapshot().text)
        target.validate_change(json.dumps({**value, 'max_tool_calls_per_turn': 128}), options)
        with self.assertRaisesRegex(ValueError, 'bounds'):
            target.validate_change(json.dumps({**value, 'max_tool_calls_per_turn': 1024}), options)
        with self.assertRaisesRegex(ValueError, 'fixed'):
            target.validate_change(json.dumps({**value, 'max_turns': 8}), options)
        owned = ExecutionPolicyTarget(config, fixed_fields={'max_turns'})
        with self.assertRaises(ValueError): owned.validate_options({'editable_fields': ['max_turns']})
