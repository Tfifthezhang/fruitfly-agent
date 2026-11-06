"""Joint component edits preserve operation contracts and immutable parent scope."""
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.lab.improvement.targets.bundle import ComponentTarget
from fruitfly_agent.lab.improvement.targets.retained import RetainedText
from fruitfly_agent.improvement.contracts.optimization import TargetSnapshot
from fruitfly_agent.improvement.contracts.text import target_edits
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.tools.methods.read.algorithm import create_read_tool
from tests.support.faux_provider import FauxProvider


class ComponentTargetTests(unittest.TestCase):
    def setUp(self):
        self.tool = create_read_tool()
        self.target = ComponentTarget('instructions', 'Instructions',
            (BasePromptTarget('Original instructions'),
             RetainedText('fixture-notes', 'Original note', 'Fixture note', 'fixture-v1', 12000)))

    def test_single_and_joint_edits_preserve_tools_and_parent(self):
        config = AgentLoopConfig(provider=FauxProvider(), system_prompt='Original instructions', tools=(self.tool,))
        for keys in (('base_prompt',), ('fixture-notes',), ('base_prompt', 'fixture-notes')):
            with self.subTest(keys=keys):
                values = json.loads(self.target.snapshot().text)
                values.update({key: 'Updated ' + key for key in keys})
                text = canonical_json(values)
                trial = self.target.prepare_trial(config, text)
                self.assertEqual({p.target_id for p, _ in target_edits(self.target.snapshot(), text)}, set(keys))
                self.assertIs(trial.tools[0].execute, self.tool.execute)
                self.assertEqual(trial.tools[0].parameters, self.tool.parameters)
                self.assertEqual(trial.tools[0].permission, self.tool.permission)
                self.assertEqual(config.system_prompt, 'Original instructions')
                self.assertEqual(config.tools[0].description, self.tool.description)
        self.assertEqual(TargetSnapshot.from_dict(self.target.snapshot().to_dict()), self.target.snapshot())
        self.assertEqual({p.role for p in self.target.snapshot().components}, {'H', 'S'})

    def test_invalid_scope_types_and_oversized_guidance_are_rejected(self):
        values = json.loads(self.target.snapshot().text)
        for data in ({}, {**values, 'unknown': 'x'}, {**values, 'fixture-notes': {}},
                     {**values, 'fixture-notes': 'x' * 12001}):
            with self.subTest(data=list(data)), self.assertRaises(ValueError):
                self.target.validate(canonical_json(data))

    def test_large_tool_descriptions_do_not_create_a_second_instruction_catalog(self):
        tool = replace(self.tool, description='x' * 30001)
        config = AgentLoopConfig(provider=FauxProvider(), tools=(tool,))
        target = BasePromptTarget('Base')
        trial = target.prepare_trial(config, 'Updated base')
        self.assertEqual(tool.description, trial.tools[0].description)
        self.assertIsNone(trial.readable_resources)
        self.assertEqual('Updated base', trial.system_prompt)
