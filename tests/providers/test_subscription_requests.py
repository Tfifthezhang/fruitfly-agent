"""Real protocol adapters with renewable auth, fake streams and safe budgets."""
from dataclasses import replace
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch
from fruitfly_agent.providers.registry import default_registry
from fruitfly_agent.providers.specs import ModelSpec
from fruitfly_agent.core.data_model import ProviderView, UserMessage, ToolResultMessage, TextBlock
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.lab.context_manager.measurement.budget import MeasurementService
from tests.support.connections import account_record, connection_service
from tests.support.provider_streams import SDKStream
from tests.support.loop import make_tool

class SubscriptionRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_go_reasoning_details_survive_tool_followup(self):
        from fruitfly_agent.providers.chat_completions import ChatCompletionsProvider
        first = SDKStream([
            NS(choices=[NS(index=0, finish_reason=None, delta=NS(
                reasoning='Plan.', reasoning_details=[{'type': 'reasoning.text', 'text': 'Plan.', 'index': 0}]))]),
            NS(choices=[NS(index=0, finish_reason='tool_calls', delta=NS(tool_calls=[NS(
                index=0, id='call-a', function=NS(name='echo', arguments='{}'))]))]),
        ])
        final = SDKStream([NS(choices=[NS(index=0, finish_reason='stop', delta=NS(content='done'))])])
        client = NS(base_url='https://opencode.ai/inference/go/v1', close=AsyncMock(),
            chat=NS(completions=NS(create=AsyncMock(side_effect=[first, final]))))
        with patch('openai.AsyncOpenAI', return_value=client):
            provider = ChatCompletionsProvider(api_key='offline', model='fixture',
                service='opencode-go', base_url=client.base_url)
        view = ProviderView('instructions', [UserMessage('hi')], [make_tool('echo')[0]], 'fixture')
        try:
            message = await provider(view).result()
            from fruitfly_agent.core.data_model import AssistantMessage
            message = AssistantMessage.from_dict(message.to_dict())
            self.assertEqual([block.thinking for block in message.content if hasattr(block, 'thinking')], ['Plan.'])
            result = await provider(replace(view, messages=[*view.messages, message,
                ToolResultMessage('call-a', [TextBlock('ok')])])).result()
            self.assertEqual(result.text, 'done')
            sent = client.chat.completions.create.call_args.kwargs['messages'][2]
            self.assertEqual(sent['reasoning'], 'Plan.')
            self.assertEqual(sent['reasoning_details'], [{'type': 'reasoning.text', 'text': 'Plan.', 'index': 0}])
        finally:
            await provider.close()

    def test_reasoning_dialects_and_invalid_structures(self):
        from fruitfly_agent.providers.chat_codec import ChatReasoning
        reasoning = ChatReasoning()
        empty = ChatReasoning()
        self.assertEqual(empty.consume({'reasoning_details': [
            {'type': 'reasoning.text', 'text': '', 'index': 0}]}), '')
        self.assertEqual(empty.consume({'reasoning': 'Visible'}), 'Visible')
        self.assertEqual(reasoning.consume({'reasoning_details': [
            {'type': 'summary', 'summary': 'First ', 'index': 0}]}), 'First ')
        self.assertEqual(reasoning.consume({'reasoning_details': [
            {'type': 'summary', 'summary': 'second', 'index': 0},
            {'type': 'encrypted', 'encrypted': 'opaque', 'index': 1}]}), 'second')
        self.assertEqual(reasoning.replay(), {'reasoning_details': [
            {'type': 'summary', 'summary': 'First second'}, {'type': 'encrypted', 'encrypted': 'opaque'}]})
        for delta in ({'reasoning': {}}, {'reasoning_details': {}},
                      {'reasoning_details': [{'type': 'unknown'}]}):
            with self.subTest(delta=delta), self.assertRaises(FatalError) as failure:
                ChatReasoning().consume(delta)
            self.assertEqual(failure.exception.details['diagnostics']['failure_category'], 'response_schema')

    async def test_chatgpt_renewal_preserves_tool_continuation_and_reserves_server_maximum(self):
        with tempfile.TemporaryDirectory() as directory:
            service = connection_service(directory)
            service.credentials().modify('account-a', lambda _: account_record())
            spec = ModelSpec.from_dict('work', {'sdk': 'openai', 'protocol': 'responses', 'service': 'chatgpt',
                'base_url': 'https://api.openai.com/v1', 'model': 'offline-model', 'context_window': 8192,
                'max_output_tokens': 2048, 'access': {'integration': 'chatgpt', 'account': 'account-a'}})
            calls = [{'type': 'function_call', 'call_id': 'call-a', 'name': 'echo', 'namespace': 'fruitfly', 'arguments': '{}'}]
            response = NS(output=calls, usage=None, incomplete_details=None)
            final = NS(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'done'}]}], usage=None, incomplete_details=None)
            client = NS(base_url='https://api.openai.com/v1', close=AsyncMock(), responses=NS(create=AsyncMock(side_effect=[
                SDKStream([NS(type='response.completed', response=response)]), SDKStream([NS(type='response.completed', response=final)])])))
            registry = default_registry()
            registry.credential_store = service.credentials()
            with patch('openai.AsyncOpenAI', return_value=client):
                provider = registry.create(replace(spec, max_output_tokens=32))
            view = ProviderView('instructions', [UserMessage('hello')], [make_tool('echo')[0]], 'offline-model', 32)
            measurement = await MeasurementService().measure(view, provider)
            self.assertEqual(measurement.output_reserve, 2048)
            self.assertFalse(provider.input_count_supported)
            first = await provider(view).result()
            identity = first.provider_state['identity']
            service.credentials().modify('account-a', lambda record: {**record, 'access_token': 'offline-token-b'})
            next_view = replace(view, messages=[*view.messages, first, ToolResultMessage('call-a', [TextBlock('ok')])])
            result = await provider(next_view).result()
            self.assertEqual(result.text, 'done')
            self.assertEqual(result.provider_state['identity'], identity)
            payload = client.responses.create.call_args.kwargs
            self.assertNotIn('max_output_tokens', payload)
            self.assertNotIn('parallel_tool_calls', payload)
            self.assertFalse(payload['store'])
            self.assertTrue(payload['stream'])
            self.assertEqual(payload['tools'][0]['type'], 'namespace')
            self.assertEqual(client.api_key, 'offline-token-b')
            service.credentials().modify('account-a', lambda record: {**record, 'status': 'signed_out'})
            with self.assertRaises(FatalError):
                await provider(view).result()
            self.assertEqual(client.responses.create.call_count, 2)
            await provider.close()

    async def test_go_attribution_and_billing_are_independent_of_token_usage(self):
        from fruitfly_agent.providers.connections.methods.opencode_go.requests import GoRequests
        policy = GoRequests()
        payload = policy.prepare({'model': 'fixture', 'extra_headers': {'feature': 'value'}}, 'session-a')
        self.assertEqual(payload['extra_headers']['x-opencode-session'], 'session-a')
        self.assertEqual(payload['extra_headers']['User-Agent'], 'fruitfly-agent/0.1')
        receipt = policy.receipt({'prompt_tokens': 1200, 'cost': 0, 'opencode': {'billing_source': 'go',
            'allowance': .12, 'secret': 'must-not-persist'}})
        self.assertEqual(receipt, {'billing_source': 'go', 'charged_usd': 0, 'allowance_usd': .12})
        self.assertEqual(policy.receipt(None), {})

    async def test_go_environment_reference_uses_subscription_route_without_keyring(self):
        from fruitfly_agent.providers.registry import credential_available

        spec = ModelSpec.from_dict('work', {'sdk': 'openai', 'protocol': 'chat-completions',
            'service': 'opencode-go', 'base_url': 'https://opencode.ai/inference/go/v1',
            'model': 'offline-model', 'context_window': 8192,
            'access': {'integration': 'opencode-go', 'credential': {'env': 'GO_TEST_KEY'}}})
        self.assertFalse(credential_available(spec, {}))
        environment = {'GO_TEST_KEY': 'offline-go-token'}
        self.assertTrue(credential_available(spec, environment))
        stream = SDKStream([NS(choices=[NS(index=0, finish_reason='stop',
            delta=NS(content='done'))], usage=None)])
        client = NS(base_url=spec.provider.base_url, close=AsyncMock(), chat=NS(completions=NS(create=AsyncMock(return_value=stream))))
        with patch('fruitfly_agent.providers.auth.stores.configured_store') as store, patch(
            'openai.AsyncOpenAI', return_value=client
        ):
            directory = self.enterContext(tempfile.TemporaryDirectory())
            registry = default_registry()
            registry.binding_directory = Path(directory) / 'bindings'
            provider = registry.create(spec, environment)
            try:
                result = await provider(ProviderView('instructions', [UserMessage('hi')], [], spec.model)).result()
                self.assertEqual(result.text, 'done')
                self.assertEqual(client.api_key, 'offline-go-token')
                self.assertIn('x-opencode-session', client.chat.completions.create.call_args.kwargs['extra_headers'])
                self.assertNotIn('offline-go-token', str(spec.to_dict()))
                store.assert_not_called()
            finally:
                await provider.close()

    def test_quota_errors_are_not_context_overflow(self):
        from fruitfly_agent.providers.error_classification import classify_provider_error
        error = RuntimeError('too many tokens')
        error.body = {'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}
        classified = classify_provider_error(error, status_code=429)
        self.assertIsInstance(classified, FatalError)
        self.assertEqual(classified.details['kind'], 'subscription_exhausted')


    async def test_sdk_subscription_failure_keeps_category_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            service = connection_service(directory)
            service.credentials().modify('account-a', lambda _: account_record())
            spec = ModelSpec.from_dict('work', {'sdk': 'openai', 'protocol': 'responses', 'service': 'chatgpt',
                'base_url': 'https://api.openai.com/v1', 'model': 'offline-model', 'context_window': 8192,
                'max_output_tokens': 2048, 'access': {'integration': 'chatgpt', 'account': 'account-a'}})
            error = RuntimeError('too many tokens')
            error.body = {'error': {'code': 'subscription_sharing_usage_limit_exceeded'}}
            error.status_code = 429
            client = NS(base_url='https://api.openai.com/v1', close=AsyncMock(),
                responses=NS(create=AsyncMock(side_effect=error)))
            from fruitfly_agent.run.runtime.usage import ModelUsage, ObservedProviderRegistry
            registry = default_registry()
            registry.credential_store = service.credentials()
            observed = ObservedProviderRegistry(registry, ModelUsage())
            with patch('openai.AsyncOpenAI', return_value=client):
                provider = observed.create(spec)
            with self.assertRaises(FatalError) as failure:
                await provider(ProviderView('instructions', [UserMessage('hello')], [], 'offline-model')).result()
            self.assertEqual(failure.exception.details['kind'], 'subscription_exhausted')
            self.assertEqual(client.responses.create.call_count, 1)
            await provider.aclose()
            client.close.assert_awaited_once()
