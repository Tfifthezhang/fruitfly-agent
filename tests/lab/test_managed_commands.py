"""Long command polling is bounded and runtime ownership retires active work."""
import asyncio
import unittest
from types import SimpleNamespace
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.core.env import ExecResult
from fruitfly_agent.core.errors import Result
from fruitfly_agent.lab.tools.bash import create_bash_tool
from fruitfly_agent.lab.tools.commands import CommandManager


class ManagedCommandsTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_poll_and_cancel_retire_backend_and_enforce_capacity(self):
        entered, closed = asyncio.Event(), asyncio.Event()
        async def execute(command, options):
            entered.set()
            try:
                await options.on_stdout('x' * 30000)
                await asyncio.Event().wait()
            finally: closed.set()
        environment = SimpleNamespace(cwd='.', exec=execute)
        manager = CommandManager(max_active=1, output_characters=100)
        tool = create_bash_tool(manager=manager, default_timeout_seconds=5)
        def context(args): return ToolCallContext('call', 'bash', args, env=environment)
        try:
            result = await tool.execute(context({'action': 'start', 'command': 'work', 'wait_seconds': 0}))
            handle = result.details['handle']
            await entered.wait()
            result = await tool.execute(context({'action': 'poll', 'handle': handle, 'wait_seconds': 0}))
            self.assertEqual(result.details['status'], 'running')
            self.assertLess(len(result.content[0].text), 200)
            with self.assertRaisesRegex(ValueError, 'active command'):
                await tool.execute(context({'action': 'start', 'command': 'second'}))
            result = await tool.execute(context({'action': 'cancel', 'handle': handle}))
            self.assertEqual(result.details['status'], 'cancelled')
            self.assertTrue(closed.is_set())
        finally: await manager.aclose()

    async def test_close_cancels_commands_and_synchronous_omission_uses_default(self):
        seen = []
        async def execute(command, options):
            seen.append(options.timeout_seconds)
            return Result.success(ExecResult('done', '', 0))
        environment = SimpleNamespace(cwd='.', exec=execute)
        tool = create_bash_tool(default_timeout_seconds=7)
        await tool.execute(ToolCallContext('call', 'bash', {'command': 'work'}, env=environment))
        self.assertEqual(seen, [7])
        for value in (None, True, float('inf'), 0):
            with self.subTest(value=value), self.assertRaises((ValueError, RuntimeError)):
                await tool.execute(ToolCallContext('call', 'bash', {'command': 'work', 'timeout': value}, env=environment))

    async def test_task_cancellation_retires_a_command_after_start_returned(self):
        entered, closed = asyncio.Event(), asyncio.Event()
        async def execute(command, options):
            entered.set()
            try: await asyncio.Event().wait()
            finally: closed.set()
        manager = CommandManager()
        signal = asyncio.Event()
        environment = SimpleNamespace(cwd='.', exec=execute)
        tool = create_bash_tool(manager=manager)
        context = ToolCallContext('call', 'bash', {'action': 'start', 'command': 'work', 'wait_seconds': 0},
            env=environment, signal=signal)
        try:
            result = await tool.execute(context)
            await entered.wait()
            signal.set()
            await asyncio.wait_for(closed.wait(), timeout=1)
            result = await manager.poll(result.details['handle'])
            self.assertEqual(result.details['status'], 'cancelled')
        finally: await manager.aclose()
