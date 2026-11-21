"""Opt-in local Unix socket integration with a fake upstream."""
from pathlib import Path
import tempfile
import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

import httpx

from fruitfly_agent.providers.gateway import ModelRelay, RelayGrant, RelaySocket, RelayTransport


class ModelRelaySocketTests(IsolatedAsyncioTestCase):
    async def test_private_socket_streams_and_rejects_missing_grant(self):
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(200, content=b'data: fixture\n\n',
                                  headers={'content-type': 'text/event-stream', 'set-cookie': 'private'})

        auth = AsyncMock()
        auth.token.return_value = 'fixture-upstream-token'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'model.sock'
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as upstream:
                relay = ModelRelay(upstream)
                token = relay.issue(RelayGrant('fixture', 'https://fixture.invalid/v1',
                                               '/responses', auth, time.monotonic() + 30))
                async with RelaySocket(path, relay):
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                    async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=str(path)),
                                                 base_url='http://localhost') as client:
                        payload = {'model': 'fixture', 'stream': True}
                        denied = await client.post('/responses', json=payload)
                        self.assertEqual(denied.status_code, 403)
                        self.assertEqual(seen, [])
                    async with httpx.AsyncClient(transport=RelayTransport(path,
                            upstream_url='https://fixture.invalid/v1', route='/responses', grant=token)) as routed:
                        async with routed.stream('POST', 'https://fixture.invalid/v1/responses', json=payload) as response:
                            self.assertEqual(await response.aread(), b'data: fixture\n\n')
                            self.assertNotIn('set-cookie', response.headers)
                self.assertFalse(path.exists())
            self.assertEqual(len(seen), 1)

