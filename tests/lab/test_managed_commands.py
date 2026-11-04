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
    async def test_default_timeout_reaches_backend_and_managed_capacity_tolerates_four_jobs(self):
        from fruitfly_agent.lab.catalog import builtin_catalog
        seen = []
        async def execute(command, options):
            seen.append(options.timeout_seconds)
            return Result.success(ExecResult('done', '', 0))
        environment = SimpleNamespace(cwd='.', exec=execute)
        tool = create_bash_tool()
        await tool.execute(ToolCallContext('call', 'bash', {'command': 'work'}, env=environment))
        self.assertEqual(seen, [300])
        startup_manager = CommandManager()
        try:
            managed = create_bash_tool(manager=startup_manager)
            await managed.execute(ToolCallContext('start', 'bash',
                {'action': 'start', 'command': 'work', 'wait_seconds': .2}, env=environment))
            await tool.execute(ToolCallContext('override', 'bash',
                {'command': 'work', 'timeout': 17}, env=environment))
            self.assertEqual(seen, [300, 300, 17])
        finally:
            await startup_manager.aclose()
        parameters = builtin_catalog().get('bash-tool').descriptor.normalize_parameters({})
        self.assertEqual(parameters['default_timeout_seconds'], 300)
        manager = CommandManager()
        started = asyncio.Event()
        async def block(context):
            started.set()
            await asyncio.Event().wait()
        try:
            context = ToolCallContext('call', 'bash', {}, env=environment)
            for _ in range(4):
                await manager.start_command(block, context, wait_seconds=0)
            await started.wait()
            with self.assertRaisesRegex(ValueError, 'active command'):
                await manager.start_command(block, context, wait_seconds=0)
            self.assertEqual(parameters['max_active_commands'], manager.max_active)
            self.assertEqual(parameters['retained_commands'], 128)
        finally:
            await manager.aclose()

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

    async def test_background_work_does_not_block_independent_work_and_listener_failure_is_isolated(self):
        from fruitfly_agent.lab.tools.managed import ManagedOperations
        from fruitfly_agent.core.observation import ObservationContext, bind_observation
        operations = ManagedOperations()
        self.addAsyncCleanup(operations.close)
        entered, release = asyncio.Event(), asyncio.Event()
        notices, independent = [], []
        async def work(update):
            entered.set()
            await release.wait()
            return 'result'
        def listen(value):
            notices.append(value)
            raise RuntimeError('offline display failure')
        operations.listener = listen
        with self.assertLogs('fruitfly_agent.lab.tools.managed', level='WARNING'):
            with bind_observation(ObservationContext(run_id='initiator', tool_call_id='call')):
                handle = await operations.submit(work)
            await asyncio.wait_for(entered.wait(), 1)
            independent.append('other work completed')
            self.assertEqual('running', operations.status(handle).state)
            release.set()
            await operations.wait(handle, 1)
        self.assertEqual(['other work completed'], independent)
        self.assertEqual(['running', 'succeeded'], [value.state for value in notices])
        self.assertTrue(all(value.run_id == 'initiator' and value.tool_call_id == 'call' for value in notices))
        await operations.close()
        await operations.close()

    async def test_cancel_before_task_entry_notifies_terminal_state_once(self):
        from fruitfly_agent.lab.tools.managed import ManagedOperations
        operations = ManagedOperations()
        self.addAsyncCleanup(operations.close)
        entered, notices = [], []
        async def work(update):
            entered.append(True)
        operations.listener = lambda status: notices.append(status.state)
        handle = await operations.submit(work)
        await operations.cancel(handle)
        self.assertEqual([], entered)
        self.assertEqual(['running', 'cancelled'], notices)
