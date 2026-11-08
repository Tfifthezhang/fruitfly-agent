"""Retained state and workflow adapters execute their exact frozen candidates."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.improvement.targets.retained import RetainedText
from fruitfly_agent.improvement.contracts.text import state_artifact_path
from tests.support.faux_provider import FauxProvider


class RetainedTargetTests(unittest.IsolatedAsyncioTestCase):
    def test_state_projection_is_idempotent_bounded_and_immutable(self):
        target = RetainedText('fixture-note', 'Original', 'Selected skill', 'fixture-note-v1', 128)
        config = AgentLoopConfig(provider=FauxProvider(), system_prompt='base')
        projected = target.prepare_trial(config, 'Candidate')
        self.assertEqual(projected, target.prepare_trial(projected, 'Candidate'))
        self.assertNotIn('Original', projected.system_prompt)
        self.assertEqual(target.snapshot().text, 'Original')
        self.assertEqual(target.freeze().files[0].path, state_artifact_path('fixture-note'))
        self.assertEqual(target.freeze_text('Candidate').files[0].content, 'Candidate')
        for text in ('', 'x' * 129, '<!-- fruitfly:fixture-note:start -->', '<!-- fruitfly:workflow:start -->'):
            with self.assertRaises(ValueError):
                target.validate(text)

    async def trial(self, config, targets, changed, text, calls=10):
        from fruitfly_agent.lab.improvement.components import component_registry
        from fruitfly_agent.improvement.contracts.plans import RunPlan
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from tests.support.task_execution import TaskRunnerFixture
        from fruitfly_agent.improvement.stages.services import StageServices
        from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
        from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        registry = component_registry(targets)
        harness = HarnessSnapshot(tuple(with_component_text(c, text)
            if c.component_id == changed else c for c in registry.snapshot().components))
        plan = RunPlan('test', SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S'))), (changed,))
        services = StageServices(plan)
        record = await TaskRunnerFixture(config, registry, MemoryArtifacts(), services).execute(
            plan, TaskMaterial('task', 'select'), harness)
        return record, services

    async def test_retained_trial_changes_only_its_frozen_document(self):
        provider = FauxProvider(); provider.respond_text('B')
        skill = RetainedText('fixture-note', 'old skill', 'Skill', 'fixture-note-v1')
        fixed = RetainedText('fixture-memory', 'fixed note', 'Fixture', 'fixture-v1')
        record, services = await self.trial(AgentLoopConfig(provider=provider), (skill, fixed), 'fixture-note', 'new skill')
        self.assertEqual(record.output, 'B')
        self.assertIn('fixed note', provider.calls[0]['system_prompt'])
        self.assertIn('new skill', provider.calls[0]['system_prompt'])
        self.assertNotIn('old skill', provider.calls[0]['system_prompt'])
        self.assertEqual(skill.text, 'old skill')

    def test_selected_skill_source_is_bounded_and_rejects_symlinks(self):
        from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import load_skill_document
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
