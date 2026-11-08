"""Independent stage clocks and observational usage, without quota allocation."""
import asyncio
import unittest
from dataclasses import replace

from fruitfly_agent.improvement.contracts.plans import StageTimeouts
from fruitfly_agent.improvement.stages.services import StageServices
from tests.support.stages import proposal_fixture


class StageTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_editor_timeout_does_not_consume_evaluator_time(self):
        _,plan,_,_=proposal_fixture()
        plan=replace(plan,timeouts=StageTimeouts(.01,.1,.1))
        async with StageServices(plan) as services:
            with self.assertRaises(TimeoutError):
                await services.operation(asyncio.sleep(10),stage='editor')
            self.assertFalse(services.signal.is_set())
            await services.operation(asyncio.sleep(.02),stage='evaluator')
            records=[f for e,f in services.events if e=='operation-finished']
            self.assertEqual([r['status'] for r in records],['timeout','completed'])

    async def test_nested_same_role_shares_invocation_time(self):
        _,plan,_,_=proposal_fixture()
        plan=replace(plan,timeouts=StageTimeouts(.03,.1,.1))
        async with StageServices(plan) as services:
            async def edit():
                await asyncio.sleep(.02)
                await services.operation(asyncio.sleep(.02),stage='editor')
            with self.assertRaises(TimeoutError):await services.operation(edit(),stage='editor')
            self.assertEqual(sum(e=='operation-started'for e,_ in services.events),1)

    async def test_user_cancellation_propagates_to_active_stage(self):
        _,plan,_,_=proposal_fixture()
        async with StageServices(plan) as services:
            entered=asyncio.Event()
            async def work():entered.set();await asyncio.Event().wait()
            pending=asyncio.create_task(services.operation(work(),stage='execution'))
            await entered.wait();services.signal.set()
            with self.assertRaises(asyncio.CancelledError):await pending

    def test_times_are_strict_and_have_no_arbitrary_upper_ceiling(self):
        for value in (0,-1,True,float('inf'),float('nan')):
            with self.subTest(value=value),self.assertRaises(ValueError):StageTimeouts(editor_seconds=value)
        self.assertEqual(StageTimeouts(editor_seconds=100000).editor_seconds,100000)
