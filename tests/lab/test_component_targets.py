"""Object-owned instruction changes retain runtime behavior and immutable scope."""
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core import AgentLoopConfig
from fruitfly_agent.lab.improvement.targets.bundle import ComponentTarget
from fruitfly_agent.improvement.contracts.optimization import TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import target_edits
from fruitfly_agent.improvement.contracts.versions import canonical_json
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.tools.catalog import ToolCatalogTarget
from fruitfly_agent.lab.tools.read import create_read_tool
from tests.support.faux_provider import FauxProvider


class ComponentTargetTests(unittest.TestCase):
    def setUp(self):
        self.tool = create_read_tool()
        self.target = ComponentTarget('instructions', 'Instructions',
            (BasePromptTarget('Original instructions'), ToolCatalogTarget()))

    def test_single_and_joint_edits_preserve_tools_and_parent(self):
        config = AgentLoopConfig(provider=FauxProvider(), system_prompt='Original instructions', tools=(self.tool,))
        for keys in (('base_prompt',), ('tool-catalog',), ('base_prompt', 'tool-catalog')):
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
        for data in ({}, {**values, 'unknown': 'x'}, {**values, 'tool-catalog': {}},
                     {**values, 'tool-catalog': 'x' * 12001}):
            with self.subTest(data=list(data)), self.assertRaises(ValueError):
                self.target.validate(canonical_json(data))
        mixed = ComponentTarget('mixed', 'Mixed',
            (BasePromptTarget('base'), replace_snapshot_role(ToolCatalogTarget())))
        self.assertEqual({p.role for p in mixed.snapshot().components}, {'H', 'S'})

    def test_candidate_size_limit_does_not_block_runtime_target_registration(self):
        tool = replace(self.tool, description='x' * 30_001)
        target = ComponentTarget('large', 'Tool catalog policy', (ToolCatalogTarget(),))
        config = AgentLoopConfig(provider=FauxProvider(), tools=(tool,))
        trial = target.targets[0].prepare_trial(config, target.targets[0].snapshot().text)
        self.assertNotIn(tool.description, trial.tools[0].description)
        prefix = f'resource://{trial.readable_resources.scope}/tools/'
        self.assertEqual(trial.readable_resources.read(prefix + 'read.txt').decode(), tool.description)
        target.validate(target.snapshot().text)
        with self.assertRaises(ValueError):
            target.validate(canonical_json({'tool-catalog': 'y' * 12001}))


def replace_snapshot_role(target):
    class OtherRole:
        def snapshot(self):
            return replace(target.snapshot(), role='S')
    return OtherRole()
