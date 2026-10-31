"""Independent stage clocks and observational usage, without quota allocation."""
import asyncio
import unittest
from dataclasses import replace

from fruitfly_agent.improvement.contracts.plans import StageTimeouts
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from tests.support.pipeline import build_pipeline


class StageTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_editor_timeout_does_not_consume_evaluator_time(self):
        _,plan,_,_=build_pipeline()
        plan=replace(plan,timeouts=StageTimeouts(.01,.1,.1))
        async with WorkflowServices(plan) as services:
            with self.assertRaises(TimeoutError):
                await services.operation(asyncio.sleep(10),stage='editor')
            self.assertFalse(services.signal.is_set())
            await services.operation(asyncio.sleep(.02),stage='evaluator')
            records=[f for e,f in services.events if e=='operation-finished']
            self.assertEqual([r['status'] for r in records],['timeout','completed'])

    async def test_nested_same_role_shares_invocation_time(self):
        _,plan,_,_=build_pipeline()
        plan=replace(plan,timeouts=StageTimeouts(.03,.1,.1))
        async with WorkflowServices(plan) as services:
            async def edit():
                await asyncio.sleep(.02)
                await services.operation(asyncio.sleep(.02),stage='editor')
            with self.assertRaises(TimeoutError):await services.operation(edit(),stage='editor')
            self.assertEqual(sum(e=='operation-started'for e,_ in services.events),1)

    async def test_user_cancellation_propagates_to_active_stage(self):
        _,plan,_,_=build_pipeline()
        async with WorkflowServices(plan) as services:
            entered=asyncio.Event()
            async def work():entered.set();await asyncio.Event().wait()
            pending=asyncio.create_task(services.operation(work(),stage='execution'))
            await entered.wait();services.signal.set()
            with self.assertRaises(asyncio.CancelledError):await pending

    def test_times_are_strict_and_have_no_arbitrary_upper_ceiling(self):
        for value in (0,-1,True,float('inf'),float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):StageTimeouts(editor_seconds=value)
        self.assertEqual(StageTimeouts(editor_seconds=100000).editor_seconds,100000)

    async def test_execution_timeout_preserves_partial_evidence_with_matching_facts(self):
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
        from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts, read_facts
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        flow, plan, baseline, runner = build_pipeline()
        plan = replace(plan, strategy_id='simple', component_ids=('prompt',), retain_experience=False,
                       timeouts=StageTimeouts(.1, .01, .1))
        flow.artifacts = artifacts = MemoryArtifacts()
        original = runner.execute
        async def interrupted(plan, task, harness):
            record = await original(plan, task, harness)
            resource = Resource('partial.log', artifacts.put(b'work observed'), kind='trajectory')
            record = replace(record, status='cancelled', artifacts=(resource,))
            record = attach_facts(record, receipt_facts(record, artifacts, diagnosable=True), artifacts)
            try:
                await asyncio.Event().wait()
            finally:
                services.retain_execution(record)
        runner.execute = interrupted
        async with WorkflowServices(plan) as services:
            outcome = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
        self.assertTrue(outcome.records)
        record = outcome.records[0]
        self.assertEqual(record.status, 'timeout')
        self.assertEqual(read_facts(record, artifacts).termination_reason, 'execution_timeout')
        self.assertTrue(any(r.path == 'partial.log' for r in record.artifacts))
        self.assertFalse(services.signal.is_set())
