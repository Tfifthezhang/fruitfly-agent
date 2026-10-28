"""Schedules separate the simple loop from Harness² without weakening evidence guards."""
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.lab.improvement.api import WorkflowServices, TaskMaterial, Measurement
from tests.support.pipeline import build_pipeline


class SearchStrategyTests(unittest.IsolatedAsyncioTestCase):
    def test_editor_instructions_require_all_current_fields(self):
        import json
        from fruitfly_agent.lab.improvement.api import EditorInstructions, EditorInstructionTarget
        current = EditorInstructions()
        target = EditorInstructionTarget(current)
        self.assertEqual(target.snapshot().schema, 'editor-instructions-v3')
        target.validate(target.snapshot().text)
        value = json.loads(current.serialize())
        value.pop('propose')
        with self.assertRaisesRegex(ValueError, 'exactly the registered stage fields'):
            EditorInstructions.parse(json.dumps(value))

    async def test_simple_runs_one_reference_and_one_candidate_without_composition_or_reflection(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.composer.compose = AsyncMock(side_effect=AssertionError('unexpected composition'))
        flow.reflector = type('Reflector', (), {'reflect': AsyncMock(side_effect=AssertionError('unexpected reflection'))})()
        plan = replace(plan, strategy_id='simple', retain_experience=False)
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Complete the task'), baseline, services)
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.decision.assurance, 'selected')
        scopes = [fields['scope'] for event, fields in services.events if event == 'proposal-start']
        self.assertEqual(scopes, ['propose'])

    async def test_simple_retains_baseline_after_worse_candidate_and_uses_it_next_round(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.measurements = type('Scores', (), {'measure': AsyncMock(side_effect=lambda task, record:
            Measurement(record.run_id, 'fixed', 1 if record.harness_id == baseline.snapshot_id else 0))})()
        plan = replace(plan, strategy_id='simple', feedback='scored', depth=2)
        result = await flow.run(plan, TaskMaterial('task', 'Complete the task'), baseline, WorkflowServices(plan))
        self.assertEqual(result.harness, baseline)
        self.assertEqual(len(runner.calls), 3)

    async def test_unknown_strategy_and_incompatible_width_fail_before_execution(self):
        flow, plan, baseline, runner = build_pipeline()
        for changed in (replace(plan, strategy_id='unknown'), replace(plan, strategy_id='simple', width=2)):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                await flow.run(changed, TaskMaterial('task', 'Complete the task'), baseline, WorkflowServices(changed))
        self.assertEqual(runner.calls, [])
