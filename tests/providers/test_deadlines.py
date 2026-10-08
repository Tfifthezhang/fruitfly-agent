"""Quiet transports, keepalive, retries, receipts, and cancellation stay offline."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.core.errors import RetryableError
from fruitfly_agent.core.model_stream import StreamActivity, TextDelta, ThinkingDelta
from fruitfly_agent.providers.openai import OpenAIProvider
from fruitfly_agent.providers.anthropic import AnthropicProvider
from tests.support.provider_streams import SDKStream, adapter, view


def delta(kind, text='answer', thinking=False):
    if kind == 'openai':
        return NS(type='response.reasoning_summary_text.delta' if thinking else 'response.output_text.delta', delta=text)
    return NS(type='content_block_delta', delta=NS(type='thinking_delta' if thinking else 'text_delta',
                                                  text=text, thinking=text))


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_signal_interrupts_headers_and_quiet_chunks_and_closes_acquired_stream(self):
        for kind in ('openai', 'anthropic'):
            for headers in (False, True):
                with self.subTest(kind=kind, headers=headers):
                    entered = asyncio.Event()
                    class Waiting(SDKStream):
                        async def __aenter__(self):
                            if headers:
                                entered.set()
                                await asyncio.Event().wait()
                            return self
                        async def __anext__(self):
                            entered.set()
                            await asyncio.Event().wait()
                    sdk = Waiting()
                    provider, request = adapter(kind, [sdk])
                    if kind == 'openai' and headers:
                        async def wait_headers(**kwargs):
                            entered.set()
                            await asyncio.Event().wait()
                        request.side_effect = wait_headers
                    signal = asyncio.Event()
                    task = asyncio.create_task(provider(view(), signal=signal).result())
                    await asyncio.wait_for(entered.wait(), 1)
                    signal.set()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 1)
                    if not headers:
                        self.assertTrue(sdk.exited)
                    self.assertEqual(1, request.call_count)

    async def test_keepalive_cannot_extend_first_progress_deadline(self):
        class Ping(SDKStream):
            async def __anext__(self):
                await asyncio.sleep(0.002)
                return NS(type='ping')
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                sdk = Ping()
                provider, request = adapter(kind, [sdk], first_progress_timeout=0.03, retry_max=0)
                events = []
                stream = provider(view())
                async for event in stream:
                    events.append(event)
                with self.assertRaises(RetryableError) as error:
                    await asyncio.wait_for(stream.result(), 1)
                self.assertEqual('first_progress_timeout', error.exception.details['timeout_kind'])
                self.assertEqual('provider_timeout', events[-1].phase)
                self.assertTrue(sdk.exited)
                self.assertEqual(1, request.call_count)

    async def test_stalled_partial_output_fails_without_retry(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                class Partial(SDKStream):
                    async def __anext__(self):
                        if not getattr(self, 'sent', False):
                            self.sent = True
                            return delta(kind)
                        await asyncio.Event().wait()
                sdk = Partial()
                provider, request = adapter(kind, [sdk], stall_timeout=0.03)
                with self.assertRaises(RetryableError) as error:
                    await asyncio.wait_for(provider(view()).result(), 1)
                self.assertEqual('stall_timeout', error.exception.details['timeout_kind'])
                self.assertEqual(1, request.call_count)
                self.assertTrue(sdk.exited)

    async def test_text_and_reasoning_delivery_prevent_retry_on_connection_failure(self):
        for kind in ('openai', 'anthropic'):
            for thinking in (False, True):
                with self.subTest(kind=kind, thinking=thinking):
                    sdk = SDKStream([delta(kind, thinking=thinking), ConnectionError('connection reset')])
                    provider, request = adapter(kind, [sdk])
                    with self.assertRaises(RetryableError):
                        await provider(view()).result()
                    self.assertEqual(1, request.call_count)
                    self.assertTrue(sdk.exited)

    async def test_reasoning_deltas_reset_progress_without_text(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                class Reasoning(SDKStream):
                    async def __anext__(self):
                        await asyncio.sleep(0.015)
                        return await super().__anext__()
                sdk = Reasoning([delta(kind, thinking=True) for _ in range(5)],
                                NS(content=[], stop_reason='end_turn', usage=None))
                provider, request = adapter(kind, [sdk], first_progress_timeout=0.06, stall_timeout=0.06)
                stream = provider(view())
                events = [event async for event in stream]
                await stream.result()
                self.assertEqual(5, sum(isinstance(e, ThinkingDelta) for e in events))
                self.assertEqual(1, request.call_count)
                self.assertTrue(sdk.exited)

    async def test_total_deadline_includes_retry_backoff(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                sdk = SDKStream([ConnectionError('connection reset')])
                provider, request = adapter(kind, [sdk], total_timeout=0.03)
                provider.retry_base_delay = 10
                stream = provider(view())
                events = [event async for event in stream]
                with self.assertRaises(RetryableError) as error:
                    await stream.result()
                self.assertEqual('total_timeout', error.exception.details['timeout_kind'])
                self.assertTrue(any(isinstance(e, StreamActivity) and e.phase == 'provider_retrying' for e in events))
                self.assertEqual(1, request.call_count)

    async def test_retry_after_is_respected_and_reported(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                failure = ConnectionError('service unavailable')
                failure.status_code = 503
                failure.response = NS(headers={'retry-after': '0.25'})
                success = SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))
                provider, request = adapter(kind, [SDKStream([failure]), success], retry_jitter=0)
                delays = []
                async def sleep(delay, signal):
                    delays.append(delay)
                provider._sleep = sleep
                stream = provider(view())
                events = [e async for e in stream]
                await stream.result()
                retry = next(e for e in events if isinstance(e, StreamActivity) and e.phase == 'provider_retrying')
                self.assertEqual([0.25], delays)
                self.assertEqual((1, 4, 0.25, 503), (retry.attempt, retry.max_attempts, retry.delay_seconds, retry.status_code))
                self.assertEqual(2, request.call_count)

    async def test_cleanup_deadline_is_terminal_and_not_retried(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                class SlowClose(SDKStream):
                    async def close(self):
                        await asyncio.Event().wait()
                    async def __aexit__(self, *args):
                        await self.close()
                provider, request = adapter(kind, [SlowClose([], NS(content=[], stop_reason='end_turn', usage=None))], cleanup_timeout=0.03)
                with self.assertRaises(RetryableError) as error:
                    await asyncio.wait_for(provider(view()).result(), 1)
                self.assertEqual('cleanup_timeout', error.exception.details['timeout_kind'])
                self.assertEqual(1, request.call_count)

    async def test_closing_suspended_public_stream_releases_transport(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                sdk = SDKStream([delta(kind)])
                provider, _ = adapter(kind, [sdk])
                stream = provider(view())
                self.assertIsInstance(await anext(stream), StreamActivity)
                self.assertIsInstance(await anext(stream), TextDelta)
                await stream.aclose()
                self.assertTrue(sdk.exited)

    async def test_missing_usage_is_unknown_and_owned_client_closes(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                provider, _ = adapter(kind, [SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))])
                self.assertIsNone((await provider(view()).result()).usage)
                provider._client.close = AsyncMock()
                await provider.close()
                provider._client.close.assert_awaited_once()

    def test_parameters_validate_before_client_construction(self):
        for cls, constructor in ((OpenAIProvider, 'openai.AsyncOpenAI'), (AnthropicProvider, 'anthropic.AsyncAnthropic')):
            for options in ({'first_progress_timeout': 0}, {'stall_timeout': float('inf')},
                            {'total_timeout': True}, {'timeout': None}, {'retry_max': -1},
                            {'retry_base_delay': float('nan')}):
                with self.subTest(cls=cls, options=options), patch(constructor) as client:
                    with self.assertRaises(ValueError):
                        cls(api_key='offline-placeholder', model='offline', **options)
                    client.assert_not_called()
