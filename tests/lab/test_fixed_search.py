"""The fixed round flow preserves evidence guards and rejects schedule choices."""
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.assessment import Measurement
from tests.support.pipeline import build_pipeline


class FixedSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_editor_instructions_require_all_current_fields(self):
        import json
        from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructions, EditorInstructionTarget
        current = EditorInstructions()
        target = EditorInstructionTarget(current)
        self.assertEqual(target.snapshot().schema, 'editor-instructions')
        target.validate(target.snapshot().text)
        value = json.loads(current.serialize())
        value.pop('propose')
        with self.assertRaisesRegex(ValueError, 'exactly the registered stage fields'):
            EditorInstructions.parse(json.dumps(value))

    async def test_simple_runs_one_reference_and_one_candidate_without_composition_or_reflection(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.reflector = type('Reflector', (), {'reflect': AsyncMock(side_effect=AssertionError('unexpected reflection'))})()
        plan = replace(plan,  retain_experience=False)
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Complete the task'), baseline, services)
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.decision.assurance, 'selected')
        self.assertEqual(len([e for e, _ in services.events if e == 'proposal-start']), 1)

    async def test_simple_retains_baseline_after_worse_candidate_and_uses_it_next_round(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.measurements = type('Scores', (), {'measure': AsyncMock(side_effect=lambda task, record:
            Measurement(record.run_id, 'fixed', 1 if record.harness_id == baseline.snapshot_id else 0))})()
        plan = replace(plan,   rounds=2)
        result = await flow.run(plan, TaskMaterial('task', 'Complete the task'), baseline, WorkflowServices(plan))
        self.assertEqual(result.harness, baseline)
        self.assertEqual(len(runner.calls), 3)

    def test_removed_schedule_fields_are_rejected_by_the_public_plan(self):
        _, plan, _, runner = build_pipeline()
        for value in ({'strategy_id':'retired'}, {'width':2}, {'mode':'parallel'}, {'feedback':'auto'}):
            with self.subTest(value=value), self.assertRaises(TypeError):
                replace(plan, **value)
        self.assertEqual(runner.calls, [])

    async def test_uncertain_later_comparison_retains_the_current_incumbent(self):
        from fruitfly_agent.improvement.contracts.assessment import SelectionDecision
        flow,plan,baseline,runner=build_pipeline();plan=replace(plan,rounds=2)
        comparisons=[]
        async def select(task,records):
            comparisons.append(records)
            chosen=records[-1] if len(comparisons)==1 else records[0]
            return SelectionDecision(chosen.run_id,'First improvement, then insufficient evidence to replace incumbent')
        flow.selector.select=select
        outcome=await flow.run(plan,TaskMaterial('task','Work'),baseline,WorkflowServices(plan))
        self.assertEqual(len(runner.calls),3)
        self.assertEqual(comparisons[1][0].run_id,comparisons[0][-1].run_id)
        self.assertEqual(outcome.harness,outcome.candidates[0].harness)
