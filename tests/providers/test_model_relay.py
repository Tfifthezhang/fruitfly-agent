"""Exercise grant isolation and upstream authorization without real model calls."""
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import httpx

from fruitfly_agent.providers.gateway import ModelRelay, RelayGrant, RelayRejected


class ModelRelayTests(IsolatedAsyncioTestCase):
    async def test_revocation_cancels_only_the_granted_active_stream(self):
        import asyncio
        entered = asyncio.Event()
        auth = AsyncMock()
        auth.token.return_value = 'offline'
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b'ok'))) as client:
            relay = ModelRelay(client)
            grant = relay.issue(RelayGrant('fixture', 'https://fixture.invalid/v1',
                '/responses', auth, time.monotonic() + 30))
            async def active():
                async with relay.stream(grant, '/responses', b'{"model":"fixture","stream":true}'):
                    entered.set()
                    await asyncio.Event().wait()
            task = asyncio.create_task(active())
            try:
                await asyncio.wait_for(entered.wait(), 2)
                relay.revoke(grant)
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_relay_rejects_other_models_and_revocation_and_preserves_stream(self):
        requests = []

        def upstream(request):
            requests.append(request)
            return httpx.Response(200, content=b'data: fixture\n\n',
                                  headers={'content-type': 'text/event-stream'})

        authorization = AsyncMock()
        authorization.token.return_value = 'fixture-upstream-token'
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            relay = ModelRelay(client)
            token = relay.issue(RelayGrant('fixture-model', 'https://fixture.invalid/v1',
                                          '/responses', authorization, time.monotonic() + 30))
            valid = b'{"model":"fixture-model","stream":true}'
            for route, body in (('/models', valid), ('/responses', b'{"model":"other","stream":true}')):
                with self.assertRaises(RelayRejected):
                    async with relay.stream(token, route, body):
                        self.fail('Out-of-scope request reached upstream')
            authorization.token.assert_not_called()
            async with relay.stream(token, '/responses', valid) as response:
                self.assertEqual(await response.aread(), b'data: fixture\n\n')
            self.assertEqual(requests[0].url, 'https://fixture.invalid/v1/responses')
            self.assertEqual(requests[0].headers['authorization'], 'Bearer fixture-upstream-token')
            relay.revoke(token)
            with self.assertRaises(RelayRejected):
                async with relay.stream(token, '/responses', valid):
                    self.fail('Revoked request reached upstream')
            self.assertEqual(len(requests), 1)

    async def test_protocol_adapters_accept_relay_client_without_changing_endpoint_identity(self):
        from unittest.mock import patch
        from fruitfly_agent.providers.openai import OpenAIProvider
        from fruitfly_agent.providers.chat_completions import ChatCompletionsProvider

        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200))) as client:
            for adapter in (OpenAIProvider, ChatCompletionsProvider):
                with self.subTest(adapter=adapter.__name__), patch('openai.AsyncOpenAI') as sdk:
                    provider = adapter(api_key='fixture-placeholder', model='fixture-model',
                        base_url='https://fixture.invalid/v1', http_client=client)
                    self.assertIs(sdk.call_args.kwargs['http_client'], client)
                    self.assertEqual(sdk.call_args.kwargs['base_url'], 'https://fixture.invalid/v1')
                    self.assertNotIn('http_client', provider.request_options)

    async def test_network_relay_requires_tls_and_verified_server_identity(self):
        import ssl
        from pathlib import Path
        from fruitfly_agent.providers.gateway import RelaySocket, RelayTransport
        with self.assertRaisesRegex(ValueError, 'requires TLS'):
            RelaySocket(Path('/unused/model.sock'), None, listen=('127.0.0.1', 0))
        contexts = (None, ssl._create_unverified_context())
        for context in contexts:
            with self.subTest(verified=context is not None):
                with self.assertRaisesRegex(ValueError, 'verified HTTPS'):
                    RelayTransport(Path('/unused/model.sock'), upstream_url='https://fixture.invalid/v1',
                        route='/responses', grant='fixture', network_url='https://localhost:1234', tls=context)

    async def test_registry_injects_task_authorization_and_transport_without_reading_host_accounts(self):
        from unittest.mock import patch
        from fruitfly_agent.providers.registry import default_registry
        from fruitfly_agent.providers.specs import ModelSpec
        spec = ModelSpec.from_dict('work', {'sdk': 'openai', 'protocol': 'responses',
            'service': 'chatgpt', 'base_url': 'https://api.openai.com/v1',
            'model': 'fixture', 'context_window': 8192,
            'access': {'integration': 'chatgpt', 'account': 'fixture-account'}})
        authorization = AsyncMock()
        authorization.integration = 'chatgpt'
        authorization.account = 'fixture-account'
        authorization.identity = 'stable-binding'
        authorization.label = 'Fixture account'
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200))) as client:
            registry = default_registry(http_client_factory=lambda selected: client,
                authorization_factory=lambda selected: authorization)
            with patch('fruitfly_agent.providers.auth.stores.configured_store') as store, patch('openai.AsyncOpenAI') as sdk:
                sdk.return_value.base_url = 'https://api.openai.com/v1'
                connected = registry.create(spec, {})
                self.assertIs(connected.auth, authorization)
                self.assertIs(sdk.call_args.kwargs['http_client'], client)
                store.assert_not_called()
