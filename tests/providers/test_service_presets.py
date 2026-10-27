"""Official service presets use offline SDK streams and the shared catalog contract."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolResultMessage
from fruitfly_agent.providers.model_setup import SERVICES, model_entry
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_agent.providers.chat_completions import ChatCompletionsProvider
from tests.support.loop import make_tool
from tests.support.provider_streams import SDKStream, view


EXAMPLE = Path(__file__).resolve().parents[2] / 'examples/configuration/additional-models.example.yaml'


class ServicePresetTests(unittest.IsolatedAsyncioTestCase):
    def test_templates_match_explicit_wizard_defaults(self):
        specs = load_model_specs(EXAMPLE)
        self.assertEqual(set(specs), {'Qwen3.8-Flash', 'GLM-4.5-Air'})
        for choice in (item for item in SERVICES if item.id in {'qwen', 'bigmodel'}):
            values = {name: str(value).lower() if type(value) is bool else str(value)
                      for name, value in choice.initial.items()}
            label, entry = model_entry(choice.id, values)
            with self.subTest(choice=choice.id):
                spec = specs[label]
                self.assertEqual(ModelSpec.from_dict(label, entry), spec)
                self.assertEqual(ModelSpec.from_dict(label, spec.to_dict()), spec)
                with patch('openai.AsyncOpenAI') as sdk:
                    provider = default_registry().create(spec, {spec.provider.api_key_env: 'offline-placeholder'})
                self.assertEqual(provider.transport_parameters, {**spec.transport, 'transport_version': 'bounded-v1'})
                self.assertEqual(provider.request_options, spec.parameters)
                self.assertEqual(sdk.call_args.kwargs['base_url'], spec.provider.base_url)
                with patch('openai.AsyncOpenAI'):
                    defaults = ChatCompletionsProvider(api_key='offline-placeholder', model=spec.model,
                        service=spec.service, **spec.parameters)
                self.assertEqual(defaults.transport_parameters, provider.transport_parameters)

    def test_invalid_service_parameters_fail_before_sdk_construction(self):
        specs = load_model_specs(EXAMPLE)
        cases = {
            'Qwen3.8-Flash': [
                {'extra_body': {'enable_thinking': 'true'}},
                {'extra_body': {'preserve_thinking': 1}},
                {'extra_body': {'thinking_budget': True}},
                {'extra_body': {'thinking_budget': -1}},
                {'extra_body': {'reasoning_effort': 'unsupported'}},
                {'extra_body': {'reasoning_effort': 'medium', 'thinking_budget': 1000}},
                {'reasoning_effort': 'medium'},
                {'tool_choice': {'type': 'function', 'function': {'name': 'count'}}},
            ],
            'GLM-4.5-Air': [
                {'reasoning_effort': 'high'},
                {'extra_body': {'reasoning_effort': 'high'}},
                {'extra_body': {'thinking': {'type': 'adaptive'}}},
                {'extra_body': {'thinking': {'type': 'enabled', 'budget_tokens': 2048}}},
                {'extra_body': {'tool_stream': True}},
                {'temperature': 1.1}, {'top_p': 0}, {'tool_choice': 'required'},
                {'response_format': {'type': 'json_schema', 'json_schema': {
                    'name': 'example', 'schema': {'type': 'object'}}}},
            ],
        }
        with patch('openai.AsyncOpenAI') as sdk:
            for label, options in cases.items():
                for parameters in options:
                    with self.subTest(label=label, parameters=parameters), self.assertRaises(ValueError):
                        replace(specs[label], parameters=parameters)
        sdk.assert_not_called()

    async def test_presets_stream_thinking_tools_and_replay_without_unsupported_controls(self):
        for label, spec in load_model_specs(EXAMPLE).items():
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
            with self.subTest(label=label):
                result = await provider(current).result()
                self.assertEqual(result.content[0].thinking, 'Plan.')
                self.assertEqual(result.usage.total_tokens, 20)
                request = create.call_args.kwargs
                self.assertEqual(request['max_tokens'], current.max_tokens)
                self.assertEqual(request['extra_body'], spec.parameters['extra_body'])
                if spec.service == 'bigmodel':
                    self.assertNotIn('stream_options', request)
                    self.assertNotIn('parallel_tool_calls', request)
                else:
                    self.assertEqual(request['stream_options'], {'include_usage': True})
                    self.assertTrue(request['parallel_tool_calls'])
                restored = AssistantMessage.from_dict(result.to_dict())
                answer = await provider(replace(current, messages=[*current.messages, restored,
                    ToolResultMessage('call', [TextBlock('result')])])).result()
                self.assertEqual(answer.text, 'Done.')
                self.assertEqual(create.call_args.kwargs['messages'][2]['reasoning_content'], 'Plan.')
                self.assertTrue(first.exited)
                self.assertTrue(second.exited)

    def test_service_protocol_selection_is_explicit_and_generic_remains_extensible(self):
        spec = load_model_specs(EXAMPLE)['GLM-4.5-Air']
        with self.assertRaises(ValueError):
            replace(spec, provider=replace(spec.provider, protocol='responses'))
        # A custom gateway with the same model name still owns its extension semantics.
        replace(spec, service='generic', parameters={'reasoning_effort': 'high'})
