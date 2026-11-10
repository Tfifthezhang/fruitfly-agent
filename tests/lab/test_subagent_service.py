"""Delegation scheduling, reliable result reads and bounded cancellation."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, UserMessage
from fruitfly_agent.lab.agents.subagent.service import SubagentError
from fruitfly_agent.lab.agents.subagent.storage import SubagentStore
from tests.support.subagents import ChildFixture
from tests.support.faux_provider import FauxProvider

class SubagentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = ChildFixture(self.directory.name)
        self.service = self.fixture.service(run_timeout_seconds=2, retirement_timeout=.1)
        self.expect_cleanup_failure = False
        async def cleanup():
            if self.expect_cleanup_failure:
                from fruitfly_agent.core.extensions.operations import OperationCleanupError
                with self.assertRaises(OperationCleanupError):
                    await self.service.close()
            else:
                await self.service.close()
        self.addAsyncCleanup(cleanup)
        self.service.begin()

    async def finish(self, row):
        return (await self.service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2))['executions'][0]

    async def test_result_survives_repeated_reads_and_followup_rebuilds_private_history(self):
        row = self.service.spawn('Inspect')
        first = await self.finish(row)
        self.assertEqual(('completed', 'confirmed'), (first['state'], first['cleanup']))
        self.assertEqual(1, self.fixture.closed)
        self.assertEqual(first, await self.finish(row))
        self.assertEqual('child result', self.fixture.store.read_result(first)['output'])
        second = self.service.send(row['agent_id'], row['run_id'], 'followup', 'Check again')
        self.assertNotEqual(row['run_id'], second['run_id'])
        await self.finish(second)
        self.assertEqual(['Inspect', 'child result', 'Check again'],
            [m.content if isinstance(m.content, str) else m.text for m in self.fixture.providers[1].calls[0]['messages']])
        with self.assertRaisesRegex(SubagentError, 'stale_run'):
            await self.service.cancel(row['agent_id'], row['run_id'])

    async def test_scope_and_capacity_do_not_leak_to_another_parent_task(self):
        self.service.max_agents = 1
        row = self.service.spawn('Inspect')
        await self.finish(row)
        with self.assertRaisesRegex(SubagentError, 'capacity_exceeded'):
            self.service.spawn('Other')
        await self.service.end()
        self.service.begin()
        with self.assertRaisesRegex(SubagentError, 'scope_closed'):
            self.service.send(row['agent_id'], row['run_id'], 'followup', 'Other task')
        self.assertEqual('completed', self.service.detail(row['agent_id'])['state'])

    async def test_queue_is_bounded_by_slots_and_wait_timeout_does_not_cancel(self):
        gate = asyncio.Event()
        entered = asyncio.Event()
        active, peak = 0, 0
        def provider(request):
            async def stream():
                nonlocal active, peak
                active += 1; peak = max(active, peak); entered.set()
                try:
                    await gate.wait()
                    yield StreamDone(AssistantMessage([TextBlock('done')], 'stop'))
                finally:
                    active -= 1
            return lambda view, signal=None: AssistantMessageEventStream(stream())
        self.fixture.provider = provider
        self.service.slots = asyncio.Semaphore(1)
        first, second = self.service.spawn('one'), self.service.spawn('two')
        await asyncio.wait_for(entered.wait(), 1)
        value = await self.service.wait([(second['agent_id'], second['run_id'])], timeout_seconds=0)
        self.assertTrue(value['timed_out'])
        self.assertEqual('queued', value['executions'][0]['state'])
        self.service.send(second['agent_id'], second['run_id'], 'steer', 'Extra queued context')
        gate.set()
        await self.finish(first); await self.finish(second)
        self.assertEqual(1, peak)
        self.assertTrue(any('Extra queued context' in str(m.to_dict()) for m in self.fixture.sessions[1].canonical_messages()))

    async def test_cancel_waiter_does_not_cancel_child_and_child_cancel_confirms_cleanup(self):
        entered = asyncio.Event()
        def provider(request):
            async def stream():
                entered.set()
                await asyncio.Event().wait()
                yield StreamDone(AssistantMessage([TextBlock('unreachable')], 'stop'))
            return lambda view, signal=None: AssistantMessageEventStream(stream())
        self.fixture.provider = provider
        row = self.service.spawn('wait')
        await asyncio.wait_for(entered.wait(), 1)
        waiter = asyncio.create_task(self.service.wait([(row['agent_id'], row['run_id'])]))
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError): await waiter
        self.assertEqual('running', self.service.detail(row['agent_id'])['state'])
        cancelled = await self.service.cancel(row['agent_id'], row['run_id'])
        self.assertEqual(('cancelled', 'confirmed'), (cancelled['state'], cancelled['cleanup']))
        self.assertEqual(1, self.fixture.closed)

    async def test_queue_time_counts_toward_execution_deadline(self):
        self.service.timeout = .02
        self.service.slots = asyncio.Semaphore(0)
        row = self.service.spawn('queued')
        result = await self.finish(row)
        self.assertEqual('timed_out', result['state'])
        self.assertEqual(0, self.fixture.started)

    async def test_reopen_recognizes_unfinished_records_without_replaying_them(self):
        row = self.service.spawn('one')
        result = await self.finish(row)
        self.fixture.store.save({**result, 'state': 'running', 'delivered': False})
        await self.service.end()
        self.fixture.store.close()
        restored = SubagentStore(self.fixture.root / 'children', self.fixture.store.artifacts)
        self.addCleanup(restored.close)
        self.assertEqual('interrupted', restored.rows[row['run_id']]['state'])
        self.assertEqual('host_interrupted', restored.rows[row['run_id']]['error'])

    async def test_parent_final_response_collects_children_before_final_integration(self):
        await self.service.end()
        parent = FauxProvider()
        captured = []
        async def delegate(ctx):
            row = self.service.spawn('inspect')
            captured.append(row)
            from fruitfly_agent.core.data_model import AgentToolResult
            return AgentToolResult([TextBlock('accepted')])
        from fruitfly_agent.core.tool_runtime import AgentTool
        from fruitfly_agent.core.config import AgentLoopConfig
        parent.respond_tool_call('delegate', {})
        parent.respond_text('provisional')
        parent.respond_text('integrated')
        tool = AgentTool('delegate', 'Delegate', 'Delegate', {'type': 'object'}, delegate)
        result = await self.service.run_loop(AgentLoopConfig(parent, tools=(tool,)), [UserMessage('root')])
        self.assertFalse(result.is_error)
        self.assertEqual('integrated', result.messages[-1].text)
        self.assertTrue(self.service.detail(captured[0]['agent_id'])['delivered'])
        self.assertEqual(1, self.fixture.closed)


    async def test_prepare_and_start_failure_never_leave_an_execution_running(self):
        async def broken(request): raise RuntimeError('prepare failed')
        self.service.prepare = broken
        row = self.service.spawn('prepare')
        result = await self.finish(row)
        self.assertEqual(('failed', 'confirmed'), (result['state'], result['cleanup']))
        from dataclasses import replace
        async def broken_start(request):
            runtime = await self.fixture.prepare(request)
            async def start(): raise RuntimeError('startup failed')
            return replace(runtime, start=start)
        self.service.prepare = broken_start
        row = self.service.spawn('start')
        self.assertEqual('failed', (await self.finish(row))['state'])
        self.assertEqual(1, self.fixture.closed)

    async def test_unconfirmed_cleanup_blocks_followup_and_reports_separate_failure(self):
        from dataclasses import replace
        from fruitfly_agent.core.extensions.operations import OperationCleanupError
        gate = asyncio.Event()
        async def prepare(request):
            runtime = await self.fixture.prepare(request)
            async def close():
                try: await gate.wait()
                except asyncio.CancelledError: await gate.wait()
                await runtime.close()
            return replace(runtime, close=close)
        self.service.prepare = prepare
        row = self.service.spawn('cleanup')
        # Once poison is recorded, ordinary waits fail rather than hanging.
        await asyncio.wait_for(self.service.tasks[row['run_id']], 1)
        value = self.service.detail(row['agent_id'])
        self.assertEqual('failed', value['cleanup'])
        self.assertTrue(self.service.poisoned)
        with self.assertRaisesRegex(SubagentError, 'scope_closed'):
            self.service.spawn('more')
        gate.set()
        # Let the quarantined cleanup finish, but retain the failure fact.
        await asyncio.sleep(0)
        with self.assertRaises(OperationCleanupError): await self.service.end()
        # Retain the poisoned state and assert its failure during fixture cleanup.
        self.expect_cleanup_failure = True


    async def test_failed_followup_does_not_republish_the_previous_answer(self):
        row = self.service.spawn('first')
        first = await self.finish(row)
        self.assertEqual('child result', first['summary'])
        def failure(request):
            provider = FauxProvider(); provider.respond_fatal('offline failure'); return provider
        self.fixture.provider = failure
        second = self.service.send(row['agent_id'], row['run_id'], 'followup', 'follow up')
        result = await self.finish(second)
        self.assertEqual('failed', result['state'])
        self.assertEqual('', self.fixture.store.read_result(result)['output'])

    async def test_parent_history_failure_does_not_acknowledge_uncommitted_child_result(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import AgentToolResult
        from fruitfly_agent.core.session import Session
        from fruitfly_agent.core.tool_runtime import AgentTool
        await self.service.end()
        parent = FauxProvider()
        parent.respond_tool_call('delegate', {})
        parent.respond_text('provisional')
        async def delegate(ctx):
            self.service.spawn('Inspect')
            return AgentToolResult([TextBlock('accepted')])
        tool = AgentTool('delegate', 'Delegate', 'Delegate', {'type': 'object'}, delegate)
        with Session(self.fixture.root / 'parent.jsonl') as session:
            original = session.append
            def append(kind, payload, **kwargs):
                if kind == 'message' and payload.get('message', {}).get('kind') == 'subagent-result':
                    raise OSError('offline parent history failure')
                return original(kind, payload, **kwargs)
            session.append = append
            with self.assertLogs('fruitfly_agent.core.loop', level='ERROR'):
                result = await self.service.run_loop(AgentLoopConfig(parent, session=session, tools=(tool,)), [UserMessage('root')])
            self.assertTrue(result.is_error)
            self.assertFalse(self.service.snapshot()['executions'][0]['delivered'])
            self.assertEqual(2, len(parent.calls))


    async def test_execution_slot_is_held_until_owned_resources_retire(self):
        from dataclasses import replace
        closing, release = asyncio.Event(), asyncio.Event()
        self.service.slots = asyncio.Semaphore(1)
        calls = 0
        async def prepare(request):
            nonlocal calls
            calls += 1
            runtime = await self.fixture.prepare(request)
            if calls == 1:
                async def close():
                    closing.set()
                    await release.wait()
                    await runtime.close()
                return replace(runtime, close=close)
            return runtime
        self.service.prepare = prepare
        first = self.service.spawn('one')
        second = self.service.spawn('two')
        await asyncio.wait_for(closing.wait(), 1)
        self.assertEqual(1, self.fixture.started)
        self.assertEqual('queued', self.service.detail(second['agent_id'])['state'])
        release.set()
        await self.finish(first); await self.finish(second)
        self.assertEqual(2, self.fixture.closed)
