"""Task-set cancellation, required judgments and zero-reward exploration stay bounded."""
import asyncio
from dataclasses import replace
import json
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.improvement.execution.batches import BatchEvaluator
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.assessment.completed import CompletedAssessmentService
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import ExecutionPorts
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.lab.improvement.assessment.joint import assess_batch
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.faux_provider import FauxProvider
from tests.support.stages import fixture, version
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
        services = StageServices(plan)
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
