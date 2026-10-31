"""Joint search uses shared rounds, bounded leaf execution and full-set promotion."""
from types import SimpleNamespace
import unittest

from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.lab.improvement.workflow.task_sets import TaskSetProblem
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from tests.support.pipeline import fixture, version
from tests.support.task_sets import collection, IncrementGenerator
from dataclasses import replace


class TaskSetSearchTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, binding, *, settings=None, rounds=1, model_calls=100):
        components, baseline = fixture()
        snapshot = TaskSetSnapshot(binding.entries)
        plan = RunPlan('joint-fixture', version(), ('prompt',), generator_id='increment', strategy_id='simple',
            depth=rounds, feedback='scored', retain_experience=False)
        services = WorkflowServices(plan)
        context = ExecutionContext(None, MemoryArtifacts(), components, None, None, None, plan=plan, services=services)
        registry = GeneratorRegistry(); registry.register('increment', IncrementGenerator)
        problem = TaskSetProblem(context, snapshot, (binding,), settings or MultiTaskSettings())
        flow = ComponentWorkflow(generators=registry, components=components, runner=None,
            composer=None, selector=None, problem=problem)
        try:
            return await flow.run(plan, snapshot, baseline, services), baseline, services
        finally:
            await services.close()

    async def test_joint_candidates_run_concurrently_and_promote_on_a_shared_full_set(self):
        components, baseline = fixture()
        a, state = collection('a', 4)
        snapshot = TaskSetSnapshot(a.entries)
        settings = MultiTaskSettings.from_dict({'sampling': {'batch_size': 2}, 'execution': {'concurrency': 2}})
        plan = RunPlan('joint', version(), ('prompt',), generator_id='increment', strategy_id='simple',
            depth=2, feedback='scored', retain_experience=False)
        services = WorkflowServices(plan)
        artifacts = MemoryArtifacts()
        context = ExecutionContext(None, artifacts, components, None, None, None, plan=plan, services=services)
        generator = IncrementGenerator()
        registry = GeneratorRegistry(); registry.register('increment', lambda: generator)
        problem = TaskSetProblem(context, snapshot, (a,), settings)
        flow = ComponentWorkflow(generators=registry, components=components, runner=None, composer=None,
            selector=None, problem=problem)
        try:
            result = await flow.run(plan, snapshot, baseline, services)
            self.assertIsNotNone(result.selected)
            self.assertEqual(result.selected.batch.phase, 'selection')
            self.assertEqual(set(result.selected.batch.task_keys), {e.key for e in snapshot.entries})
            self.assertEqual(result.selected.assessment.score, 1)
            self.assertEqual(state.peak, 2)
            self.assertEqual(services.used['model'], len(state.calls))
            self.assertEqual(services.used['execution'], len(state.calls))
            self.assertEqual(state.cleaned, len(state.calls))
            workspace = EvidenceWorkspace.build(generator.requests[-1], artifacts)
            self.assertIn('context/evaluations.json', workspace.paths())
            self.assertTrue(any('execution-facts.json' in p for p in workspace.paths()))
        finally:
            await services.close()

    async def test_small_batch_winner_cannot_replace_a_better_full_set_incumbent(self):
        def score(task, harness):
            changed = '+' in harness.component('prompt').files[0].text
            return float(changed if task.task_id == 'a-0' else not changed)
        binding, state = collection('a', 4, score=score)
        settings = MultiTaskSettings.from_dict({'sampling': {'policy': 'fixed', 'task_keys': ['a-0']}})
        outcome, baseline, services = await self.execute(binding, settings=settings)
        self.assertEqual(outcome.harness, baseline)
        self.assertEqual(outcome.selected.assessment.score, .75)
        self.assertTrue(any(e.batch.phase == 'search' and e.assessment.score == 1 for e in outcome.records))
        self.assertTrue(any(e.batch.phase == 'selection' and e.assessment.score == .25 for e in outcome.records))

    async def test_candidate_execution_error_cannot_be_hidden_by_other_successful_tasks(self):
        def score(task, harness):
            if '+' in harness.component('prompt').files[0].text and task.task_id == 'a-1':
                raise RuntimeError('fixture task infrastructure unavailable')
            return 1
        binding, state = collection('a', 2, score=score)
        outcome, baseline, services = await self.execute(binding)
        self.assertEqual(outcome.harness, baseline)
        self.assertEqual(outcome.selected.assessment.score, 1)
        incomplete = [e for e in outcome.records if not e.complete]
        self.assertTrue(incomplete)
        self.assertEqual(incomplete[0].assessment.expected, 2)
        self.assertEqual(incomplete[0].assessment.completed, 1)
        self.assertEqual(state.cleaned, len(state.calls))

    async def test_concurrency_is_not_reduced_by_hidden_model_reservations(self):
        binding, state = collection('a', 3, limit=3)
        outcome, baseline, services = await self.execute(binding,
            settings=MultiTaskSettings.from_dict({'execution': {'concurrency': 3}}), model_calls=26)
        self.assertEqual(outcome.selected.assessment.score, 1)
        self.assertEqual(services.used['model'], len(state.calls))
        self.assertEqual(services.used['execution'], len(state.calls))
        self.assertEqual(state.peak, 3)
