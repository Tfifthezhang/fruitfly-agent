"""User cancellation terminates quiet work while preserving session facts."""
import asyncio
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

from fruitfly_agent.core.config import AgentLoopConfig, ToolExecutionConfig
from fruitfly_agent.core.context import ContextPipeline, ContextStage
from fruitfly_agent.core.data_model import AssistantMessage, AgentToolResult, AgentLoopResult, TextBlock, ToolCallBlock, Usage
from fruitfly_agent.core.extensions.hooks import HookRegistry, AFTER_RESPONSE
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone, StreamActivity, TextDelta
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.interactive import InteractiveSession, AgentApplication, RunFinished, ApplicationState
from tests.support.application import _Factory
from tests.support.faux_provider import FauxProvider


class RunControlTests(unittest.IsolatedAsyncioTestCase):
    def quiet(self, entered, closed):
        def provider(view, *, signal=None):
            async def events():
                try:
                    entered.set()
                    await asyncio.Event().wait()
                    yield StreamDone(AssistantMessage())
                finally:
                    closed.set()
            return AssistantMessageEventStream(events())
        return provider

    async def test_cancel_quiet_provider_finishes_once_preserves_facts_and_accepts_next_turn(self):
        entered, closed = asyncio.Event(), asyncio.Event()
        provider = FauxProvider()
        provider.script.append(self.quiet(entered, closed))
        provider.respond_text('next answer')
        events = []
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as durable:
            session = InteractiveSession(AgentLoopConfig(provider=provider, session=durable, model='offline'), event_sink=events.append)
            submission = asyncio.create_task(session.submit('cancel me'))
            await asyncio.wait_for(entered.wait(), 1)
            self.assertTrue(session.cancel())
            self.assertTrue(session.cancel())  # repeated request must not interrupt finalization twice
            result = await asyncio.wait_for(submission, 1)
            self.assertEqual('aborted', result.stop_reason)
            self.assertTrue(closed.is_set())
            self.assertEqual(1, len([e for e in events if isinstance(e, RunFinished)]))
            records = [e.payload for e in durable.read_all() if e.payload.get('kind') == 'runRecord' and e.payload.get('event') == 'end']
            self.assertEqual(1, len(records))
            self.assertEqual('aborted', records[0]['data']['stop_reason'])
            self.assertEqual('next answer', (await session.submit('continue')).messages[-1].text)
            self.assertEqual(['cancel me', 'continue'], [m.content for m in durable.canonical_messages() if m.role == 'user'])

    async def test_external_task_cancellation_propagates_but_still_delivers_aborted_end(self):
        entered, closed = asyncio.Event(), asyncio.Event()
        events = []
        session = InteractiveSession(AgentLoopConfig(provider=self.quiet(entered, closed), model='offline'), event_sink=events.append)
        task = asyncio.create_task(session.submit('external'))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(closed.is_set())
        self.assertFalse(session.running)
        ends = [e for e in events if isinstance(e, RunFinished)]
        self.assertEqual(1, len(ends))
        self.assertEqual('aborted', ends[0].stop_reason)

    async def test_cancel_during_run_started_observer_still_interrupts_owned_task(self):
        entered, closed = asyncio.Event(), asyncio.Event()
        session = None
        def observe(event):
            if event.event_type == 'run_started':
                session.cancel()
        session = InteractiveSession(AgentLoopConfig(provider=self.quiet(entered, closed), model='offline'), event_sink=observe)
        result = await asyncio.wait_for(session.submit('cancel early'), 1)
        self.assertEqual('aborted', result.stop_reason)
        self.assertFalse(entered.is_set())

    async def test_tool_batch_keeps_completed_outcomes_and_marks_interrupted_and_unstarted(self):
        for parallel in (False, True):
            with self.subTest(parallel=parallel):
                entered = asyncio.Event()
                provider = FauxProvider()
                calls = [ToolCallBlock('first', 'fast', {}), ToolCallBlock('second', 'wait', {}), ToolCallBlock('third', 'later', {})]
                provider.script.append(lambda view, signal=None: AssistantMessageEventStream(self.final(AssistantMessage(content=calls, usage=Usage(10, 2)))))
                provider.respond_text('continued')
                effects = []
                async def fast(ctx):
                    effects.append('fast')
                    return AgentToolResult(content=[TextBlock('completed')])
                async def wait(ctx):
                    entered.set()
                    await asyncio.Event().wait()
                async def later(ctx):
                    effects.append('later')
                    return AgentToolResult(content=[])
                tools = tuple(AgentTool(name=name, label=name, description='', parameters={'type': 'object'}, execute=fn)
                              for name, fn in (('fast', fast), ('wait', wait), ('later', later)))
                config = AgentLoopConfig(provider=provider, model='offline', tools=tools,
                                         tool_execution=ToolExecutionConfig(max_parallel=1, default_execution_mode='parallel' if parallel else 'sequential'))
                session = InteractiveSession(config)
                task = asyncio.create_task(session.submit('tools'))
                await entered.wait()
                session.cancel()
                result = await asyncio.wait_for(task, 1)
                outcomes = [m for m in result.messages if m.role == 'toolResult']
                self.assertEqual(['first', 'second', 'third'], [m.tool_call_id for m in outcomes])
                self.assertEqual('completed', outcomes[0].text)
                self.assertFalse(outcomes[0].is_error)
                self.assertIn('unknown', outcomes[1].text)
                self.assertIn('not executed', outcomes[2].text)
                self.assertEqual(['fast'], effects)
                self.assertEqual((10, 2), (result.usage.input_tokens, result.tool_call_count))
                self.assertEqual('continued', (await session.submit('continue')).messages[-1].text)

    async def final(self, message):
        yield StreamDone(message)

    async def test_cancellation_before_tool_dispatch_pairs_committed_calls(self):
        entered = asyncio.Event()
        provider = FauxProvider()
        provider.respond_tool_call('never', {})
        hooks = HookRegistry()
        async def after(event):
            entered.set()
            await asyncio.Event().wait()
        hooks.on(AFTER_RESPONSE, after)
        session = InteractiveSession(AgentLoopConfig(provider=provider, hooks=hooks, model='offline'))
        task = asyncio.create_task(session.submit('stop before tools'))
        await entered.wait()
        session.cancel()
        result = await asyncio.wait_for(task, 1)
        self.assertEqual('aborted', result.stop_reason)
        self.assertEqual('toolResult', result.messages[-1].role)
        self.assertEqual(result.messages[-2].tool_calls[0].id, result.messages[-1].tool_call_id)

    async def test_cancel_clears_queue_and_close_and_rebuild_interrupt_quiet_work(self):
        for operation in ('cancel', 'close', 'rebuild'):
            with self.subTest(operation=operation):
                entered, closed = asyncio.Event(), asyncio.Event()
                first = InteractiveSession(AgentLoopConfig(provider=self.quiet(entered, closed), model='first'))
                second = InteractiveSession(AgentLoopConfig(provider=FauxProvider(), model='second'))
                application = AgentApplication(_Factory([first, second]))
                await application.start()
                application.enqueue('active')
                await entered.wait()
                application.enqueue('pending')
                if operation == 'cancel':
                    self.assertTrue(application.cancel())
                    await asyncio.wait_for(application.wait_until_idle(), 1)
                    self.assertEqual('aborted', application.last_result.stop_reason)
                else:
                    await asyncio.wait_for(getattr(application, operation)(), 1)
                self.assertTrue(closed.is_set())
                self.assertEqual(0, application.pending_count)
                self.assertEqual(1, first.status.message_count)
                if operation == 'close':
                    self.assertEqual(ApplicationState.CLOSED, application.state)
                elif operation == 'rebuild':
                    self.assertEqual('second', application.status.model)
                await application.close()

    async def test_shutdown_deadline_retains_uncooperative_runtime_without_closing_resources(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def uncooperative(config, messages, **kwargs):
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
            return AgentLoopResult(messages=list(messages), stop_reason='aborted')
        session = InteractiveSession(AgentLoopConfig(provider=FauxProvider()), run_loop=uncooperative)
        application = AgentApplication(_Factory([session]), shutdown_timeout=0.08)
        await application.start()
        submission = asyncio.create_task(application.submit('wait'))
        await entered.wait()
        try:
            with self.assertRaisesRegex(RuntimeError, 'runtime retained'):
                await application.close()
            self.assertEqual(ApplicationState.CLOSING, application.state)
            self.assertIsNotNone(application.last_error)
        finally:
            release.set()
            await submission
            await application.close()
