"""Serialized confirmation, exact replies and runtime-scoped approval reset."""
import asyncio
import unittest
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationPrompt
from fruitfly_agent.interactive.authorization import AuthorizationService

class AuthorizationServiceTests(unittest.IsolatedAsyncioTestCase):
    def prompt(self, identity='one', operation='read', targets=('/outside/a.txt',)):
        return AuthorizationPrompt(identity, 'fixture', operation, targets, 'operation', 'session scope')

    async def wait_pending(self, service, identity):
        async with asyncio.timeout(1):
            while service.pending is None or service.pending.request_id != identity:
                await asyncio.sleep(0)

    async def test_once_does_not_grant_next_request_and_stale_reply_is_rejected(self):
        service = AuthorizationService()
        service.available = True
        first = asyncio.create_task(service.confirm(self.prompt()))
        await self.wait_pending(service, 'one')
        self.assertFalse(service.respond('stale', 'once'))
        self.assertTrue(service.respond('one', 'once'))
        self.assertEqual('once', await first)
        second = asyncio.create_task(service.confirm(self.prompt('two')))
        await self.wait_pending(service, 'two')
        self.assertFalse(service.respond('one', 'once'))
        service.respond('two', 'deny')
        self.assertEqual('deny', await second)
        self.assertEqual(0, service.status()['grants'])

    async def test_directory_grant_does_not_authorize_writes_or_sibling_directories(self):
        service = AuthorizationService()
        calls = []
        async def handler(prompt):
            calls.append(prompt)
            return 'session' if len(calls) == 1 else 'deny'
        service.handler = handler
        self.assertEqual('session', await service.confirm(self.prompt()))
        self.assertEqual('session', await service.confirm(self.prompt('next', targets=('/outside/sub/b.txt',))))
        self.assertEqual('deny', await service.confirm(self.prompt('write', 'write')))
        self.assertEqual('deny', await service.confirm(self.prompt('sibling', targets=('/other/a.txt',))))
        service.clear()
        self.assertEqual('deny', await service.confirm(self.prompt('cleared')))
        self.assertEqual(4, len(calls))

    async def test_local_execution_grant_is_cleared_on_close(self):
        service = AuthorizationService()
        async def approve(prompt):
            return 'session'
        service.handler = approve
        await service.confirm(self.prompt(operation='execute'))
        self.assertTrue(service.status()['local_execution'])
        await service.close()
        self.assertEqual(0, service.status()['grants'])
        self.assertEqual('deny', await service.confirm(self.prompt(operation='execute')))

    async def test_confirmations_are_serialized_and_close_denies_pending(self):
        service = AuthorizationService()
        service.available = True
        tasks = [asyncio.create_task(service.confirm(self.prompt(name))) for name in ('one', 'two')]
        await self.wait_pending(service, 'one')
        self.assertFalse(service.respond('two', 'once'))
        service.respond('one', 'once')
        self.assertEqual('once', await tasks[0])
        await self.wait_pending(service, 'two')
        await service.close()
        self.assertEqual('deny', await tasks[1])

    async def test_timeout_noninteractive_and_signal_do_not_approve(self):
        service = AuthorizationService(timeout_seconds=0.01)
        self.assertEqual('deny', await service.confirm(self.prompt()))
        service.available = True
        self.assertEqual('deny', await service.confirm(self.prompt()))
        signal = asyncio.Event()
        task = asyncio.create_task(service.confirm(self.prompt('cancel'), signal))
        await self.wait_pending(service, 'cancel')
        signal.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(service.pending)
