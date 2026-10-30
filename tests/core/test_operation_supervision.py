"""Timeout and cancellation require confirmed retirement before subsequent work."""
import asyncio
import unittest

from fruitfly_agent.core.extensions.operations import OperationSupervisor, OperationCleanupError
from fruitfly_agent.core.extensions.hooks import HookRegistry, BEFORE_REQUEST, BeforeRequestEvent


class OperationSupervisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_retires_a_cooperative_operation(self):
        retired = asyncio.Event()
        async def wait():
            try:
                await asyncio.Event().wait()
            finally:
                retired.set()
        supervisor = OperationSupervisor(retirement_timeout=.03)
        with self.assertRaises(TimeoutError):
            await supervisor.run(wait, timeout=.01)
        self.assertTrue(retired.is_set())
        self.assertEqual(await supervisor.run(lambda: 7, timeout=.1), 7)

    async def test_unconfirmed_retirement_poisoned_supervisor_never_runs_next_operation(self):
        release, entered = asyncio.Event(), asyncio.Event()
        async def resist():
            entered.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
        supervisor = OperationSupervisor(retirement_timeout=.01)
        try:
            with self.assertRaises(OperationCleanupError):
                await supervisor.run(resist, timeout=.01)
            calls = []
            with self.assertRaises(OperationCleanupError):
                await supervisor.run(lambda: calls.append(True), timeout=.1)
            self.assertEqual(calls, [])
        finally:
            release.set()
            await asyncio.sleep(0)

    async def test_required_hook_failure_blocks_following_handlers(self):
        hooks, calls = HookRegistry(), []
        def fail(event):
            raise OSError('guard unavailable')
        hooks.add(BEFORE_REQUEST, fail, required=True)
        hooks.add(BEFORE_REQUEST, lambda event: calls.append(True))
        with self.assertRaisesRegex(RuntimeError, 'required hook'):
            await hooks.run(BEFORE_REQUEST, BeforeRequestEvent('', [], [], 'fake', 1))
        self.assertEqual(calls, [])
