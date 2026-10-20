"""Object-owned instruction changes retain runtime behavior and immutable scope."""
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.lab.algorithms.components import ComponentTarget
from fruitfly_agent.lab.algorithms.targets import TargetSnapshot, canonical_json, target_edits
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.tools.guidance import ToolGuidanceTarget
from fruitfly_agent.lab.tools.read import create_read_tool
from tests.support.faux_provider import FauxProvider


class ComponentTargetTests(unittest.TestCase):
    def setUp(self):
        self.tool = create_read_tool()
        self.target = ComponentTarget('instructions', 'Instructions',
            (BasePromptTarget('Original instructions'), ToolGuidanceTarget(self.tool)))

    def test_single_and_joint_edits_preserve_tools_and_parent(self):
        config = AgentLoopConfig(provider=FauxProvider(), system_prompt='Original instructions', tools=(self.tool,))
        for keys in (('base_prompt',), ('tool-guidance.read',), ('base_prompt', 'tool-guidance.read')):
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

    def test_invalid_scope_types_and_oversized_guidance_are_rejected(self):
        values = json.loads(self.target.snapshot().text)
        for data in ({}, {**values, 'unknown': 'x'}, {**values, 'tool-guidance.read': {}},
                     {**values, 'tool-guidance.read': 'x' * 6001}):
            with self.subTest(data=list(data)), self.assertRaises(ValueError):
                self.target.validate(canonical_json(data))
        mixed = ComponentTarget('mixed', 'Mixed',
            (BasePromptTarget('base'), replace_snapshot_role(ToolGuidanceTarget(self.tool))))
        self.assertEqual({p.role for p in mixed.snapshot().components}, {'H', 'S'})

    def test_candidate_size_limit_does_not_block_runtime_target_registration(self):
        tool = replace(self.tool, description='x' * 30_001)
        target = ComponentTarget('large', 'Large instructions', (ToolGuidanceTarget(tool),))
        self.assertEqual(json.loads(target.snapshot().text)['tool-guidance.read'], tool.description)
        target.validate(target.snapshot().text)
        with self.assertRaises(ValueError):
            target.validate(canonical_json({'tool-guidance.read': 'y' * 30001}))


def replace_snapshot_role(target):
    class OtherRole:
        def snapshot(self):
            return replace(target.snapshot(), role='S')
    return OtherRole()
