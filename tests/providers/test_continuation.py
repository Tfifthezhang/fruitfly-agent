"""Exact response replay survives tools, serialization and a new Provider instance."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.core.data_model import (AssistantMessage, UserMessage, ToolResultMessage,
    TextBlock, ImageBlock, Usage)
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.core.session import Session
from fruitfly_agent.providers.openai import OpenAIProvider
from fruitfly_agent.providers.chat_completions import ChatCompletionsProvider
from fruitfly_agent.providers.anthropic import AnthropicProvider
from tests.support.provider_streams import SDKStream, view, adapter
from tests.support.loop import make_tool


class ContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_continues_commentary_and_counts_reasoning_without_double_counting(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.loop import run_agent_loop
        from tests.support.faux_provider import FauxProvider
        provider = FauxProvider()
        provider.respond(AssistantMessage(content=[TextBlock('working')], stop_reason='stop',
            usage=Usage(input_tokens=5, output_tokens=8, reasoning_tokens=3), continue_turn=True))
        provider.respond(AssistantMessage(content=[TextBlock('answer')], stop_reason='stop',
            usage=Usage(input_tokens=10, output_tokens=4, reasoning_tokens=1)))
        result = await run_agent_loop(AgentLoopConfig(provider=provider), [UserMessage('task')])
        self.assertFalse(result.is_error)
        self.assertEqual(result.messages[-1].text, 'answer')
        self.assertEqual(result.usage.reasoning_tokens, 4)
        self.assertEqual(result.usage.total_tokens, 27)

    async def test_core_bounds_nonfinal_responses_and_unknown_reasoning_stays_unknown(self):
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.loop import run_agent_loop
        from tests.support.faux_provider import FauxProvider
        provider = FauxProvider()
        for _ in range(2):
            provider.respond(AssistantMessage(content=[TextBlock('working')], stop_reason='stop',
                usage=Usage(input_tokens=1, output_tokens=2), continue_turn=True))
        result = await run_agent_loop(AgentLoopConfig(provider=provider, max_turns=2), [UserMessage('task')])
        self.assertTrue(result.is_error)
        self.assertEqual(result.error_details['kind'], 'continuation_limit')
        self.assertIsNone(result.usage.reasoning_tokens)

    async def response(self, output, *, service='generic'):
        sdk = SDKStream([NS(type='response.completed', response=NS(output=output,
            usage=NS(input_tokens=10, output_tokens=8, output_tokens_details=NS(reasoning_tokens=5))))])
        provider, request = adapter('openai', [sdk], service=service)
        tool, _ = make_tool()
        current = view((tool,))
        return await provider(current).result(), current, request

    async def test_responses_preserves_order_encryption_phase_and_thinking_across_session_restore(self):
        original = [
            {'type': 'reasoning', 'id': 'r1', 'encrypted_content': 'opaque-state', 'summary': []},
            {'type': 'message', 'id': 'm1', 'role': 'assistant', 'phase': 'commentary',
             'content': [{'type': 'output_text', 'text': 'Checking.'}]},
            {'type': 'function_call', 'id': 'f1', 'call_id': 'call-1', 'name': 'count', 'arguments': '{"value":"x"}'},
        ]
        message, current, _ = await self.response(original)
        self.assertEqual(message.usage.reasoning_tokens, 5)
        self.assertEqual(message.usage.total_tokens, 18)
        self.assertEqual(message.tool_calls[0].id, 'call-1')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.jsonl'
            with Session(path) as session:
                for item in [*current.messages, message, ToolResultMessage('call-1', [TextBlock('result')])]:
                    session.append('message', {'message': item.to_dict()})
            with Session(path) as session:
                restored = session.messages()
            provider, request = adapter('openai', [SDKStream([])])
            await provider(replace(current, messages=restored)).result()
        self.assertEqual(request.call_args.kwargs['input'][1:4], original)
        self.assertEqual(request.call_args.kwargs['input'][4]['type'], 'function_call_output')
        self.assertNotIn('offline-placeholder', str(message.to_dict()))

    async def test_deepseek_replays_plain_reasoning_and_retains_protocol_controls(self):
        items = [{'type': 'reasoning', 'content': [{'type': 'reasoning_text', 'text': 'Plan.'}]},
                 {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Done.'}]}]
        message, _, request = await self.response(items, service='deepseek')
        self.assertFalse(request.call_args.kwargs['store'])
        self.assertTrue(request.call_args.kwargs['parallel_tool_calls'])
        self.assertEqual(message.content[0].thinking, 'Plan.')
        self.assertEqual(message.provider_state['items'], items)

    async def test_signed_messages_keep_empty_thinking_signature_and_redacted_blocks(self):
        raw = [NS(type='thinking', thinking='', signature='signed-state'),
               NS(type='redacted_thinking', data='encrypted-state'),
               NS(type='tool_use', id='call', name='count', input={'value': 'x'})]
        provider, request = adapter('anthropic', [SDKStream([], NS(content=raw, stop_reason='tool_use', usage=None)),
                                                SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))])
        tool, _ = make_tool()
        current = view((tool,))
        message = await provider(current).result()
        restored = AssistantMessage.from_dict(message.to_dict())
        await provider(replace(current, messages=[*current.messages, restored,
            ToolResultMessage('call', [TextBlock('result')])])).result()
        wire = request.call_args.kwargs['messages'][1]['content']
        self.assertEqual(wire[0]['signature'], 'signed-state')
        self.assertEqual(wire[0]['thinking'], '')
        self.assertEqual(wire[1], {'type': 'redacted_thinking', 'data': 'encrypted-state'})

    async def test_context_changes_block_signed_active_tool_continuation_and_new_user_allows_rebuild(self):
        provider, request = adapter('anthropic', [SDKStream([], NS(content=[
            NS(type='thinking', thinking='', signature='signature'),
            NS(type='tool_use', id='call', name='count', input={})], stop_reason='tool_use', usage=None)),
            SDKStream([], NS(content=[], stop_reason='end_turn', usage=None))])
        tool, _ = make_tool()
        current = view((tool,))
        message = await provider(current).result()
        history = [*current.messages, message, ToolResultMessage('call', [TextBlock('result')])]
        for changes in ({'system_prompt': 'changed'}, {'tools': []},
                        {'messages': [UserMessage('edited prefix'), *history[1:]]}):
            changed = replace(replace(current, messages=history), **changes)
            with self.subTest(changes=list(changes)), self.assertRaises(FatalError):
                await provider(changed).result()
        self.assertEqual(request.call_count, 1)
        await provider(replace(current, system_prompt='changed', messages=[*history, UserMessage('new task')])).result()
        self.assertTrue(all(b['type'] != 'thinking' for b in request.call_args.kwargs['messages'][1]['content']))

    async def test_hook_edit_and_changed_credentials_cannot_reuse_active_state(self):
        message, current, _ = await self.response([
            {'type': 'function_call', 'call_id': 'call', 'name': 'count', 'arguments': '{}'}])
        edited = replace(message, content=[TextBlock('edited'), *message.content])
        for candidate, key in ((edited, 'offline-placeholder'), (message, 'changed-placeholder')):
            client = NS(responses=NS(create=AsyncMock()))
            with patch('openai.AsyncOpenAI', return_value=client):
                provider = OpenAIProvider(api_key=key, model='fallback')
            with self.assertRaises(FatalError):
                await provider(replace(current, messages=[*current.messages, candidate,
                    ToolResultMessage('call', [TextBlock('result')])])).result()
            client.responses.create.assert_not_called()

    async def test_responses_truncation_overrides_tools_and_commentary_continues(self):
        message = OpenAIProvider._assemble(NS(incomplete_details=NS(reason='max_output_tokens'), usage=None), [], {},
            output=[{'type': 'function_call', 'call_id': 'call', 'name': 'count', 'arguments': '{}'}])
        self.assertEqual(message.stop_reason, 'length')
        message, _, _ = await self.response([{'type': 'message', 'phase': 'commentary',
            'content': [{'type': 'output_text', 'text': 'Working.'}]}])
        self.assertTrue(message.continue_turn)
        self.assertTrue(AssistantMessage.from_dict(message.to_dict()).continue_turn)

    async def test_final_response_is_authoritative_and_does_not_duplicate_deltas(self):
        sdk = SDKStream([NS(type='response.output_text.delta', delta='hello'),
            NS(type='response.completed', response=NS(output=[{'type': 'message', 'content': [
                {'type': 'output_text', 'text': 'hello'}]}], usage=None))])
        provider, _ = adapter('openai', [sdk])
        self.assertEqual((await provider(view()).result()).text, 'hello')

    async def test_unsupported_response_content_fails_instead_of_returning_an_empty_success(self):
        with self.assertRaisesRegex(FatalError, 'message content'):
            await self.response([{'type': 'message', 'content': [{'type': 'output_audio', 'data': 'opaque'}]}])

    async def test_missing_terminal_response_fails_and_closes_stream(self):
        sdk = SDKStream([NS(type='response.output_text.delta', delta='partial')])
        client = NS(responses=NS(create=AsyncMock(return_value=sdk)))
        with patch('openai.AsyncOpenAI', return_value=client):
            provider = OpenAIProvider(api_key='offline-placeholder', model='model')
        with self.assertRaises(FatalError):
            await provider(view()).result()
        self.assertTrue(sdk.exited)
        self.assertEqual(client.responses.create.call_count, 1)

    async def test_server_tool_activity_is_recorded_separately_and_prevents_automatic_retry(self):
        from fruitfly_agent.core.model_stream import StreamActivity
        from fruitfly_agent.core.errors import RetryableError
        sdk = SDKStream([NS(type='response.output_item.added', item=NS(type='web_search_call', id='server-1')),
                         ConnectionError('connection reset')])
        provider, request = adapter('openai', [sdk])
        stream = provider(view())
        events = [event async for event in stream]
        activity = next(e for e in events if isinstance(e, StreamActivity) and e.tool_name)
        self.assertEqual(activity.tool_name, 'web_search_call')
        self.assertEqual(activity.tool_call_id, 'server-1')
        with self.assertRaises(RetryableError):
            await stream.result()
        self.assertEqual(request.call_count, 1)

    async def test_server_results_do_not_become_local_tool_calls(self):
        message, _, _ = await self.response([{'type': 'web_search_call', 'id': 's1', 'status': 'completed'},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Found.'}]}])
        self.assertEqual(message.tool_calls, [])
        self.assertEqual(message.text, 'Found.')
        self.assertEqual(message.provider_state['items'][0]['type'], 'web_search_call')

    async def test_image_tool_results_are_kept_by_responses_and_messages_codecs(self):
        from fruitfly_agent.providers.openai_codec import convert_to_openai
        from fruitfly_agent.providers.anthropic_codec import convert_to_anthropic
        from fruitfly_agent.core.data_model import ToolCallBlock
        history = [UserMessage('look'), AssistantMessage([ToolCallBlock('call', 'capture', {})]),
            ToolResultMessage('call', [TextBlock('image'), ImageBlock('abc', 'image/png')])]
        self.assertEqual(convert_to_openai(history)[-1]['output'][1]['type'], 'input_image')
        self.assertEqual(convert_to_anthropic(history)[-1]['content'][0]['content'][1]['type'], 'image')


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_deepseek_chat_thinking_parallel_calls_usage_and_exact_followup(self):
        chunks = [NS(choices=[NS(index=0, finish_reason=None, delta=NS(content=None,
            reasoning_content='Plan', tool_calls=[]))]),
            NS(choices=[NS(index=0, finish_reason=None, delta=NS(tool_calls=[
                NS(index=0, id='a', function=NS(name='count', arguments='{"value":')),
                NS(index=1, id='b', function=NS(name='count', arguments='{}'))]))]),
            NS(choices=[NS(index=0, finish_reason='tool_calls', delta=NS(tool_calls=[
                NS(index=0, id=None, function=NS(name=None, arguments='"x"}'))]))]),
            NS(choices=[], usage=NS(prompt_tokens=10, completion_tokens=8,
                completion_tokens_details=NS(reasoning_tokens=5)))]
        sdk = SDKStream(chunks)
        followup = SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='done'))])])
        create = AsyncMock(side_effect=[sdk, followup])
        client = NS(chat=NS(completions=NS(create=create)))
        with patch('openai.AsyncOpenAI', return_value=client):
            provider = ChatCompletionsProvider(api_key='offline-placeholder', model='deepseek-flash',
                service='deepseek', reasoning_effort='high', extra_body={'thinking': {'type': 'enabled'}})
        tool, _ = make_tool()
        current = view((tool,))
        result = await provider(current).result()
        self.assertEqual(result.usage.reasoning_tokens, 5)
        self.assertEqual(result.usage.total_tokens, 18)
        self.assertEqual([c.id for c in result.tool_calls], ['a', 'b'])
        self.assertEqual(result.tool_calls[0].input, {'value': 'x'})
        first = create.call_args.kwargs
        self.assertEqual(first['max_tokens'], 32)
        self.assertEqual(first['extra_body'], {'thinking': {'type': 'enabled'}})
        restored = AssistantMessage.from_dict(result.to_dict())
        answer = await provider(replace(current, messages=[*current.messages, restored,
            ToolResultMessage('a', [TextBlock('one')]), ToolResultMessage('b', [TextBlock('two')])])).result()
        self.assertEqual(answer.text, 'done')
        self.assertEqual(create.call_args.kwargs['messages'][2]['reasoning_content'], 'Plan')
        self.assertTrue(sdk.exited)

    async def test_chat_length_with_tools_and_missing_finish_are_safe(self):
        for finish in ('length', None):
            sdk = SDKStream([NS(choices=[NS(index=0, finish_reason=finish, delta=NS(content='partial'))])])
            client = NS(chat=NS(completions=NS(create=AsyncMock(return_value=sdk))))
            with patch('openai.AsyncOpenAI', return_value=client):
                provider = ChatCompletionsProvider(api_key='offline-placeholder', model='model')
            if finish is None:
                with self.assertRaises(FatalError):
                    await provider(view()).result()
            else:
                self.assertEqual((await provider(view()).result()).stop_reason, 'length')
            self.assertTrue(sdk.exited)
