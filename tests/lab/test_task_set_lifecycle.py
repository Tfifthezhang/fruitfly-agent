"""Task-set cancellation, required judgments and zero-reward exploration stay bounded."""
import asyncio
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.improvement.execution.batches import BatchEvaluator
from fruitfly_agent.lab.improvement.workflow import ImprovementWorkflow as ComponentWorkflow
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.assessment.completed import CompletedAssessmentService
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import ExecutionPorts
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.lab.improvement.strategies.exploration import builtin_explorations
from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.workflow.task_sets import TaskSetProblem
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import fixture, version
from tests.support.task_sets import collection, IncrementGenerator


class TaskSetLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_batch_retains_incomplete_evaluation_and_cleans_owned_leaves(self):
        components, baseline = fixture()
        binding, state = collection('tasks', 3)
        entered = asyncio.Event()
        closed = []
        class Runner:
            async def execute(self, plan, task, harness):
                entered.set()
                await asyncio.Event().wait()
            async def aclose(self): closed.append(self)
        binding = replace(binding, build=lambda context: ExecutionPorts(Runner()))
        snapshot = TaskSetSnapshot(binding.entries)
        plan = RunPlan('cancel-batch', version(), ('prompt',))
        services = WorkflowServices(plan)
        context = ExecutionContext(None, MemoryArtifacts(), components, None, None, None, plan=plan, services=services)
        evaluator = BatchEvaluator(context, snapshot, (binding,), MultiTaskSettings(), aggregate=assess_batch)
        pending = asyncio.create_task(evaluator.evaluate(plan, baseline, EvaluationBatch(snapshot.snapshot_id,
            tuple(e.key for e in snapshot.entries))))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError): await pending
            self.assertEqual(len(closed), 2)
            self.assertFalse(evaluator.evaluations[-1].complete)
            self.assertEqual(evaluator.evaluations[-1].assessment.expected, 3)
            self.assertEqual(evaluator.evaluations[-1].assessment.completed, 0)
            self.assertFalse(evaluator.scheduler.active)
            self.assertFalse(hasattr(services,'budget'))
        finally:
            await services.close()

    async def test_unavailable_assessment_keeps_incumbent_without_blocking_search(self):
        outcome, baseline, generator, services, provider = await self.search(invalid=True)
        self.assertEqual(outcome.stop_reason, 'completed')
        self.assertEqual(outcome.harness, baseline)
        self.assertIsNotNone(outcome.selected)
        self.assertTrue(generator.requests)
        self.assertGreaterEqual(len(provider.calls), 1)
        self.assertFalse(hasattr(services,'budget'))

    async def test_equal_official_reward_can_select_supported_process_improvement(self):
        outcome, baseline, generator, services, provider = await self.search()
        self.assertEqual(outcome.harness.component('prompt').files[0].text, 'prompt++')
        self.assertEqual(outcome.selected.assessment.score, 0)
        self.assertEqual(generator.requests[1].baseline.component('prompt').files[0].text, 'prompt+')
        self.assertGreaterEqual(len(provider.calls), 4)
        self.assertEqual(services.used, {'model': len(provider.calls) + 3, 'execution': 3})

    async def search(self, *, invalid=False):
        components, baseline = fixture()
        binding, _ = collection('tasks', 1, score=lambda task, harness: 0)
        snapshot = TaskSetSnapshot(binding.entries)
        settings = MultiTaskSettings()
        plan = RunPlan('judged-batch', version(), ('prompt',), generator_id='increment', strategy_id='simple',
            depth=2, feedback='scored', retain_experience=False)
        services = WorkflowServices(plan)
        artifacts = MemoryArtifacts()
        context = ExecutionContext(None, artifacts, components, None, None, None, plan=plan, services=services)
        provider = FauxProvider()
        if invalid:
            provider.respond_text('invalid JSON')
        else:
            def response(view, signal=None):
                from tests.support.model_evaluation import judgment
                async def stream(): yield StreamDone(judgment(view))
                return AssistantMessageEventStream(stream())
            provider.script = [response] * 8
        assessment = CompletedAssessmentService(config=AgentLoopConfig(provider=provider), artifacts=artifacts, services=services)
        generator = IncrementGenerator()
        registry = GeneratorRegistry(); registry.register('increment', lambda: generator, supports_task_sets=True)
        flow = ComponentWorkflow(generators=registry, components=components, runner=None, composer=None, selector=None,
            completed_assessment=assessment, exploration=builtin_explorations().create('process-guided'),
            problem=TaskSetProblem(context, snapshot, (binding,), settings))
        try:
            return await flow.run(plan, snapshot, baseline, services), baseline, generator, services, provider
        finally:
            await services.close()
