"""Real SDK against a deterministic local stdio peer."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from tests.support.mcp import HAS_MCP, write_mcp_config
from fruitfly_agent.lab.mcp.config import load_config
from fruitfly_agent.lab.mcp.client import McpClient


@unittest.skipUnless(HAS_MCP, "install the optional [mcp] extra")
class McpClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    async def client(self, *, mode='normal', tools=('echo',), **options):
        config = load_config(write_mcp_config(self.root, tools=tools, mode=mode, **options), self.root)[0]
        client = McpClient(config, {})
        self.addAsyncCleanup(client.close)
        await client.start()
        return client

    async def test_discovery_pagination_call_and_idempotent_lifecycle(self):
        client = await self.client(mode='pages')
        self.assertEqual(6, len(client.descriptors))
        await client.start()
        result = await client.call('echo', {'value': None})
        self.assertIsNone(result['structuredContent']['value'])
        await client.close()
        await client.close()
        self.assertEqual('closed', client.status().state)

    async def test_repeated_cursor_and_startup_timeout_fail_closed(self):
        for mode in ('loop', 'hang'):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(RuntimeError, 'startup'):
                    await self.client(mode=mode, startup_timeout=.15)

    async def test_cancel_and_timeout_do_not_retry(self):
        client = await self.client(call_timeout=.15)
        with self.assertRaisesRegex(RuntimeError, 'Do not automatically replay'):
            await client.call('wait', {'value': 'waiting', 'delay': 60})
        client = await self.client()
        pending = asyncio.create_task(client.call('wait', {'value': 'waiting', 'delay': 60}))
        await asyncio.sleep(.03)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending

    async def test_cancelling_startup_closes_a_hung_peer_before_startup_deadline(self):
        config = load_config(write_mcp_config(self.root, mode='hang', startup_timeout=30), self.root)[0]
        client = McpClient(config, {})
        self.addAsyncCleanup(client.close)
        pending = asyncio.create_task(client.start())
        await asyncio.sleep(.03)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 5)
        self.assertNotEqual('starting', client.status().state)

    async def test_changed_catalog_requires_application(self):
        client = await self.client(tools=('change',))
        await client.call('change', {'value': 'change'})
        await asyncio.sleep(.02)
        self.assertIn('catalog changed', client.status().state)
        with self.assertRaisesRegex(RuntimeError, 'catalog changed'):
            await client.call('echo', {'value': 'again'})

    async def test_legacy_protocol_and_structured_content_are_supported(self):
        client = await self.client(mode='legacy')
        self.assertEqual('2025-11-25', client.protocol)
        self.assertEqual('fixture', client.server_info['name'])
        result = await client.call('echo', {'value': None})
        self.assertIsNone(result['structuredContent']['value'])

    async def test_disconnect_fails_without_implicit_restart(self):
        client = await self.client(mode='disconnect')
        with self.assertRaisesRegex(RuntimeError, 'Do not automatically replay'):
            await client.call('echo', {'value': 'disconnect'})
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            await client.call('echo', {'value': 'again'})
        with self.assertRaisesRegex(RuntimeError, 'restarted implicitly'):
            await client.start()

    async def test_signal_cancels_waiting_call_without_consuming_slot(self):
        client = await self.client()
        first = asyncio.create_task(client.call('wait', {'value': 'hold', 'delay': 60}))
        await asyncio.sleep(.03)
        signal = asyncio.Event()
        waiting = asyncio.create_task(client.call('echo', {'value': 'queued'}, signal))
        await asyncio.sleep(.02)
        signal.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(waiting, 1)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        result = await client.call('echo', {'value': 'slot released'})
        self.assertEqual('slot released', result['structuredContent']['value'])
