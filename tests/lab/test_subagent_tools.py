"""Model operations remain one group with independent descriptions and schemas."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.agents.subagent.tools import create_tools
from fruitfly_agent.lab.catalog import builtin_catalog
from tests.support.subagents import ChildFixture

class SubagentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_five_tools_and_repeated_waits_return_actual_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ChildFixture(directory)
            service = fixture.service()
            try:
                service.begin()
                definition = builtin_catalog().get('subagent')
                params = definition.descriptor.normalize_parameters({})
                tools = {t.name: t for t in create_tools(service, params)}
                self.assertEqual({'subagent_spawn', 'subagent_send', 'subagent_wait', 'subagent_status', 'subagent_cancel'}, set(tools))
                self.assertEqual(5, len({t.description for t in tools.values()}))
                async def call(name, args):
                    result = await tools[name].execute(ToolCallContext('call', name, args, env=None, signal=asyncio.Event()))
                    return result, json.loads(result.content[0].text)
                _, row = await call('subagent_spawn', {'task': 'Inspect'})
                ref = {key: row[key] for key in ('agent_id', 'run_id')}
                _, result = await call('subagent_wait', {'executions': [ref], 'timeout_seconds': 1})
                self.assertEqual('completed', result['executions'][0]['state'])
                self.assertFalse(result['timed_out'])
                _, repeated = await call('subagent_wait', {'executions': [ref]})
                self.assertEqual(result, repeated)
                error, value = await call('subagent_send', {**ref, 'mode': 'steer', 'message': 'late'})
                self.assertTrue(error.is_error)
                self.assertEqual('invalid_state', value['error'])
            finally:
                await service.close()


    async def test_exact_admission_retry_reuses_receipt_and_invalid_bounds_never_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ChildFixture(directory)
            service = fixture.service()
            try:
                service.begin()
                parameters = builtin_catalog().get('subagent').descriptor.normalize_parameters({})
                tools = {t.name: t for t in create_tools(service, parameters)}
                tool = tools['subagent_spawn']
                context = ToolCallContext('same-call', tool.name, {'task': 'Inspect'}, env=None)
                first = await tool.execute(context)
                repeated = await tool.execute(context)
                self.assertEqual(first, repeated)
                self.assertEqual(1, len(service.snapshot()['executions']))
                conflict = await tool.execute(ToolCallContext('same-call', tool.name, {'task': 'Different'}, env=None))
                self.assertTrue(conflict.is_error)
                cases = [
                    ('subagent_spawn', {'task': None}),
                    ('subagent_spawn', {'task': 'x' * 16001}),
                    ('subagent_spawn', {'task': 'Inspect', 'api_key': 'offline-placeholder'}),
                    ('subagent_wait', {'executions': []}),
                    ('subagent_wait', {'executions': [{'agent_id': 'a', 'run_id': 'b'}], 'timeout_seconds': float('nan')}),
                    ('subagent_status', {'limit': True}),
                ]
                for name, arguments in cases:
                    with self.subTest(tool=name, arguments=arguments):
                        self.assertFalse(tools[name].validate_arguments(arguments).is_ok)
            finally:
                await service.close()
