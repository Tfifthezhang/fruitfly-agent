"""Count the same encoded input sent by the adapter; fake SDK only."""
from dataclasses import replace
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import unittest

from fruitfly_agent.core.data_model import UserMessage, ImageBlock, ToolResultMessage, TextBlock, Usage
from fruitfly_agent.providers.token_counting import OPENAI_COUNT_FIELDS
from fruitfly_agent.run.runtime.usage import ObservedProvider, ModelUsage
from tests.support.provider_streams import adapter, SDKStream, view
from tests.support.loop import make_tool


class ProviderTokenCountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_responses_count_reuses_final_wire_input_options_and_tool_schema(self):
        provider, request = adapter('openai', [SDKStream()], service='openai',
            reasoning={'effort': 'low'}, text={'format': {'type': 'json_object'}})
        counter = AsyncMock(return_value=NS(input_tokens=321))
        provider._client.responses.input_tokens = NS(count=counter)
        tool, _ = make_tool()
        context = replace(view((tool,)), messages=[UserMessage([TextBlock('task'), ImageBlock('fake', 'image/png')])])
        identity = provider.input_count_identity(context)
        self.assertEqual(321, await provider.count_input(context))
        await provider(context).result()
        wire = request.call_args.kwargs
        self.assertEqual({k: v for k, v in wire.items() if k in OPENAI_COUNT_FIELDS}, counter.call_args.kwargs)
        self.assertNotIn('stream', counter.call_args.kwargs)
        self.assertEqual(32, wire['max_output_tokens'])
        provider.request_options['reasoning']['effort'] = 'high'
        self.assertNotEqual(identity, provider.input_count_identity(context))
        self.assertNotEqual(identity, provider.input_count_identity(replace(context, tools=[])))

    async def test_generic_responses_does_not_guess_counter_and_invalid_counts_fail(self):
        generic, _ = adapter('openai', [])
        self.assertFalse(generic.input_count_supported)
        with self.assertRaises(ValueError): await generic.count_input(view())
        native, _ = adapter('openai', [], service='openai')
        native._client.responses.input_tokens = NS(count=AsyncMock(return_value=NS(input_tokens=-1)))
        with self.assertRaises(ValueError): await native.count_input(view())

    async def test_usage_normalization_does_not_double_count_responses_cache(self):
        responses, _ = adapter('openai', [])
        messages, _ = adapter('anthropic', [])
        usage = Usage(input_tokens=100, cache_read_tokens=50, cache_creation_tokens=20)
        self.assertEqual(100, responses.context_usage_tokens(usage))
        self.assertEqual(170, messages.context_usage_tokens(usage))

    async def test_generation_budget_wrapper_forwards_count_without_charging_generation(self):
        provider, _ = adapter('openai', [SDKStream()], service='openai')
        provider._client.responses.input_tokens = NS(count=AsyncMock(return_value=NS(input_tokens=5)))
        budget = ModelUsage()
        wrapped = ObservedProvider(provider, budget)
        self.assertTrue(wrapped.input_count_supported)
        self.assertEqual(5, await wrapped.count_input(view()))
        self.assertEqual(0, budget.used)
        self.assertEqual(provider.input_count_identity(view()), wrapped.input_count_identity(view()))
        await wrapped(view()).result()
        self.assertEqual(1, budget.used)
