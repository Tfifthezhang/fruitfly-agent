"""Retained state and workflow adapters execute their exact frozen candidates."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.algorithms.retained import RetainedText
from fruitfly_agent.lab.algorithms.targets import state_artifact_path
from fruitfly_agent.lab.workflow import WorkflowTarget, apply_workflow, parse_workflow
from tests.support.faux_provider import FauxProvider


class RetainedTargetTests(unittest.IsolatedAsyncioTestCase):
    def test_state_projection_is_idempotent_bounded_and_immutable(self):
        target = RetainedText('skill-document', 'Original', 'Selected skill', 'skill-document-v1', 128)
        config = AgentLoopConfig(provider=FauxProvider(), system_prompt='base')
        projected = target.prepare_trial(config, 'Candidate')
        self.assertEqual(projected, target.prepare_trial(projected, 'Candidate'))
        self.assertNotIn('Original', projected.system_prompt)
        self.assertEqual(target.snapshot().text, 'Original')
        self.assertEqual(target.freeze().files[0].path, state_artifact_path('skill-document'))
        self.assertEqual(target.freeze_text('Candidate').files[0].content, 'Candidate')
        for text in ('', 'x' * 129, '<!-- fruitfly:skill-document:start -->', '<!-- fruitfly:workflow:start -->'):
            with self.assertRaises(ValueError):
                target.validate(text)

    async def trial(self, config, targets, changed, text, calls=10):
        from fruitfly_agent.lab.improvement.api import (component_registry, RunPlan,
            TaskMaterial, FileTaskRunner, WorkflowServices, HarnessSnapshot, ComponentFile)
        from fruitfly_agent.lab.algorithms.targets import SystemVersion, content_hash
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        registry = component_registry(targets)
        harness = HarnessSnapshot(tuple(replace(c, files=(ComponentFile('instructions.txt', text),))
            if c.component_id == changed else c for c in registry.snapshot().components))
        plan = RunPlan('test', SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S'))), (changed,), max_model_calls=calls)
        services = WorkflowServices(plan)
        record = await FileTaskRunner(config, registry, MemoryArtifacts(), services).execute(
            plan, TaskMaterial('task', 'select'), harness)
        return record, services

    async def test_workflow_production_and_trials_use_same_steps_and_final_output(self):
        text = json.dumps({'steps': ['Solve carefully.', 'Critique and return final answer only.']})
        provider = FauxProvider()
        provider.respond_text('draft')
        provider.respond_text('B')
        config = AgentLoopConfig(provider=provider, system_prompt='base')
        result = await run_agent_loop(apply_workflow(config, text), [UserMessage(content='select')])
        self.assertEqual([m.text for m in result.messages if isinstance(m, AssistantMessage)], ['draft', 'B'])
        production_calls = provider.calls.copy()
        provider.calls.clear()
        provider.respond_text('draft')
        provider.respond_text('B')
        record, services = await self.trial(config, (WorkflowTarget(text),), 'execution-workflow', text)
        self.assertEqual((record.status, record.output), ('completed', 'B'))
        self.assertEqual(services.used['model'], 2)
        self.assertEqual(provider.calls[0]['system_prompt'], production_calls[0]['system_prompt'])
        self.assertEqual(provider.calls[1]['messages'][-1].content, 'Critique and return final answer only.')

    async def test_fixed_workflow_and_other_state_survive_a_skill_trial(self):
        provider = FauxProvider()
        provider.respond_text('draft')
        provider.respond_text('B')
        skill = RetainedText('skill-document', 'old skill', 'Skill', 'skill-document-v1')
        memory = RetainedText('learned-memory', 'fixed memory', 'Memory', 'environment-memory-v1')
        workflow = WorkflowTarget('{"steps":["reason","return final"]}')
        record, _ = await self.trial(AgentLoopConfig(provider=provider), (skill, memory, workflow), 'skill-document', 'new skill')
        self.assertEqual(record.output, 'B')
        self.assertIn('fixed memory', provider.calls[0]['system_prompt'])
        self.assertIn('new skill', provider.calls[0]['system_prompt'])
        self.assertNotIn('old skill', provider.calls[0]['system_prompt'])
        self.assertEqual(len(provider.calls), 2)

    async def test_multistep_execution_stops_at_shared_model_budget(self):
        provider = FauxProvider()
        provider.respond_text('draft')
        target = WorkflowTarget('{"steps":["reason","finish"]}')
        record, services = await self.trial(AgentLoopConfig(provider=provider), (target,), 'execution-workflow', target.text, calls=1)
        self.assertEqual(record.status, 'error')
        self.assertEqual(services.used['model'], 1)
        self.assertEqual(len(provider.calls), 1)

    def test_workflow_rejects_code_unknown_fields_and_unbounded_steps(self):
        for value in ('print(1)', '{}', '{"steps":[]}', '{"steps":[1]}',
                      json.dumps({'steps': ['x'] * 7}), '{"steps":["ok"],"exec":"code"}',
                      '{"steps":["<!-- fruitfly:skill-document:start -->"]}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_workflow(value)
        with self.assertRaises(ValueError):
            apply_workflow(AgentLoopConfig(provider=FauxProvider(), max_turns=1), '{"steps":["a","b"]}')

    def test_selected_skill_source_is_bounded_and_rejects_symlinks(self):
        from fruitfly_agent.lab.context_manager.augmentation.skills.catalog import load_skill_document
        with tempfile.TemporaryDirectory() as directory:
            # macOS exposes its temporary root through /var -> /private/var.
            # Match the canonical workspace path supplied by Catalog assembly.
            root = Path(directory).resolve()
            source = root / 'SKILL.md'
            source.write_text('---\nname: review\ndescription: Review code\n---\nBody with references/check.md')
            selected = load_skill_document(source)
            self.assertEqual(selected.name, 'review')
            self.assertEqual(selected.content, 'Body with references/check.md')
            self.assertEqual(selected.file_path, str(source.resolve()))
            linked = root / 'linked.md'
            linked.symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                load_skill_document(linked)
            source.write_text('x' * 128001)
            with self.assertRaisesRegex(ValueError, 'byte limit'):
                load_skill_document(source)
