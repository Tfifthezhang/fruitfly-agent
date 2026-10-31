"""Stop, retention, quotas and fixed-field contracts for bounded experiments."""
import asyncio
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision, Measurement
from fruitfly_agent.improvement.contracts.components import ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructions, EditorInstructionTarget
from fruitfly_agent.lab.improvement.termination.policies import BoundedStopPolicy
from fruitfly_agent.improvement.contracts.stopping import SearchState
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from tests.support.pipeline import build_pipeline


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_editor_candidate_cannot_change_fixed_fields(self):
        instructions = EditorInstructions()
        target = EditorInstructionTarget(instructions)
        target.validate(EditorInstructionTarget(replace(instructions, invariant='Use a different proposal procedure')).snapshot().text)
        for field in ('system', 'reflect'):
            text = EditorInstructionTarget(replace(instructions, **{field: 'Mutated field'})).snapshot().text
            target.validate_change(text, {'editable_fields': ['parameters.instructions.'+field]})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'fixed'):
                target.validate_change(text, {'editable_fields': ['parameters.instructions.invariant']})
        formatted = json.dumps(json.loads(target.snapshot().text), indent=2)
        self.assertEqual(EditorInstructionTarget(instructions, text=formatted).snapshot().text, formatted)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            EditorInstructions.parse(instructions.serialize().replace('{', '{"system":"duplicate",', 1))

    def test_stop_reasons_are_separate_from_assurance(self):
        policy = BoundedStopPolicy()
        self.assertEqual(policy.decide(SearchState(0, 1, 2, False, False)), 'completed')
        self.assertEqual(policy.decide(SearchState(0, 3, 2, True, False)), 'repeated_candidates')
        self.assertEqual(policy.decide(SearchState(0, 3, 0, False, False)), 'no_candidate')


class RetentionTests(unittest.IsolatedAsyncioTestCase):
    def build(self, **kwargs):
        return build_pipeline(**kwargs)

    async def test_baseline_competes_even_when_a_composition_succeeds(self):
        flow, plan, baseline, runner = self.build()
        seen = []
        async def select(task, records):
            seen.extend(records)
            return SelectionDecision(records[0].run_id, 'Baseline satisfies the requirements')
        flow.selector.select = select
        outcome = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(len(seen), 4)
        self.assertEqual(outcome.harness, baseline)
        self.assertEqual(outcome.decision.assurance, 'selected')

    async def test_sequential_round_uses_retained_baseline_after_bad_candidates(self):
        flow, plan, baseline, _ = self.build()
        plan = replace(plan, mode='sequential', depth=2, feedback='scored')
        flow.measurements = type('Scores', (), {'measure': AsyncMock(side_effect=lambda task, record:
            Measurement(record.run_id, 'fixed', 1 if record.harness_id == baseline.snapshot_id else 0))})()
        requests = []
        original = flow.generators.factories['rule-generator']
        class Recording(original):
            async def propose(self, request, services):
                requests.append(request)
                return await super().propose(request, services)
        flow.generators.factories['rule-generator'] = Recording
        outcome = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(outcome.harness, baseline)
        self.assertTrue(all(q.baseline == baseline for q in requests))

    async def test_final_selection_timeout_preserves_completed_result(self):
        flow,plan,baseline,_=self.build()
        plan=replace(plan,timeouts={'editor_seconds':1,'execution_seconds':1,'evaluator_seconds':.01})
        async def select(*args):await asyncio.Event().wait()
        flow.selector.select=select
        outcome=await flow.run(plan,TaskMaterial('task','Do work'),baseline,WorkflowServices(plan))
        self.assertIsNotNone(outcome.selected)
        self.assertEqual(outcome.harness,baseline)
        self.assertEqual(outcome.decision.assurance,'selected')
