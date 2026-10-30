"""Reliability behavior and failure contracts."""
import asyncio
from dataclasses import replace
import unittest
from unittest.mock import AsyncMock
from fruitfly_agent.improvement.contracts.failures import IntegrityError, PersistenceError, CleanupError
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.pipeline import build_pipeline


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_failure_preserves_reference_and_checkpoint(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.generators.factories['rule-generator'] = lambda: type('Broken', (), {
            'generator_id': 'rule-generator', 'required_capabilities': frozenset(), 'propose': AsyncMock(side_effect=RuntimeError('broken'))})()
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
        self.assertEqual(result.stop_reason, 'stage_failed.propose')
        self.assertEqual(result.harness, baseline)
        self.assertIsNotNone(result.selected)
        checkpoints = [fields['outcome'] for event, fields in services.events if event == 'workflow-checkpoint']
        self.assertEqual(checkpoints[-1]['selected']['run_id'], result.selected.run_id)
        await services.close()

    async def test_candidate_timeouts_keep_baseline_and_do_not_invent_measurements(self):
        flow, plan, baseline, runner = build_pipeline()
        original = runner.execute
        async def execute(plan, task, harness):
            if harness != baseline:
                await asyncio.Event().wait()
            return await original(plan, task, harness)
        runner.execute = execute
        plan = replace(plan, operation_timeout=.01)
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
        self.assertEqual(result.harness, baseline)
        self.assertTrue(any(r.status == 'error' for r in result.records))
        self.assertTrue(all(r.model_calls is None for r in result.records if r.status == 'error'))
        self.assertEqual(result.decision.assurance, 'selected')
        await services.close()

    async def test_missing_scores_cannot_promote_a_candidate(self):
        flow, plan, baseline, _ = build_pipeline()
        flow.measurements = type('BrokenScores', (), {'measure': AsyncMock(side_effect=OSError('unavailable'))})()
        plan = replace(plan, feedback='scored')
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        self.assertEqual(result.harness, baseline)
        self.assertIsNotNone(result.selected)
        self.assertNotEqual(result.decision.assurance, 'verified')

    async def test_diagnosable_failed_reference_can_generate_without_fabricating_baseline_score(self):
        flow, plan, baseline, runner = build_pipeline()
        artifacts = flow.artifacts = MemoryArtifacts()
        original = runner.execute
        async def execute(plan, task, harness):
            record = await original(plan, task, harness)
            if harness == baseline:
                record = replace(record, status='error', output='Partial work; tool allowance exhausted')
                record = attach_facts(record, receipt_facts(record, artifacts, diagnosable=True,
                    termination_reason='tool_limit'), artifacts)
            return record
        runner.execute = execute
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        self.assertTrue(result.candidates)
        self.assertEqual(result.selected.status, 'completed')
        self.assertTrue(all(r.status == 'error' for r in result.records if r.harness_id == baseline.snapshot_id))

    async def test_receipt_mismatch_and_persistence_failure_are_fatal(self):
        flow, plan, baseline, runner = build_pipeline()
        original = runner.execute
        async def wrong(*args):
            return replace(await original(*args), task_id='other-task')
        runner.execute = wrong
        with self.assertRaises(IntegrityError):
            await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        async def work():
            return 1
        def failed_sink(event, **fields):
            raise OSError('disk full')
        services = WorkflowServices(plan, record=failed_sink)
        with self.assertRaises(PersistenceError):
            services.record('checkpoint')
        await services.close()

    async def test_cleanup_attempts_all_resources_and_closes_budget(self):
        _, plan, _, _ = build_pipeline()
        closed = []
        class Resource:
            def __init__(self, name): self.name = name
            async def aclose(self):
                closed.append(self.name)
                if self.name == 'bad': raise OSError('failed close')
        services = WorkflowServices(plan)
        services.own(Resource('good')); services.own(Resource('bad'))
        with self.assertRaises(CleanupError): await services.close()
        self.assertEqual(closed, ['bad', 'good'])
        self.assertTrue(services.budget.closed)
