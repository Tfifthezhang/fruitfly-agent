"""One-shot summary rejection, retry suppression and cancellation boundaries."""
import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.context_manager.reduction import LayeredCompactionConfig, LayeredCompactionReducer
from fruitfly_agent.lab.context_manager.reduction.methods.layered_compaction.summary import HistorySummarizer
from tests.support.compaction import mounted_history, source_messages, snapshot, structured_summary
from tests.support.faux_provider import FauxProvider


class LayeredSummaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.history, registry = mounted_history()
        self.addCleanup(registry.close)

    def reducer(self, provider, **settings):
        config = LayeredCompactionConfig(mode='hybrid', summary_model_profile='summary',
            keep_recent_groups=1, tail_tokens=256, **settings)
        summary = HistorySummarizer(provider, model='summary', context_window=100000,
            output_limit=4096)
        return LayeredCompactionReducer(config, history=self.history, summarizer=summary)

    async def test_structured_summary_is_used_once_and_exposes_progress(self):
        provider = FauxProvider(); provider.respond_text(structured_summary())
        method = self.reducer(provider)
        events = []
        async def observe(event): events.append(event)
        decision = await method.check_budget(snapshot(source_messages(), report_activity=observe))
        self.assertEqual(len(provider.calls),1)
        self.assertIn('Verified facts retained.', '\n'.join(getattr(m,'text','') for m in decision.messages))
        self.assertTrue(any(e.stage=='summarizing_history' and e.outcome=='succeeded' for e in events))
        self.assertTrue(all(call['model']=='summary' for call in provider.calls))

    async def test_invalid_summary_falls_back_without_changing_original_history(self):
        for text, reason in (('', 'stop'), ('partial memory','length'), ('missing headings','stop'),
                             (structured_summary('x'*1000), 'stop')):
            with self.subTest(reason=reason,text_length=len(text)):
                provider = FauxProvider(); provider.respond_text(text,stop_reason=reason)
                method = self.reducer(provider)
                source = snapshot(source_messages())
                original = [m.to_dict() for m in source.messages]
                decision = await method.check_budget(source)
                self.assertIsNotNone(decision.messages)
                self.assertEqual(len(provider.calls),1)
                self.assertEqual(decision.state['attempt']['outcome'],'failed')
                self.assertEqual(original,[m.to_dict() for m in source.messages])

    async def test_failed_summary_does_not_repeat_when_even_protected_input_cannot_fit(self):
        provider=FauxProvider();provider.respond_text('partial',stop_reason='length')
        method=self.reducer(provider)
        messages=source_messages(); messages[0]=UserMessage('Required constraint: '+'keep '*1800)
        source=snapshot(messages,context_window=1500)
        first=await method.check_budget(source)
        self.assertIsNone(first.messages)
        self.assertEqual(first.state['attempt']['outcome'],'failed')
        second=await method.check_budget(replace(source,context_state={method.mechanism_id:first.state},revision=1))
        self.assertIsNone(second)
        self.assertEqual(len(provider.calls),1)

    async def test_summary_timeout_retires_stream_and_returns_deterministic_projection(self):
        entered,closed=asyncio.Event(),asyncio.Event()
        def provider(view,*,signal=None):
            async def events():
                entered.set()
                try:
                    await asyncio.Event().wait()
                    yield StreamDone(None)
                finally:closed.set()
            return AssistantMessageEventStream(events())
        method=self.reducer(provider,summary_timeout_seconds=1.)
        decision=await asyncio.wait_for(method.check_budget(snapshot(source_messages())),2.)
        self.assertTrue(entered.is_set());self.assertTrue(closed.is_set())
        self.assertIsNotNone(decision.messages)
        self.assertEqual(decision.state['attempt']['outcome'],'failed')

    async def test_cancellation_never_becomes_fallback_or_another_request(self):
        entered,closed=asyncio.Event(),asyncio.Event();signal=asyncio.Event()
        def provider(view,*,signal=None):
            async def events():
                entered.set()
                try:
                    await asyncio.Event().wait()
                    yield StreamDone(None)
                finally:closed.set()
            return AssistantMessageEventStream(events())
        method=self.reducer(provider)
        task=asyncio.create_task(method.check_budget(snapshot(source_messages(),signal=signal)))
        await asyncio.wait_for(entered.wait(),1.)
        signal.set()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(closed.is_set());self.assertEqual(self.history.values,{})

    async def test_already_cancelled_snapshot_does_no_auxiliary_work(self):
        signal=asyncio.Event();signal.set();provider=FauxProvider()
        with self.assertRaises(asyncio.CancelledError):
            await self.reducer(provider).check_budget(snapshot(source_messages(),signal=signal))
        self.assertEqual(provider.calls,[])

    async def test_provider_failure_falls_back_but_outer_allowance_errors_propagate(self):
        from fruitfly_agent.core.errors import FatalError
        for kind in ('service_unavailable', 'model_budget_exhausted', 'unconfirmed_cancellation'):
            with self.subTest(kind=kind):
                provider = FauxProvider(); provider.respond_fatal('offline failure', kind=kind)
                method = self.reducer(provider)
                if kind == 'service_unavailable':
                    decision = await method.check_budget(snapshot(source_messages()))
                    self.assertIsNotNone(decision.messages)
                    self.assertEqual(decision.state['attempt']['outcome'], 'failed')
                else:
                    with self.assertRaises(FatalError): await method.check_budget(snapshot(source_messages()))
                self.assertEqual(len(provider.calls), 1)

    async def test_summary_input_ledger_marks_omissions_and_cooldown_needs_new_evidence(self):
        from fruitfly_agent.lab.context_manager.reduction.methods.layered_compaction.state import may_summarize
        import json
        provider = FauxProvider(); provider.respond_text(structured_summary())
        method = self.reducer(provider, summary_input_max_tokens=2048)
        source = snapshot(source_messages())
        decision = await method.check_budget(source)
        self.assertEqual(len(provider.calls), 1)
        ledgers = [json.loads(data) for data in self.history.values.values() if data.startswith(b'{')]
        self.assertTrue(any(row['kind'] == 'reference' for row in ledgers[-1]['summary_input']))
        previous = decision.state
        count = previous['source_count']
        fingerprint = previous['attempt']['fingerprint']
        self.assertFalse(may_summarize(previous, method.policy, fingerprint, count + 8))
        self.assertFalse(may_summarize(previous, method.policy, 'new', count + 7))
        self.assertTrue(may_summarize(previous, method.policy, 'new', count + 8))
