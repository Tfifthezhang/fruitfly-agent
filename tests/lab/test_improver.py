"""Stop, retention, quotas and fixed-field contracts for bounded experiments."""
import asyncio
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.lab.improvement.api import (BudgetScope, AllocationExhausted, WorkflowServices,
    SelectionDecision, Measurement, ComponentFile, CandidateBundle, HarnessSnapshot, EditReason,
    EditorInstructions, EditorInstructionTarget, BoundedStopPolicy, SearchState, TaskMaterial)
from tests.support.pipeline import build_pipeline


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_allocations_hold_quota_and_charge_leaf_once(self):
        root = BudgetScope({'model': 10, 'execution': 4})
        protected = root.child({'model': 4, 'execution': 2})
        search = root.child({'model': 6, 'execution': 2})
        with self.assertRaises(AllocationExhausted):
            root.reserve('model')
        leaf = search.child({'model': 3, 'execution': 1})
        leaf.reserve('model', 2)
        leaf.reserve('execution')
        self.assertEqual(root.used, {'model': 2, 'execution': 1})
        self.assertEqual(search.used, root.used)
        self.assertEqual(root.available('model'), 0)
        leaf.close()
        self.assertEqual(search.available('model'), 4)
        search.close()
        self.assertEqual(root.available('model'), 4)
        protected.reserve('model', 4)
        protected.close()
        self.assertEqual(root.used['model'], 6)
        self.assertEqual(root.available('model'), 4)
        root.close()

    async def test_deadline_and_cancellation_are_inherited(self):
        root = BudgetScope({'model': 5, 'execution': 5}, deadline=time.monotonic() + 30)
        child = root.child({'model': 2, 'execution': 2}, timeout=1)
        self.assertLess(child.deadline, root.deadline)
        root.signal.set()
        with self.assertRaises(asyncio.CancelledError):
            child.reserve('model')
        child.close()
        self.assertEqual(root.used['model'], 0)

    def test_editor_candidate_cannot_change_fixed_fields(self):
        instructions = EditorInstructions()
        target = EditorInstructionTarget(instructions)
        target.validate(replace(instructions, invariant='Use a different proposal procedure').serialize())
        for field in ('system', 'select', 'reflect'):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'frozen'):
                target.validate(replace(instructions, **{field: 'Mutated field'}).serialize())
        formatted = json.dumps(json.loads(instructions.serialize()), indent=2)
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

    async def test_budget_exhaustion_preserves_completed_result(self):
        flow, plan, baseline, _ = self.build()
        plan = replace(plan, max_executions=2)
        outcome = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(outcome.stop_reason, 'budget_exhausted')
        self.assertIsNotNone(outcome.selected)
        self.assertEqual(outcome.decision.assurance, 'selected')
