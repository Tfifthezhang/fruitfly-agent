"""Explicit model examples preserve user options through the shared adapters."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolResultMessage
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.providers.specs import ModelSpec
from tests.support.loop import make_tool
from tests.support.provider_streams import SDKStream, view


EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/configuration/additional-models.example.yaml'


class ServiceExampleTests(unittest.IsolatedAsyncioTestCase):
    def test_examples_round_trip_and_construct_without_changing_explicit_options(self):
        specs = load_model_specs(EXAMPLE)
        self.assertEqual(set(specs), {'Qwen3.8-Flash', 'Qwen3.8-Flash-Responses', 'Qwen3.8-Flash-Messages'})
        for label, spec in specs.items():
            with self.subTest(label=label):
                self.assertEqual(ModelSpec.from_dict(label, spec.to_dict()), spec)
                with patch('openai.AsyncOpenAI') as openai, patch('anthropic.AsyncAnthropic') as anthropic:
                    provider = default_registry().create(spec, {spec.provider.api_key_env: 'offline-placeholder'})
                sdk = anthropic if spec.provider.protocol == 'messages' else openai
                self.assertEqual(provider.transport_parameters, {**spec.transport, 'transport_version': 'bounded-v1'})
                self.assertEqual(provider.request_options, spec.parameters)
                self.assertEqual(sdk.call_args.kwargs['base_url'], spec.provider.base_url)

    def test_extensions_are_not_interpreted_as_local_model_policies(self):
        spec = load_model_specs(EXAMPLE)['Qwen3.8-Flash']
        options = {'reasoning_effort': 'high', 'tool_choice': 'required',
                   'extra_body': {'enable_thinking': True, 'future_feature': {'enabled': True}}}
        changed = replace(spec, model='custom-model', parameters=options)
        self.assertEqual(changed.parameters, options)
        # Protocol changes preserve authored options; remote support is the caller's responsibility.
        self.assertEqual(replace(spec, provider=replace(spec.provider, protocol='responses')).parameters, spec.parameters)

    async def test_chat_example_streams_thinking_tools_and_exact_followup(self):
        spec = load_model_specs(EXAMPLE)['Qwen3.8-Flash']
        first = SDKStream([
            NS(choices=[NS(index=0, finish_reason=None, delta=NS(reasoning_content='Plan.'))]),
            NS(choices=[NS(index=0, finish_reason='tool_calls', delta=NS(tool_calls=[
                NS(index=0, id='call', function=NS(name='count', arguments='{}'))]))]),
            NS(choices=[], usage=NS(prompt_tokens=12, completion_tokens=8)),
        ])
        second = SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='Done.'))])])
        create = AsyncMock(side_effect=[first, second])
        client = NS(chat=NS(completions=NS(create=create)))
        with patch('openai.AsyncOpenAI', return_value=client):
            provider = default_registry().create(spec, {spec.provider.api_key_env: 'offline-placeholder'})
        tool, _ = make_tool()
        current = replace(view((tool,)), model=spec.model)
        result = await provider(current).result()
        self.assertEqual(result.content[0].thinking, 'Plan.')
        self.assertEqual(result.usage.total_tokens, 20)
        request = create.call_args.kwargs
        self.assertEqual(request['max_tokens'], current.max_tokens)
        self.assertEqual(request['extra_body'], spec.parameters['extra_body'])
        self.assertEqual(request['stream_options'], {'include_usage': True})
        self.assertTrue(request['parallel_tool_calls'])
        restored = AssistantMessage.from_dict(result.to_dict())
        answer = await provider(replace(current, messages=[*current.messages, restored,
            ToolResultMessage('call', [TextBlock('result')])])).result()
        self.assertEqual(answer.text, 'Done.')
        self.assertEqual(create.call_args.kwargs['messages'][2]['reasoning_content'], 'Plan.')
        self.assertTrue(first.exited)
        self.assertTrue(second.exited)
