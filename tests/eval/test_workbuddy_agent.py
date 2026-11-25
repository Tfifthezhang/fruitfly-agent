"""The older engine bridge uses public execution ports and preserves cleanup behavior."""
import asyncio
from pathlib import Path
from types import SimpleNamespace, ModuleType
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_eval.bridges.harbor018 import NativeInstalledAgent018
from fruitfly_eval.workbuddy.agent import WorkBuddyFruitFlyAgent
from tests.support.harbor import installed_agent_inputs


class WorkBuddyAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_execution_rejects_nonzero_without_requiring_private_sdk_hooks(self):
        agent = NativeInstalledAgent018.__new__(NativeInstalledAgent018)
        environment = SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(return_code=7)))
        with self.assertRaisesRegex(RuntimeError, 'exit 7'):
            await agent._exec(environment, 'exit 7', user='root')
        command = environment.exec.call_args.kwargs['command']
        self.assertIn('tee -a /logs/agent/setup.log', command)
        self.assertTrue(agent.SUPPORTS_ATIF)

    async def test_official_user_setup_precedes_native_install(self):
        agent = WorkBuddyFruitFlyAgent.__new__(WorkBuddyFruitFlyAgent)
        order = []
        async def setup(*args): order.append('user')
        async def install(*args): order.append('native')
        module = ModuleType('workbuddy_bench.agents._agent_user')
        module.ensure_agent_user = setup
        with patch.dict('sys.modules', {'workbuddy_bench.agents._agent_user': module}), \
             patch.object(NativeInstalledAgent018, 'install', new=install):
            await agent.install(object())
        self.assertEqual(order, ['user', 'native'])

    async def test_cancelled_native_execution_stops_the_supervisor_before_return(self):
        agent = NativeInstalledAgent018.__new__(NativeInstalledAgent018)
        with tempfile.TemporaryDirectory() as directory:
            installed_agent_inputs(agent, Path(directory))
            agent.profile = 'baseline'
            agent.exec_as_agent = AsyncMock(side_effect=[asyncio.CancelledError(), SimpleNamespace(return_code=0)])
            with self.assertRaises(asyncio.CancelledError):
                await agent._run_task('Work', SimpleNamespace(stop=AsyncMock()), SimpleNamespace())
            self.assertEqual(agent.exec_as_agent.await_count, 2)
            self.assertIn('--stop', agent.exec_as_agent.call_args.kwargs['command'])
