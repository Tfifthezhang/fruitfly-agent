"""Shared configuration contracts have one owner and explicit baseline precedence."""
from dataclasses import fields
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig, ToolExecutionConfig
from fruitfly_agent.runtime_spec import (HarnessProfile, MechanismSelection, execution_values,
    runtime_reference, parse_execution)
from fruitfly_agent.run.configuration import HarnessProfile as RunProfile
from fruitfly_agent.lab.catalog import MechanismSelection as CatalogSelection


class RuntimeSpecTests(unittest.TestCase):
    def test_existing_public_imports_share_the_declarative_types(self):
        self.assertIs(HarnessProfile, RunProfile)
        self.assertIs(MechanismSelection, CatalogSelection)
        values = execution_values({})
        core_fields = {field.name: field for field in fields(AgentLoopConfig)}
        for name in ('max_turns', 'max_tool_calls_per_turn', 'max_context_recovery_attempts'):
            self.assertEqual(values[name], core_fields[name].default)
        self.assertEqual(values['tool_execution']['max_parallel'], ToolExecutionConfig().max_parallel)

    def test_inherited_baseline_is_used_and_conflicting_explicit_choices_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.assertEqual(runtime_reference(root, inherited_path='custom.yaml', inherited_profile='chosen'),
                (root / 'custom.yaml', 'chosen'))
            self.assertEqual(runtime_reference(root, 'custom.yaml', 'chosen', inherited_path=root / 'custom.yaml'),
                (root / 'custom.yaml', 'chosen'))
            with self.assertRaisesRegex(ValueError, 'configurations differ'):
                runtime_reference(root, 'other.yaml', inherited_path='custom.yaml')
            with self.assertRaisesRegex(ValueError, 'profiles differ'):
                runtime_reference(root, profile='other', inherited_profile='chosen')

    def test_duplicate_and_non_scalar_execution_values_are_rejected(self):
        for text in ('{"max_turns":2,"max_turns":3}', '{"tool_execution":{"default_execution_mode":[]}}',
                     '{"provider":"arbitrary"}', '{"max_tool_calls_per_turn":1.5}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_execution(text)
