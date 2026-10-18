"""Measured method behavior, bounded edits, evidence separation and interruption."""
import asyncio
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.lab.algorithms.retained import RetainedText
from fruitfly_agent.lab.improvement.contracts.search import ImprovementProblem, TaskCase
from fruitfly_agent.lab.improvement.methods.skill_edit import SkillEditImprover, apply_edits, definition as skill_definition
from fruitfly_agent.lab.improvement.methods.memory_exploration import MemoryExplorationImprover, definition as memory_definition
from fruitfly_agent.lab.improvement.methods.workflow_search import WorkflowSearchImprover, definition as workflow_definition
from fruitfly_agent.lab.improvement.runtime.services import NativeSearchServices, SearchBudget, SearchJournal
from fruitfly_agent.lab.workflow import WorkflowTarget, parse_workflow
from tests.support.faux_provider import FauxProvider


def setup_search(method, target, definition, responses=(), *, overrides=None, evaluator=None, model_limit=50):
    params = definition().descriptor.normalize_parameters(overrides or {})
    problem = ImprovementProblem('job', 'parent', target.snapshot(), '',
        (TaskCase('TRAIN_ONE', 'A'), TaskCase('TRAIN_TWO', 'B')),
        (TaskCase('PRIVATE_SELECTION_INPUT', 'PRIVATE_SELECTION_ANSWER'),),
        'cases', 'execution', parameters=tuple(params.items()))
    provider = FauxProvider()
    for response in responses:
        provider.respond_text(response)
    services = NativeSearchServices(problem, AgentLoopConfig(provider=provider), target,
        journal=SearchJournal(problem), budget=SearchBudget(model_limit, 100), evaluator=evaluator or
        (lambda text, _case: float('GOOD' in text)))
    return method, problem, services, provider


def skill_target():
    return RetainedText('skill-document', '# Skill', 'Skill document', 'skill-document-v1')


def memory_target():
    return RetainedText('learned-memory', '# Memory', 'Environment memory', 'environment-memory-v1')


class DocumentMethodTests(unittest.IsolatedAsyncioTestCase):
    def test_edits_are_bounded_unambiguous_and_transactional(self):
        original = 'first\nsecond'
        self.assertEqual(apply_edits(original, [dict(op='replace', old='first', new='new')], 1), 'new\nsecond')
        for edits in ([], [dict(op='add', old='', new='one')] * 2,
                      [dict(op='replace', old='absent', new='new')],
                      [dict(op='delete', old='first', new='unexpected')],
                      [dict(op='execute', old='', new='code')], [dict(op='add', old='', new='x', extra=True)]):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                apply_edits(original, edits, 1)
        self.assertEqual(original, 'first\nsecond')
        with self.assertRaises(ValueError):
            apply_edits('same same', [dict(op='replace', old='same', new='x')], 1)

    async def test_skill_reflects_minibatches_merges_and_gates(self):
        proposal = json.dumps([dict(op='add', old='', new='GOOD procedure')])
        method, p, services, provider = setup_search(SkillEditImprover(), skill_target(), skill_definition,
            [proposal, proposal, proposal], overrides={'rounds': 1, 'reflection_batch_size': 1})
        result = await method.search(p, services)
        self.assertEqual(result.candidates[0].score, 1)
        self.assertEqual(len(provider.calls), 3)
        prompts = '\n'.join(str(c['messages']) for c in provider.calls)
        self.assertIn('TRAIN_ONE', prompts)
        self.assertNotIn('PRIVATE_SELECTION', prompts)
        self.assertTrue(any(r['kind'] == 'skill-edit-gate' and r['accepted'] for r in services.history()))

    async def test_skill_rejected_edits_feed_later_reflection_and_ties_do_not_publish(self):
        bad = json.dumps([dict(op='add', old='', new='ineffective')])
        good = json.dumps([dict(op='add', old='', new='GOOD')])
        method, p, s, provider = setup_search(SkillEditImprover(), skill_target(), skill_definition, [bad, good])
        result = await method.search(p, s)
        self.assertEqual(result.candidates[0].score, 1)
        self.assertIn('ineffective', provider.calls[1]['messages'][0].content)
        self.assertEqual([r['accepted'] for r in s.history() if r['kind'] == 'skill-edit-gate'], [False, True])

    async def test_memory_broad_then_focused_reuses_grounded_tied_memory(self):
        responses = ['[0,1]', '# Memory\nBROAD knowledge', '[1]', '# Memory\nGOOD deep knowledge']
        method, p, s, provider = setup_search(MemoryExplorationImprover(), memory_target(), memory_definition,
            responses, overrides={'rounds': 2})
        result = await method.search(p, s)
        self.assertEqual(result.candidates[0].score, 1)
        self.assertIn('BROAD knowledge', provider.calls[2]['messages'][0].content)
        phases = [r['phase'] for r in s.history() if r['kind'] == 'memory-practice']
        self.assertEqual(phases, ['broad', 'focused'])
        self.assertTrue(all('PRIVATE_SELECTION' not in str(c['messages']) for c in provider.calls))

    async def test_curriculum_cannot_select_validation_or_unregistered_tasks(self):
        method, p, s, provider = setup_search(MemoryExplorationImprover(), memory_target(), memory_definition,
            ['[2]', '[true]', '[0,0]'])
        result = await method.search(p, s)
        self.assertEqual(result.candidates, ())
        self.assertFalse(any(r['kind'] == 'memory-practice' for r in s.history()))
        self.assertEqual(len(provider.calls), 3)

    async def test_infrastructure_errors_never_become_memory_learning(self):
        def broken(_text, _case):
            raise RuntimeError('unavailable')
        method, p, s, provider = setup_search(MemoryExplorationImprover(), memory_target(), memory_definition,
            evaluator=broken)
        result = await method.search(p, s)
        self.assertEqual(result.stop_reason, 'baseline_unmeasured')
        self.assertEqual(provider.calls, [])

    async def test_workflow_reflects_repairs_schema_and_keeps_measured_design_archive(self):
        candidate = json.dumps({'steps': ['GOOD solve', 'Return the final answer.']})
        method, p, s, provider = setup_search(WorkflowSearchImprover(), WorkflowTarget(), workflow_definition,
            ['bad design', '{"steps":[]}', candidate], overrides={'rounds': 1})
        result = await method.search(p, s)
        self.assertEqual(len(parse_workflow(result.candidates[0].text)), 2)
        self.assertEqual(len(provider.calls), 3)
        self.assertIn('schema_error', provider.calls[2]['messages'][0].content)
        self.assertNotIn('PRIVATE_SELECTION', str(provider.calls))

    async def test_workflow_semantic_duplicates_do_not_consume_trials(self):
        candidate = '{ "steps" : [ "Solve the user task and return the final answer." ] }'
        method, p, s, _ = setup_search(WorkflowSearchImprover(), WorkflowTarget(), workflow_definition,
            [candidate], overrides={'rounds': 1, 'reflection_steps': 0})
        result = await method.search(p, s)
        self.assertEqual(result.candidates, ())
        self.assertEqual(s.budget.used['trial'], 3)  # baseline selection and two training tasks

    async def test_all_methods_reject_wrong_roles_and_honor_cancel_and_root_budget(self):
        methods = ((SkillEditImprover, skill_target, skill_definition),
                   (MemoryExplorationImprover, memory_target, memory_definition),
                   (WorkflowSearchImprover, WorkflowTarget, workflow_definition))
        for cls, target, definition in methods:
            with self.subTest(method=cls.__name__):
                method, p, s, provider = setup_search(cls(), target(), definition, model_limit=1)
                wrong = replace(p, baseline=replace(p.baseline, role='I'))
                with self.assertRaises(ValueError):
                    await method.search(wrong, s)
                s.stop.set()
                with self.assertRaises(asyncio.CancelledError):
                    await method.search(p, s)
                self.assertEqual(provider.calls, [])
                method, p, s, provider = setup_search(cls(), target(), definition, model_limit=1)
                s.budget.reserve('model')
                result = await method.search(p, s)
                self.assertEqual(result.stop_reason, 'budget_exhausted')
                self.assertEqual(result.candidates, ())
                self.assertEqual(provider.calls, [])
