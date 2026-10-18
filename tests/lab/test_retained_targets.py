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
from fruitfly_agent.lab.improvement.contracts.search import ImprovementProblem, TaskCase
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices, SearchBudget, SearchJournal, BudgetExhausted
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

    async def test_workflow_production_and_trials_use_same_steps_and_final_output(self):
        text = json.dumps({'steps': ['Solve carefully.', 'Critique and return final answer only.']})
        provider = FauxProvider()
        provider.respond_text('draft')
        provider.respond_text('B')
        config = AgentLoopConfig(provider=provider, system_prompt='base')
        production = apply_workflow(config, text)
        result = await run_agent_loop(production, [UserMessage(content='select')])
        self.assertEqual([m.text for m in result.messages if isinstance(m, AssistantMessage)], ['draft', 'B'])
        self.assertIn('Solve carefully.', provider.calls[0]['system_prompt'])
        production_calls = provider.calls.copy()
        provider.calls.clear()
        provider.respond_text('draft')
        provider.respond_text('B')
        target = WorkflowTarget(text)
        problem = ImprovementProblem('job', 'parent', target.snapshot(), '', (TaskCase('train', 'A'),),
            (TaskCase('select', 'B'),), 'cases', 'execution')
        services = NativeSearchServices(problem, production, target, budget=SearchBudget(10, 5), journal=SearchJournal(problem))
        evaluation = await services.evaluate(text, 'validation')
        self.assertEqual(evaluation.score, 1)
        self.assertEqual(evaluation.observations[0].output, 'B')
        self.assertEqual(services.budget.used, {'model': 2, 'trial': 1})
        self.assertEqual(provider.calls[0]['system_prompt'], production_calls[0]['system_prompt'])
        self.assertEqual(provider.calls[1]['messages'][-1].content, 'Critique and return final answer only.')

    async def test_fixed_workflow_and_other_state_survive_a_skill_trial(self):
        provider = FauxProvider()
        provider.respond_text('draft')
        provider.respond_text('B')
        target = RetainedText('skill-document', 'old skill', 'Skill', 'skill-document-v1')
        memory = RetainedText('learned-memory', 'fixed memory', 'Memory', 'environment-memory-v1')
        workflow = WorkflowTarget('{"steps":["reason","return final"]}')
        p = ImprovementProblem('job', 'parent', target.snapshot(), '', (TaskCase('train', 'A'),),
            (TaskCase('select', 'B'),), 'cases', 'execution')
        s = NativeSearchServices(p, AgentLoopConfig(provider=provider), target, budget=SearchBudget(10, 5),
            journal=SearchJournal(p), trial_targets=(target, memory, workflow))
        self.assertEqual((await s.evaluate('new skill', 'validation')).score, 1)
        self.assertIn('fixed memory', provider.calls[0]['system_prompt'])
        self.assertIn('new skill', provider.calls[0]['system_prompt'])
        self.assertNotIn('old skill', provider.calls[0]['system_prompt'])
        self.assertEqual(len(provider.calls), 2)

    async def test_multistep_execution_stops_at_shared_model_budget(self):
        provider = FauxProvider()
        provider.respond_text('draft')
        target = WorkflowTarget('{"steps":["reason","finish"]}')
        p = ImprovementProblem('job', 'parent', target.snapshot(), '', (TaskCase('train', 'A'),),
            (TaskCase('select', 'B'),), 'cases', 'execution')
        s = NativeSearchServices(p, AgentLoopConfig(provider=provider), target,
            budget=SearchBudget(1, 5), journal=SearchJournal(p))
        with self.assertRaises(BudgetExhausted):
            await s.evaluate(target.text, 'validation')
        self.assertEqual(len(provider.calls), 1)

    async def test_production_context_order_matches_trials_with_multiple_documents(self):
        from fruitfly_agent.core.context import ContextFrame
        provider = FauxProvider()
        skill = RetainedText('skill-document', 'old skill', 'Skill', 'skill-document-v1')
        memory = RetainedText('learned-memory', 'fixed memory', 'Memory', 'environment-memory-v1')
        workflow = WorkflowTarget('{"steps":["reason","return final"]}')
        original = apply_workflow(AgentLoopConfig(provider=provider, system_prompt='base'), workflow.text)
        p = ImprovementProblem('job', 'parent', skill.snapshot(), '', (TaskCase('train', 'A'),),
            (TaskCase('select', 'B'),), 'cases', 'execution')
        s = NativeSearchServices(p, original, skill, budget=SearchBudget(10, 5), journal=SearchJournal(p),
            trial_targets=(skill, memory, workflow))
        provider.respond_text('draft')
        provider.respond_text('B')
        await s.evaluate('new skill', 'validation')
        selected = replace(skill, text='new skill')
        frame = ContextFrame(original.system_prompt, (), (), '', 1024)
        frame = selected.transform(frame).frame
        frame = memory.transform(frame).frame
        self.assertEqual(provider.calls[0]['system_prompt'], frame.system_prompt)

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
