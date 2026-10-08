"""Exercise real adapters through their public stream using offline SDK doubles."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.core.data_model import ProviderView, UserMessage, ToolCallBlock, TextBlock
from fruitfly_agent.core.errors import FatalError, OverflowError, RetryableError
from fruitfly_agent.core.model_stream import StreamActivity, TextDelta, ThinkingDelta, ToolCallStart, ToolCallDelta
from fruitfly_agent.providers.openai import OpenAIProvider
from fruitfly_agent.providers.anthropic import AnthropicProvider
from tests.support.loop import make_tool


from tests.support.provider_streams import SDKStream, adapter, view


class ProviderStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_output_limit_is_capped_and_zero_uses_provider_default(self):
        for kind, parameter in (('openai', 'max_output_tokens'), ('anthropic', 'max_tokens')):
            for requested, expected in ((32, 32), (8192, 4096), (0, 4096)):
                with self.subTest(kind=kind, requested=requested):
                    sdk = SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))
                    provider, request = adapter(kind, [sdk])
                    await provider(replace(view(), max_tokens=requested)).result()
                    self.assertEqual(expected, request.call_args.kwargs[parameter])

    async def test_sdk_retry_is_disabled_and_pre_cancelled_requests_do_not_start(self):
        for kind, constructor, cls in (
            ('openai', 'openai.AsyncOpenAI', OpenAIProvider),
            ('anthropic', 'anthropic.AsyncAnthropic', AnthropicProvider),
        ):
            with self.subTest(kind=kind), patch(constructor) as sdk:
                cls(api_key='offline-placeholder', model='offline')
                self.assertEqual(0, sdk.call_args.kwargs['max_retries'])
            provider, request = adapter(kind, [])
            signal = asyncio.Event()
            signal.set()
            with self.assertRaises(asyncio.CancelledError):
                await provider(view(), signal=signal).result()
            self.assertEqual(0, request.call_count)

    async def test_cancellation_during_retry_delay_does_not_start_another_request(self):
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                signal = asyncio.Event()
                provider, request = adapter(kind, [SDKStream([ConnectionError('connection reset')])])
                async def cancel_during_sleep(delay, event):
                    event.set()
                provider._sleep = cancel_during_sleep
                with self.assertRaises(asyncio.CancelledError):
                    await provider(view(), signal=signal).result()
                self.assertEqual(1, request.call_count)

    async def test_openai_text_tool_deltas_usage_and_request(self):
        sdk = SDKStream([
            NS(type='response.output_text.delta', delta='hello'),
            NS(type='response.output_item.added', item=NS(type='function_call', id='item-1', call_id='call-1', name='count', arguments='')),
            NS(type='response.function_call_arguments.delta', item_id='item-1', delta='{"value":'),
            NS(type='response.function_call_arguments.delta', item_id='item-1', delta='"x"}'),
            NS(type='response.function_call_arguments.done', item_id='item-1', arguments='{"value":"wrong"}', name='count'),
            NS(type='response.completed', response=NS(usage=NS(input_tokens=12, output_tokens=4, input_tokens_details=NS(cached_tokens=5)))),
        ])
        provider, request = adapter('openai', [sdk])
        tool, _ = make_tool()
        stream = provider(view((tool,)))
        events = [event async for event in stream]
        final = await stream.result()
        self.assertEqual('hello', final.text)
        self.assertTrue(sdk.exited)
        self.assertEqual(ToolCallBlock(id='call-1', name='count', input={'value': 'x'}), final.content[1])
        self.assertEqual('toolUse', final.stop_reason)
        self.assertEqual((12, 4, 5), (final.usage.input_tokens, final.usage.output_tokens, final.usage.cache_read_tokens))
        self.assertEqual([StreamActivity, TextDelta, ToolCallStart, ToolCallDelta, ToolCallDelta], [type(e) for e in events])
        self.assertEqual('chosen-model', request.call_args.kwargs['model'])
        self.assertEqual('instructions', request.call_args.kwargs['instructions'])
        self.assertEqual('count', request.call_args.kwargs['tools'][0]['name'])

    async def test_openai_done_arguments_and_incomplete_response(self):
        for arguments, expected in (('{"value":"x"}', {'value': 'x'}), ('invalid json', {})):
            with self.subTest(arguments=arguments):
                provider, _ = adapter('openai', [SDKStream([
                    NS(type='response.function_call_arguments.done', item_id='item', call_id='call', name='count', arguments=arguments),
                ])])
                final = await provider(view()).result()
                self.assertEqual(expected, final.content[0].input)
        provider, request = adapter('openai', [SDKStream([
            NS(type='response.incomplete', response=NS(incomplete_details=NS(reason='max_output_tokens'))),
        ])])
        self.assertEqual('length', (await provider(view()).result()).stop_reason)
        self.assertNotIn('tools', request.call_args.kwargs)

    async def test_anthropic_text_thinking_full_tool_input_usage_and_context_exit(self):
        final = NS(content=[NS(type='text', text='hello'), NS(type='thinking', thinking='reason'),
                            NS(type='tool_use', id='call', name='count', input='{"value":"x"}')],
                   stop_reason='tool_use', usage=NS(input_tokens=10, output_tokens=3,
                                                   cache_read_input_tokens=4, cache_creation_input_tokens=2))
        sdk = SDKStream([
            NS(type='content_block_delta', delta=NS(type='text_delta', text='hello')),
            NS(type='content_block_delta', delta=NS(type='thinking_delta', thinking='reason')),
            NS(type='content_block_start', content_block=NS(type='tool_use', id='call', name='count', input={'value': 'x'})),
            NS(type='content_block_delta', delta=NS(type='input_json_delta', partial_json='{"value":"x"}')),
            NS(type='content_block_stop'), NS(type='unknown'),
        ], final)
        provider, request = adapter('anthropic', [sdk])
        tool, _ = make_tool()
        stream = provider(view((tool,)))
        events = [event async for event in stream]
        result = await stream.result()
        self.assertTrue(sdk.exited)
        self.assertEqual([StreamActivity, TextDelta, ThinkingDelta, ToolCallStart, ToolCallDelta], [type(e) for e in events])
        self.assertEqual({'value': 'x'}, events[3].input)
        self.assertEqual('toolUse', result.stop_reason)
        self.assertEqual({'value': 'x'}, result.content[-1].input)
        self.assertEqual((10, 3, 4, 2), (result.usage.input_tokens, result.usage.output_tokens,
                                      result.usage.cache_read_tokens, result.usage.cache_creation_tokens))
        self.assertEqual('chosen-model', request.call_args.kwargs['model'])
        self.assertEqual('count', request.call_args.kwargs['tools'][0]['name'])

    async def test_anthropic_malformed_input_and_stop_reason_normalization(self):
        for reason, stop in (('max_tokens', 'length'), ('end_turn', 'stop'), ('refusal', 'stop'), ('custom', 'stop')):
            with self.subTest(reason=reason):
                sdk = SDKStream([], NS(content=[NS(type='tool_use', id='id', name='tool', input='invalid')], stop_reason=reason, usage=None))
                provider, request = adapter('anthropic', [sdk])
                final = await provider(view()).result()
                self.assertEqual({}, final.content[0].input)
                self.assertEqual(stop, final.stop_reason)
                self.assertNotIn('tools', request.call_args.kwargs)
                self.assertTrue(sdk.exited)

    async def test_retryable_failure_retries_and_exhaustion_is_structured(self):
        for kind in ('openai', 'anthropic'):
            for succeeds in (True, False):
                with self.subTest(kind=kind, succeeds=succeeds):
                    success = SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))
                    provider, request = adapter(kind, [SDKStream([ConnectionError('connection reset')]), success if succeeds else SDKStream([ConnectionError('connection reset')])], retry_max=1)
                    if succeeds:
                        self.assertEqual('stop', (await provider(view()).result()).stop_reason)
                    else:
                        with self.assertRaises(RetryableError):
                            await provider(view()).result()
                    self.assertEqual(2, request.call_count)

    async def test_fatal_and_overflow_failures_are_not_retried(self):
        for kind in ('openai', 'anthropic'):
            for error, expected in ((RuntimeError('rejected'), FatalError), (RuntimeError('prompt too long'), OverflowError)):
                with self.subTest(kind=kind, error=expected.__name__):
                    sdk = SDKStream([error])
                    provider, request = adapter(kind, [sdk], retry_max=3)
                    with self.assertRaises(expected):
                        await provider(view()).result()
                    self.assertEqual(1, request.call_count)
                    self.assertTrue(sdk.exited)

    async def test_task_cancellation_propagates_and_anthropic_context_exits(self):
        class Waiting(SDKStream):
            async def __anext__(self):
                started.set()
                await asyncio.Event().wait()
        for kind in ('openai', 'anthropic'):
            with self.subTest(kind=kind):
                started = asyncio.Event()
                sdk = Waiting()
                provider, request = adapter(kind, [sdk])
                task = asyncio.create_task(provider(view()).result())
                await asyncio.wait_for(started.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(1, request.call_count)
                self.assertTrue(sdk.exited)

    async def test_openai_signal_and_failed_event(self):
        signal = asyncio.Event()
        signal.set()
        provider, _ = adapter('openai', [SDKStream([NS(type='response.output_text.delta', delta='ignored')])])
        with self.assertRaises(asyncio.CancelledError):
            await provider(view(), signal=signal).result()
        provider, _ = adapter('openai', [SDKStream([NS(type='response.failed', error='rejected')])])
        with self.assertRaises(FatalError):
            await provider(view()).result()
