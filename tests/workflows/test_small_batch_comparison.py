"""Native collection execution feeds measured comparison without batch rewriting."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from fruitfly_agent.improvement.contracts.task_sets import TaskSetSnapshot
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.lab.improvement.task_sets import MultiTaskSettings
from fruitfly_agent.lab.improvement.task_sets.execution import execution_definition
from fruitfly_agent.lab.improvement.assessment.methods.measured.policy import compare_batches
from tests.support.task_sets import collection
from tests.support.stages import version


class SmallBatchComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_selected_tasks_twice_produce_directly_comparable_measurements(self):
        binding, state = collection('selected', 5)
        binding = replace(binding, entries=binding.entries[:3])
        snapshot = TaskSetSnapshot(binding.entries)
        settings = MultiTaskSettings.from_dict({'execution': {'attempts': 2, 'concurrency': 2}})
        definition = execution_definition(lambda _: (binding,), settings,
            expected=snapshot, capabilities=binding.capabilities)
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('before'), 'system-prompt'),))
        plan = RunPlan('study', version(), ('base_prompt',))
        with tempfile.TemporaryDirectory() as directory:
            async with StageServices(plan) as services:
                context = ExecutionContext(Path(directory), artifacts, components, None, None, None,
                    plan=plan, services=services)
                ports = definition.build(context, SimpleNamespace(task=snapshot, private=(binding,)))
                before = await ports.execute_batch(plan, components.snapshot(), services)
                after = await ports.execute_batch(plan, components.snapshot(), services)
                result = compare_batches(before, after, [])
                self.assertEqual(result['coverage']['planned'], 6)
                self.assertEqual(result['metrics']['before']['grading_coverage']['value'], 1)
                self.assertEqual(result['metrics']['after']['official_score']['known_count'], 6)
                self.assertEqual(len(state.calls), 12)
                self.assertEqual({key for key, _ in state.calls}, {'selected-0', 'selected-1', 'selected-2'})
                self.assertLessEqual(state.peak, 2)
