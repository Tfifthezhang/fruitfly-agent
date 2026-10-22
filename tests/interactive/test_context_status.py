"""Status observes prepared projections and receipts without preparing requests."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context import ContextFrame, ContextPipeline, ContextStage
from fruitfly_agent.core.data_model import AgentToolResult, AssistantMessage, ContextDecision, TextBlock, Usage, UserMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone, StreamActivity, TextDelta
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime import AgentTool
from fruitfly_agent.interactive import InteractiveSession, RunActivityChanged, RunStarted
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from tests.support.faux_provider import FauxProvider


class ContextStatusTests(unittest.IsolatedAsyncioTestCase):
    def test_request_prepared_only_accepts_passive_observers(self):
        from fruitfly_agent.core.extensions.hooks import HookRegistry, REQUEST_PREPARED
        hooks = HookRegistry()
        with self.assertRaisesRegex(ValueError, "observation"):
            hooks.add(REQUEST_PREPARED, lambda event: event)
        hooks.on(REQUEST_PREPARED, lambda event: None)

    def receipt(self, provider, tokens):
        async def final():
            yield StreamDone(AssistantMessage(content=[TextBlock('answer')], stop_reason='stop',
                                             usage=None if tokens is None else Usage(tokens, 2)))
        provider.script.append(lambda view, signal=None: AssistantMessageEventStream(final()))

    async def test_message_count_uses_canonical_records_after_reduction_and_restore(self):
        class Reduce:
            def estimate(self, snapshot):
                return 25
            async def check_budget(self, snapshot):
                return ContextDecision(messages=(UserMessage('summary'),), mechanism_id='fixture')
            async def react_to_overflow(self, snapshot, error):
                return None

        provider = FauxProvider()
        provider.respond_text('first answer')
        provider.respond_text('second answer')
        pipeline = ContextPipeline((ContextStage('reduce', 'reduction', Reduce()),))
        events = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            with Session(path) as durable:
                for message in (UserMessage('original question'), AssistantMessage([TextBlock('original answer')])):
                    durable.append('message', {'message': message.to_dict()})
                durable.append('meta', {'kind': 'fixture'})
                config = AgentLoopConfig(provider=provider, model='offline', session=durable)
                session = InteractiveSession(config, messages=durable.messages(), context_pipeline=pipeline,
                                             event_sink=events.append)
                await session.submit('first task')
                self.assertEqual(2, len(session.messages))
                self.assertEqual(4, session.status.message_count)
                await session.submit('second task')
                self.assertEqual(2, len(session.messages))
                self.assertEqual(6, session.status.message_count)
                self.assertEqual([3, 5], [event.message_count for event in events if isinstance(event, RunStarted)])
                self.assertEqual(2, session.status.compaction_count)
                before = path.read_bytes()
                text = CommandRouter().execute(InteractiveCommand('status'), session).text
                self.assertIn('messages: 6\n', text)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(2, len(provider.calls))
            with Session(path) as durable:
                restored = InteractiveSession(replace(config, session=durable), messages=durable.messages())
                self.assertEqual(2, len(restored.messages))
                self.assertEqual(6, restored.status.message_count)
                self.assertEqual(2, restored.status.compaction_count)

    async def test_message_count_updates_during_tools_and_counts_only_committed_messages(self):
        provider = FauxProvider()
        provider.respond_tool_call('pause', {})
        entered_tool = asyncio.Event()
        release_tool = asyncio.Event()
        entered_response = asyncio.Event()
        finish_response = asyncio.Event()

        async def execute(ctx):
            entered_tool.set()
            await release_tool.wait()
            return AgentToolResult(content=[TextBlock('tool result')])

        async def final_response():
            yield TextDelta('partial ')
            yield TextDelta('answer')
            entered_response.set()
            await finish_response.wait()
            yield StreamDone(AssistantMessage(content=[TextBlock('partial answer')], stop_reason='stop'))

        provider.script.append(lambda view, signal=None: AssistantMessageEventStream(final_response()))
        tool = AgentTool('pause', 'pause', 'offline barrier', {'type': 'object'}, execute)
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as durable:
            session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline', session=durable, tools=(tool,)))
            task = asyncio.create_task(session.submit('use the tool'))
            try:
                await asyncio.wait_for(entered_tool.wait(), timeout=2)
                self.assertTrue(session.running)
                self.assertEqual(1, len(session.messages))
                self.assertEqual(2, session.status.message_count)
                self.assertTrue(session.steer('follow-up guidance'))
                self.assertEqual(2, session.status.message_count)
                release_tool.set()
                await asyncio.wait_for(entered_response.wait(), timeout=2)
                self.assertTrue(session.running)
                self.assertEqual(4, session.status.message_count)
                before = durable.read_all()
                text = CommandRouter().execute(InteractiveCommand('status'), session).text
                self.assertIn('messages: 4\n', text)
                self.assertEqual(before, durable.read_all())
                self.assertEqual(2, len(provider.calls))
            finally:
                release_tool.set()
                finish_response.set()
                await task
            self.assertEqual(5, session.status.message_count)

    async def test_message_count_keeps_committed_results_after_cancellation(self):
        provider = FauxProvider()
        provider.respond_tool_call('pause', {})
        entered_tool = asyncio.Event()

        async def execute(ctx):
            entered_tool.set()
            await asyncio.Event().wait()

        tool = AgentTool('pause', 'pause', 'offline cancellation barrier', {'type': 'object'}, execute)
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as durable:
            session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline', session=durable, tools=(tool,)))
            task = asyncio.create_task(session.submit('cancel the tool'))
            try:
                await asyncio.wait_for(entered_tool.wait(), timeout=2)
                self.assertEqual(2, session.status.message_count)
            finally:
                session.cancel()
                result = await task
            self.assertEqual('aborted', result.stop_reason)
            self.assertEqual(3, session.status.message_count)
            self.assertEqual(['user', 'assistant', 'toolResult'], [message.role for message in durable.canonical_messages()])

    async def test_last_receipt_is_separate_from_cumulative_and_restores_without_requests(self):
        provider = FauxProvider()
        self.receipt(provider, 10)
        self.receipt(provider, 12)
        consumed = False
        def follow_up(ctx):
            nonlocal consumed
            if consumed:
                return []
            consumed = True
            return [UserMessage(content='follow up')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            with Session(path) as durable:
                config = AgentLoopConfig(provider=provider, model='offline', context_window=1000, max_tokens=100,
                                         session=durable, get_follow_up_messages=follow_up)
                session = InteractiveSession(config)
                await session.submit('two requests')
                status = session.status
                self.assertEqual((12, 22, 4), (status.last_input_tokens, status.run_input_tokens, status.run_output_tokens))
                self.assertIsNone(status.estimated_input_tokens)
                before = path.read_bytes()
                text = CommandRouter().execute(InteractiveCommand('status'), session).text
                self.assertIn('context usage: [--------------------] 1.2% (reported; last request)', text)
                self.assertEqual(['context usage: [--------------------] 1.2% (reported; last request)', 'compactions: 0'],
                                 text.split('pending candidates: 0\n')[1].splitlines())
                self.assertNotIn('2.2%', text)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(2, len(provider.calls))
            with Session(path) as durable:
                config = replace(config, session=durable)
                before = path.read_bytes()
                restored = InteractiveSession(config, messages=durable.messages())
                self.assertEqual(status.last_input_tokens, restored.status.last_input_tokens)
                self.assertEqual(status.receipt_model, restored.status.receipt_model)
                self.assertEqual(status.receipt_timestamp, restored.status.receipt_timestamp)
                self.assertEqual(22, restored.status.run_input_tokens)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(2, len(provider.calls))

    async def test_estimate_uses_final_projection_after_transforms_and_reduction(self):
        observations = []
        class Augment:
            def transform(self, frame):
                return replace(frame, system_prompt='augmented prompt')
        class Externalize:
            def transform(self, frame):
                return replace(frame, messages=(UserMessage(content='external reference'),))
        class Reduce:
            estimate_source = 'offline exact fixture'
            calls = 0
            def estimate(self, snapshot):
                observations.append(snapshot)
                return 25
            async def check_budget(self, snapshot):
                self.calls += 1
                return ContextDecision(messages=(UserMessage(content='reduced projection'),), mechanism_id='fixture')
            async def react_to_overflow(self, snapshot, error):
                return None
        reducer = Reduce()
        pipeline = ContextPipeline((ContextStage('augment', 'augmentation', Augment()),
                                    ContextStage('externalize', 'externalization', Externalize()),
                                    ContextStage('reduce', 'reduction', reducer)))
        provider = FauxProvider()
        self.receipt(provider, 30)
        tool = AgentTool('fixture', 'fixture', 'tool schema', {'type': 'object'}, lambda ctx: None)
        session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline', tools=(tool,), context_window=1000),
                                     context_pipeline=pipeline)
        await session.submit('original')
        self.assertEqual('augmented prompt', observations[-1].system_prompt)
        self.assertEqual('reduced projection', observations[-1].messages[0].content)
        self.assertEqual((tool,), observations[-1].tools)
        status = session.status
        self.assertEqual(25, status.estimated_input_tokens)
        self.assertEqual('reduce: offline exact fixture', status.estimate_source)
        before = len(observations)
        for _ in range(3):
            text = CommandRouter().execute(InteractiveCommand('status'), session).text
        self.assertIn('context usage: [--------------------] 2.5% (estimated; last request)', text)
        self.assertIn('compactions: 1', text)
        self.assertEqual(before, len(observations))
        self.assertEqual(1, reducer.calls)

    async def test_missing_receipt_replaces_previous_value_with_unknown(self):
        provider = FauxProvider()
        self.receipt(provider, 10)
        self.receipt(provider, None)
        session = InteractiveSession(AgentLoopConfig(provider=provider, model='offline'))
        await session.submit('known')
        await session.submit('unknown')
        self.assertIsNone(session.status.last_input_tokens)
        self.assertIsNotNone(session.status.receipt_timestamp)
        self.assertIn('context usage: unknown', CommandRouter().execute(InteractiveCommand('status'), session).text)

    async def test_compaction_count_accumulates_restores_and_excludes_cancelled_proposals(self):
        from fruitfly_agent.core.extensions.hooks import BEFORE_COMPACTION, HookRegistry

        class Reduce:
            def estimate(self, snapshot):
                return 25
            async def check_budget(self, snapshot):
                return ContextDecision(messages=snapshot.messages, mechanism_id='fixture')
            async def react_to_overflow(self, snapshot, error):
                return None

        hooks = HookRegistry()
        cancel = False
        def review(event):
            event.cancel = cancel
        hooks.add(BEFORE_COMPACTION, review)
        pipeline = ContextPipeline((ContextStage('reduce', 'reduction', Reduce()),))
        provider = FauxProvider()
        for _ in range(4):
            self.receipt(provider, 30)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            with Session(path) as durable:
                config = AgentLoopConfig(provider=provider, model='offline', session=durable, hooks=hooks)
                session = InteractiveSession(config, context_pipeline=pipeline)
                self.assertEqual(0, session.status.compaction_count)
                await session.submit('first')
                await session.submit('second')
                self.assertEqual(2, session.status.compaction_count)
                cancel = True
                await session.submit('cancel proposal')
                self.assertEqual(2, session.status.compaction_count)
                self.assertEqual(2, sum(entry.type == 'compaction' for entry in durable.read_all()))
            with Session(path) as durable:
                before = path.read_bytes()
                session = InteractiveSession(replace(config, session=durable), messages=durable.messages(),
                                             context_pipeline=pipeline)
                self.assertEqual(2, session.status.compaction_count)
                CommandRouter().execute(InteractiveCommand('status'), session)
                self.assertEqual(before, path.read_bytes())
                self.assertEqual(3, len(provider.calls))
                cancel = False
                await session.submit('after restore')
                self.assertEqual(3, session.status.compaction_count)

    def test_ratio_rejects_other_models_and_missing_window_without_clamping_overflow(self):
        from types import SimpleNamespace
        from fruitfly_agent.interactive.contracts.models import InteractiveStatus
        status = InteractiveStatus(model='current', working_directory='', session_path='',
                                   message_count=0, tool_names=(), mechanisms=(), context_window=1000,
                                   estimated_input_tokens=1200, estimate_model='current')
        def render(value):
            return CommandRouter().execute(InteractiveCommand('status'), SimpleNamespace(status=value)).text
        self.assertIn('context usage: [####################] 120.0%', render(status))
        self.assertIn('context usage: unknown', render(replace(status, estimate_model='other')))
        self.assertIn('context usage: unknown', render(replace(status, context_window=0)))

    def test_context_bar_shows_occupancy_without_ansi_or_hiding_overflow(self):
        from types import SimpleNamespace
        from fruitfly_agent.interactive.contracts.models import InteractiveStatus

        status = InteractiveStatus(model='current', working_directory='', session_path='',
                                   message_count=0, tool_names=(), mechanisms=(), context_window=1000,
                                   estimate_model='current')
        for tokens, expected in (
            (0, '[--------------------] 0.0%'),
            (102, '[##------------------] 10.2%'),
            (500, '[##########----------] 50.0%'),
            (1000, '[####################] 100.0%'),
            (1200, '[####################] 120.0%'),
        ):
            with self.subTest(tokens=tokens):
                context = SimpleNamespace(status=replace(status, estimated_input_tokens=tokens))
                text = CommandRouter().execute(InteractiveCommand('status'), context).text
                self.assertIn(f'context usage: {expected} (estimated; last request)\n', text)
                self.assertNotIn('\x1b', text)

    def test_unknown_context_has_no_empty_bar_and_uses_matching_receipt(self):
        from types import SimpleNamespace
        from fruitfly_agent.interactive.contracts.models import InteractiveStatus

        status = InteractiveStatus(model='current', working_directory='', session_path='',
                                   message_count=0, tool_names=(), mechanisms=(), context_window=1000,
                                   estimated_input_tokens=900, estimate_model='other')
        unknown = CommandRouter().execute(InteractiveCommand('status'), SimpleNamespace(status=status)).text
        self.assertIn('context usage: unknown\n', unknown)
        self.assertNotIn('[', unknown)
        receipt = replace(status, last_input_tokens=500, receipt_model='current')
        reported = CommandRouter().execute(InteractiveCommand('status'), SimpleNamespace(status=receipt)).text
        self.assertIn('context usage: [##########----------] 50.0% (reported; last request)\n', reported)

    async def test_no_reduction_does_not_report_zero_as_estimate(self):
        provider = FauxProvider()
        self.receipt(provider, 10)
        session = InteractiveSession(AgentLoopConfig(provider=provider), context_pipeline=ContextPipeline())
        await session.submit('no estimator')
        self.assertIsNone(session.status.estimated_input_tokens)
        self.assertEqual('', session.status.estimate_source)

    async def test_retry_metadata_reaches_frontend_and_persistence_without_claiming_busy(self):
        def provider(view, *, signal=None):
            async def final():
                yield StreamActivity('provider_retrying', 1, 2, 0.25, 'RetryableError', 503)
                yield StreamActivity('provider_timeout', 2, 2, error_kind='first_progress_timeout')
                yield StreamDone(AssistantMessage(content=[TextBlock('answer')], stop_reason='stop'))
            return AssistantMessageEventStream(final())
        events = []
        with tempfile.TemporaryDirectory() as directory, Session(Path(directory) / 'session.jsonl') as durable:
            session = InteractiveSession(AgentLoopConfig(provider=provider, session=durable), event_sink=events.append)
            await session.submit('retry')
            retry = next(e for e in events if isinstance(e, RunActivityChanged) and e.phase == 'provider_retrying')
            self.assertEqual((1, 2, 0.25, 503), (retry.attempt, retry.max_attempts, retry.delay_seconds, retry.status_code))
            records = [e.payload['data'] for e in durable.read_all() if e.payload.get('event') == 'provider_activity']
            self.assertEqual(['provider_retrying', 'provider_timeout'], [e['phase'] for e in records])
            self.assertNotIn('messages', records[0])
            self.assertNotIn('busy', repr(events))
