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
from fruitfly_agent.lab.improvement.assessment.configuration import ProcessAssessmentSettings
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.lab.improvement.assessment.registry import builtin_completed_assessors
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
            self.assertEqual(services.budget.held, {'model': 0, 'execution': 0})
        finally:
            await services.close()

    async def test_required_assessment_failure_stops_before_generating_or_promoting(self):
        outcome, baseline, generator, services, provider = await self.search(invalid=True)
        self.assertEqual(outcome.stop_reason, 'assessment_unavailable')
        self.assertEqual(outcome.harness, baseline)
        self.assertIsNone(outcome.selected)
        self.assertEqual(generator.requests, [])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(services.budget.held, {'model': 0, 'execution': 0})

    async def test_process_guided_seed_can_advance_while_joint_zero_reward_keeps_formal_baseline(self):
        outcome, baseline, generator, services, provider = await self.search()
        self.assertEqual(outcome.harness, baseline)
        self.assertEqual(outcome.selected.assessment.score, 0)
        self.assertEqual(generator.requests[1].baseline.component('prompt').files[0].text, 'prompt+')
        self.assertEqual(len(provider.calls), 4)
        self.assertEqual(services.used, {'model': 7, 'execution': 3})

    async def search(self, *, invalid=False):
        components, baseline = fixture()
        binding, _ = collection('tasks', 1, score=lambda task, harness: 0)
        snapshot = TaskSetSnapshot(binding.entries)
        settings = MultiTaskSettings()
        plan = RunPlan('judged-batch', version(), ('prompt',), generator_id='increment', strategy_id='simple',
            depth=2, feedback='scored', retain_experience=False, max_model_calls=100)
        services = WorkflowServices(plan)
        artifacts = MemoryArtifacts()
        context = ExecutionContext(None, artifacts, components, None, None, None, plan=plan, services=services)
        provider = FauxProvider()
        if invalid:
            provider.respond_text('invalid JSON')
        else:
            def response(view, signal=None):
                payload = json.loads(view.messages[0].content)
                if 'candidates' in payload:
                    name = next(key for key in payload['candidates'] if key != payload['incumbent'])
                    facts = payload['candidates'][name]['executions'][0]['facts_id']
                    data = {'evaluation_id': name, 'reason': 'Synthetic next-seed judgment.', 'evidence_ids': [facts]}
                else:
                    data = {'metrics': [], 'detail': 'Synthetic cited judgment.',
                        'evidence_ids': [payload['executions'][0]['facts_id']]}
                async def stream():
                    yield StreamDone(AssistantMessage(content=[TextBlock(json.dumps(data))], stop_reason='stop'))
                return AssistantMessageEventStream(stream())
            provider.script = [response] * 8
        assessment = CompletedAssessmentService(ProcessAssessmentSettings(('completed-model-v1',), 16, 1, True),
            config=AgentLoopConfig(provider=provider), artifacts=artifacts, services=services,
            registry=builtin_completed_assessors())
        generator = IncrementGenerator()
        registry = GeneratorRegistry(); registry.register('increment', lambda: generator, supports_task_sets=True)
        flow = ComponentWorkflow(generators=registry, components=components, runner=None, composer=None, selector=None,
            completed_assessment=assessment, exploration=builtin_explorations().create('process-guided'),
            problem=TaskSetProblem(context, snapshot, (binding,), settings))
        try:
            return await flow.run(plan, snapshot, baseline, services), baseline, generator, services, provider
        finally:
            await services.close()
