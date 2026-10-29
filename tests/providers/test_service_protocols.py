"""Four official services share protocol adapters without changing catalog grammar."""
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

import yaml

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolResultMessage, UserMessage
from fruitfly_agent.providers.model_setup import model_entry, setup_initial
from fruitfly_agent.providers.registry import ProviderRegistry, default_registry
from fruitfly_agent.providers.services import service_definition
from fruitfly_agent.providers.specs import ModelSpec
from tests.support.loop import make_tool
from tests.support.media import image
from tests.support.provider_streams import SDKStream, view


MATRIX = {
    'openai': ('responses', 'chat-completions'),
    'anthropic': ('messages', 'chat-completions'),
    'deepseek': ('responses', 'messages', 'chat-completions'),
    'qwen': ('responses', 'messages', 'chat-completions'),
}
ENDPOINTS = {
    'openai': {'responses': 'https://api.openai.com/v1', 'chat-completions': 'https://api.openai.com/v1'},
    'anthropic': {'messages': 'https://api.anthropic.com', 'chat-completions': 'https://api.anthropic.com/v1'},
    'deepseek': {'responses': 'https://api.deepseek.com', 'chat-completions': 'https://api.deepseek.com',
                 'messages': 'https://api.deepseek.com/anthropic'},
    'qwen': {'responses': 'https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1',
             'chat-completions': 'https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1',
             'messages': 'https://maas.qianwenaiapi.com/apps/anthropic'},
}


def spec_for(service, protocol, *, reasoning=True):
    initial = setup_initial(service, protocol)
    values = {key: str(value).lower() if type(value) is bool else str(value) for key, value in initial.items()}
    values.update(profile='fixture', model=initial.get('model', 'fixture-model'), protocol=protocol,
                  context_window='100000', max_output_tokens='4096', **{'capabilities.reasoning': str(reasoning).lower()})
    label, entry = model_entry(service, values)
    return ModelSpec.from_dict(label, entry)


class ServiceProtocolTests(unittest.IsolatedAsyncioTestCase):
    def test_all_ten_combinations_round_trip_and_resolve_the_correct_sdk_endpoint(self):
        for service, protocols in MATRIX.items():
            for protocol in protocols:
                for reasoning in (True, False):
                    with self.subTest(service=service, protocol=protocol, reasoning=reasoning):
                        spec = spec_for(service, protocol, reasoning=reasoning)
                        self.assertEqual(spec.provider.base_url, ENDPOINTS[service][protocol])
                        self.assertEqual(ModelSpec.from_dict(spec.id, yaml.safe_load(yaml.safe_dump(spec.to_dict()))), spec)
                        self.assertEqual(spec.provider.sdk, 'anthropic' if protocol == 'messages' else 'openai')
                        for explicit in (None, spec.provider.base_url, 'https://fixture.invalid/custom'):
                            current = replace(spec, provider=replace(spec.provider, base_url=explicit))
                            with patch('openai.AsyncOpenAI') as openai, patch('anthropic.AsyncAnthropic') as anthropic:
                                provider = default_registry().create(current, {spec.provider.api_key_env: 'offline-placeholder'})
                            sdk = anthropic if protocol == 'messages' else openai
                            self.assertEqual(sdk.call_args.kwargs['base_url'], explicit or ENDPOINTS[service][protocol])
                            self.assertEqual(provider.request_options, spec.parameters)
                            self.assertEqual(provider._replay.prefix_bound, service == 'anthropic' and protocol == 'messages')

    def test_service_support_is_checked_without_model_or_parameter_policies(self):
        for service, protocol in (('openai', 'messages'), ('anthropic', 'responses')):
            with self.subTest(service=service), self.assertRaisesRegex(ValueError, 'does not support protocol'):
                service_definition(service, protocol)
        for service, protocols in MATRIX.items():
            for protocol in protocols:
                options = {'temperature': .2, 'top_p': .5, 'extra_body': {'future_feature': True}}
                with self.subTest(service=service, protocol=protocol):
                    spec = replace(spec_for(service, protocol), model='unlisted-model', parameters=options)
                    with patch('openai.AsyncOpenAI'), patch('anthropic.AsyncAnthropic'):
                        provider = default_registry().create(spec, {spec.provider.api_key_env: 'offline-placeholder'})
                    self.assertEqual(provider.request_options, options)

    def test_sdk_resolution_is_explicit_and_discovery_never_calls_factories(self):
        registry = ProviderRegistry()
        factory = Mock()
        registry.register('one', 'fixture-api', factory)
        self.assertEqual(registry.sdk_for('fixture-api'), 'one')
        registry.register('two', 'fixture-api', factory)
        with self.assertRaisesRegex(ValueError, 'explicit default'):
            registry.sdk_for('fixture-api')
        registry.register('two', 'fixture-api', factory, default=True)
        self.assertEqual(registry.sdk_for('fixture-api'), 'two')
        factory.assert_not_called()

    async def test_every_combination_streams_two_tools_replays_exact_state_and_projects_images(self):
        for service, protocols in MATRIX.items():
            for protocol in protocols:
                with self.subTest(service=service, protocol=protocol):
                    spec = replace(spec_for(service, protocol), capabilities=replace(spec_for(service, protocol).capabilities, vision=True))
                    if protocol == 'messages':
                        original = [NS(type='thinking', thinking='Inspect.', signature='signed' if service == 'anthropic' else ''),
                            NS(type='tool_use', id='a', name='count', input={}),
                            NS(type='tool_use', id='b', name='count', input={})]
                        streams = [SDKStream([], NS(content=original, stop_reason='tool_use', usage=None)),
                                   SDKStream([], NS(content=[NS(type='text', text='done')], stop_reason='end_turn', usage=None))]
                        request = Mock(side_effect=streams)
                        client = NS(messages=NS(stream=request))
                        sdk_path = 'anthropic.AsyncAnthropic'
                    elif protocol == 'responses':
                        original = [NS(type='reasoning', content=[NS(type='reasoning_text', text='Inspect.')]),
                            NS(type='function_call', id='fa', call_id='a', name='count', arguments='{}'),
                            NS(type='function_call', id='fb', call_id='b', name='count', arguments='{}')]
                        def response(items):
                            return SDKStream([NS(type='response.completed', response=NS(output=items, usage=None))])
                        streams = [response(original), response([NS(type='message', content=[NS(type='output_text', text='done')])])]
                        request = AsyncMock(side_effect=streams)
                        client = NS(responses=NS(create=request))
                        sdk_path = 'openai.AsyncOpenAI'
                    else:
                        thought = {} if service == 'anthropic' else {'reasoning_content': 'Inspect.'}
                        streams = [SDKStream([NS(choices=[NS(index=0, finish_reason='tool_calls', delta=NS(**thought,
                            tool_calls=[NS(index=index, id=call, function=NS(name='count', arguments='{}'))
                                        for index, call in enumerate(('a', 'b'))]))])]),
                            SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='done'))])])]
                        request = AsyncMock(side_effect=streams)
                        client = NS(chat=NS(completions=NS(create=request)))
                        sdk_path = 'openai.AsyncOpenAI'
                    with patch(sdk_path, return_value=client):
                        provider = default_registry().create(spec, {spec.provider.api_key_env: 'offline-placeholder'})
                    tool, _ = make_tool()
                    current = replace(view((tool,)), model=spec.model, messages=[UserMessage([TextBlock('inspect'), image()])])
                    first = await provider(current).result()
                    self.assertEqual([call.id for call in first.tool_calls], ['a', 'b'])
                    restored = AssistantMessage.from_dict(first.to_dict())
                    history = [*current.messages, restored, ToolResultMessage('a', [TextBlock('rendered'), image()]),
                               ToolResultMessage('b', [TextBlock('other')])]
                    final = await provider(replace(current, messages=history)).result()
                    self.assertEqual(final.text, 'done')
                    self.assertIsNone(final.usage)
                    payload = request.call_args.kwargs
                    wire = payload['input' if protocol == 'responses' else 'messages']
                    self.assertIn(image().data, str(wire))
                    self.assertIn('rendered', str(wire))
                    self.assertNotIn('cannot view images', str(wire))
                    if protocol == 'chat-completions':
                        self.assertEqual([item['role'] for item in wire[-3:]], ['tool', 'tool', 'user'])
                        if service != 'anthropic':
                            self.assertEqual(wire[2]['reasoning_content'], 'Inspect.')
                    elif protocol == 'messages':
                        self.assertEqual(wire[1]['content'][0]['signature'], 'signed' if service == 'anthropic' else '')
                        self.assertEqual(len(wire[-1]['content']), 2)
                    else:
                        self.assertEqual(wire[1]['type'], 'reasoning')
                        self.assertEqual([item['call_id'] for item in wire[-2:]], ['a', 'b'])
                    self.assertTrue(all(stream.exited for stream in streams))

    async def test_native_anthropic_keeps_signed_prefix_protection_but_chat_is_not_signed(self):
        from fruitfly_agent.providers.replay import ReplayBinding
        native = ReplayBinding('messages', 'anthropic', None, 'offline-placeholder', namespace='anthropic')
        chat = ReplayBinding('chat-completions', 'anthropic', None, 'offline-placeholder', namespace='openai-chat')
        self.assertTrue(native.prefix_bound)
        self.assertFalse(chat.prefix_bound)
