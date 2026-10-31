"""Protocol-independent media projections and Chat tool observation regression."""
import copy
from dataclasses import replace
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_agent.core.data_model import UserMessage, AssistantMessage, ToolCallBlock, ToolResultMessage, TextBlock, ImageBlock
from fruitfly_agent.providers.chat_codec import convert_to_chat
from fruitfly_agent.providers.openai_codec import convert_to_openai
from fruitfly_agent.providers.anthropic_codec import convert_to_anthropic
from fruitfly_agent.providers.chat_completions import ChatCompletionsProvider
from fruitfly_agent.providers.media import project_images
from tests.support.provider_streams import SDKStream, view
from tests.support.media import image


class MediaCodecTests(unittest.TestCase):
    def history(self):
        return [UserMessage('inspect'), AssistantMessage([ToolCallBlock('a', 'capture', {}), ToolCallBlock('b', 'read', {})]),
                ToolResultMessage('a', [TextBlock('before'), image(), TextBlock('after'), image()]),
                ToolResultMessage('b', [TextBlock('other result')])]

    def test_chat_keeps_all_tool_results_before_attributed_images(self):
        history = self.history()
        original = copy.deepcopy(history)
        wire = convert_to_chat(history)
        self.assertEqual([m['role'] for m in wire], ['user', 'assistant', 'tool', 'tool', 'user'])
        self.assertEqual([m['tool_call_id'] for m in wire[2:4]], ['a', 'b'])
        blocks = wire[-1]['content']
        self.assertIn('call a', blocks[0]['text'])
        self.assertEqual([b['type'] for b in blocks], ['text', 'text', 'image_url', 'text', 'image_url'])
        self.assertEqual(blocks[3]['text'], 'after')
        self.assertTrue(blocks[2]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(wire, convert_to_chat(history))
        self.assertEqual(original, history)

    def test_native_protocols_keep_the_image_in_the_original_tool_result(self):
        history = self.history()
        response = convert_to_openai(history)
        self.assertEqual(response[-2]['output'][1]['type'], 'input_image')
        messages = convert_to_anthropic(history)
        self.assertEqual(messages[-1]['content'][0]['content'][1]['type'], 'image')

    def test_nonvision_projection_keeps_history_and_explicitly_reports_unavailable_images(self):
        history = [UserMessage([TextBlock('original'), image()]), *self.history()[1:]]
        before = copy.deepcopy(history)
        projected = project_images(history, False)
        for encode in (convert_to_chat, convert_to_openai, convert_to_anthropic):
            wire = str(encode(projected))
            self.assertIn('cannot view images', wire)
            self.assertNotIn(image().data, wire)
        self.assertEqual(history, before)
        self.assertEqual(project_images(history, True), before)

    def test_invalid_tool_images_are_explicit_observations_instead_of_poisoning_future_requests(self):
        bad = ImageBlock('invalid-base64!', 'image/png')
        history = [UserMessage('inspect'), AssistantMessage([ToolCallBlock('a', 'capture', {})]),
                   ToolResultMessage('a', [TextBlock('capture completed'), bad])]
        projected = project_images(history, True)
        for encode in (convert_to_chat, convert_to_openai, convert_to_anthropic):
            wire = str(encode(projected))
            self.assertIn('was not supplied', wire)
            self.assertIn('capture completed', wire)
            self.assertNotIn(bad.data, wire)
        self.assertEqual(history[-1].content[-1], bad)


class ChatMediaStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_result_followup_preserves_reasoning_and_survives_later_user_turns(self):
        tool_stream = SDKStream([NS(choices=[NS(index=0, finish_reason='tool_calls', delta=NS(
            reasoning_content='Inspect rendered output.', tool_calls=[NS(index=0, id='a',
                function=NS(name='capture', arguments='{}'))]))])])
        def answer():
            return SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='visible'))])])
        create = AsyncMock(side_effect=[tool_stream, answer(), answer()])
        with patch('openai.AsyncOpenAI', return_value=NS(chat=NS(completions=NS(create=create)))):
            provider = ChatCompletionsProvider(api_key='offline-placeholder', model='chosen-model', vision=True)
        current = view()
        assistant = await provider(current).result()
        restored = AssistantMessage.from_dict(assistant.to_dict())
        history = [*current.messages, restored, ToolResultMessage('a', [TextBlock('screenshot'), image()])]
        self.assertEqual((await provider(replace(current, messages=history)).result()).text, 'visible')
        wire = create.call_args.kwargs['messages']
        self.assertEqual(wire[2]['reasoning_content'], 'Inspect rendered output.')
        self.assertEqual(wire[3]['role'], 'tool')
        self.assertEqual(wire[4]['content'][-1]['type'], 'image_url')
        self.assertEqual((await provider(replace(current, messages=[*history, UserMessage('why?')])).result()).text, 'visible')
        self.assertEqual(len([m for m in create.call_args.kwargs['messages'] if isinstance(m.get('content'), list)]), 1)

    async def test_declared_nonvision_provider_rejects_fresh_input_but_can_continue_old_images(self):
        stream = SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='text only'))])])
        create = AsyncMock(return_value=stream)
        with patch('openai.AsyncOpenAI', return_value=NS(chat=NS(completions=NS(create=create)))):
            provider = ChatCompletionsProvider(api_key='offline-placeholder', model='chosen-model', vision=False)
        with self.assertRaisesRegex(ValueError, 'vision model'):
            provider.validate_input([image()])
        result = await provider(replace(view(), messages=[UserMessage([image()])])).result()
        self.assertEqual(result.text, 'text only')
        self.assertIn('cannot view images', str(create.call_args.kwargs['messages']))

    async def test_heuristic_measurement_includes_chat_observation_text_and_preserves_wrapper_ports(self):
        from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
        from fruitfly_agent.run.runtime.usage import ObservedProvider, ModelUsage
        history = [UserMessage('inspect'), AssistantMessage([ToolCallBlock('a', 'capture', {})]),
                   ToolResultMessage('a', [TextBlock('long observation ' * 100), image()])]
        with patch('openai.AsyncOpenAI', return_value=NS()):
            provider = ChatCompletionsProvider(api_key='offline-placeholder', model='chosen-model', vision=True)
        wrapped = ObservedProvider(provider, ModelUsage())
        meter = MeasurementService()
        current = replace(view(), messages=history)
        baseline = meter.estimate(current)
        result = await meter.measure(current, wrapped)
        self.assertGreater(result.input_tokens, baseline)
        self.assertEqual(result.quality, 'heuristic')
        self.assertIn('image-estimate', result.uncertain)
        self.assertEqual(wrapped.usage.used, 0)
