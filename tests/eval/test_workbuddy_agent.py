"""WorkBuddy uses the shared engine bridge and preserves user setup and cleanup."""
import asyncio
from pathlib import Path
from types import SimpleNamespace, ModuleType
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_eval.harbor_agent import FruitFlyHarborAgent
from fruitfly_eval.workbuddy.agent import WorkBuddyFruitFlyAgent
from tests.support.harbor import installed_agent_inputs


class WorkBuddyAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_user_setup_precedes_native_install(self):
        agent = WorkBuddyFruitFlyAgent.__new__(WorkBuddyFruitFlyAgent)
        order = []
        async def setup(*args): order.append('user')
        async def install(*args):
            agent.runtime_python = '/python'
            agent.runtime_environment = {}
            order.append('native')
        module = ModuleType('workbuddy_bench.agents._agent_user')
        module.ensure_agent_user = setup
        with patch.dict('sys.modules', {'workbuddy_bench.agents._agent_user': module}), \
             patch.object(FruitFlyHarborAgent, 'install', new=install), \
             patch('fruitfly_eval.harbor.cache_access.configure', new=AsyncMock()):
            await agent.install(object())
        self.assertEqual(order, ['user', 'native'])

    async def test_cancelled_native_execution_stops_the_supervisor_before_return(self):
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        with tempfile.TemporaryDirectory() as directory:
            installed_agent_inputs(agent, Path(directory))
            agent.profile = 'baseline'
            agent.exec_as_agent = AsyncMock(side_effect=[asyncio.CancelledError(), SimpleNamespace(return_code=0)])
            with self.assertRaises(asyncio.CancelledError):
                await agent._run_task('Work', SimpleNamespace(stop=AsyncMock()), SimpleNamespace())
            self.assertEqual(agent.exec_as_agent.await_count, 2)
            self.assertIn('--stop', agent.exec_as_agent.call_args.kwargs['command'])
