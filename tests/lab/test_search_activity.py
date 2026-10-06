"""Common progress from actual services, including waits, errors and cancellation."""
import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.lab.optimization.search import TaskCase
from tests.support.search import problem, services, engineer
from tests.support.faux_provider import FauxProvider


class SearchActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_batch_progress_and_root_usage_are_distinct(self):
        entered=[asyncio.Event(),asyncio.Event()];release=[asyncio.Event(),asyncio.Event()]
        index=0
        async def evaluate(text,case):
            nonlocal index
            current=index;index+=1;entered[current].set()
            await release[current].wait()
            if current==1:raise ValueError('private task failure')
            return 1
        p=replace(problem(),train=(TaskCase('one','SECRET_ONE'),TaskCase('two','SECRET_TWO')))
        service=services(p=p,evaluator=evaluate)
        task=asyncio.create_task(service.evaluate(p.baseline.text,'train'))
        try:
            await asyncio.wait_for(entered[0].wait(),1)
            value=service.progress()
            self.assertEqual(('Evaluating training',0,2,0,1),(value.phase,value.completed,value.total,value.model_calls,value.trial_calls))
            self.assertNotIn('SECRET',repr(value))
            release[0].set();await asyncio.wait_for(entered[1].wait(),1)
            self.assertEqual((1,2),(service.progress().completed,service.progress().trial_calls))
            release[1].set();await task
            self.assertEqual((2,2,1),(service.progress().completed,service.progress().total,service.progress().failed_trials))
            self.assertEqual(0,service.progress().model_calls)
        finally:
            for gate in release:gate.set()
            if not task.done():task.cancel()
            await asyncio.gather(task,return_exceptions=True)

    async def test_cancelled_trial_is_not_reported_as_completed(self):
        entered=asyncio.Event()
        async def evaluate(*args):
            entered.set();await asyncio.Event().wait()
        service=services(evaluator=evaluate)
        task=asyncio.create_task(service.evaluate('seed','validation'))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual((0,1,1),(service.progress().completed,service.progress().total,service.progress().trial_calls))

    async def test_generation_and_tool_agent_report_common_phases(self):
        provider=FauxProvider();provider.respond_text('new prompt')
        service=services(provider)
        await service.complete('optimizer','system','prompt')
        self.assertEqual(('Generating (optimizer)',0,1),(service.progress().phase,service.progress().total,service.progress().model_calls))
        engineer(provider,'method',role='meta')
        await service.agent('meta','system','prompt',files={'history.json':'[]'},output_path='learning-context/SKILL.md')
        self.assertEqual('Tool agent (meta)',service.progress().phase)
        self.assertEqual(4,service.progress().model_calls)
        self.assertEqual((22,12,4,0), (service.progress().tokens.input_tokens, service.progress().tokens.output_tokens,
                                                  service.progress().tokens.reported_calls, service.progress().tokens.missing_calls))
