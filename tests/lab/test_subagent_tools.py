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

    async def test_configured_protocol_rejects_before_admission_and_pages_full_result(self):
        from fruitfly_agent.lab.agents.subagent.configuration import ProtocolSettings, ResultSettings
        with tempfile.TemporaryDirectory() as directory:
            fixture = ChildFixture(directory)
            service = fixture.service(
                protocol=ProtocolSettings(max_task_characters=8, max_context_characters=8,
                    max_message_characters=8, default_wait_seconds=0, max_wait_seconds=1),
                results=ResultSettings(output_page_characters=3, summary_characters=6,
                    summary_preview_characters=4, task_preview_characters=2,
                    default_list_entries=1, max_list_entries=2))
            try:
                service.begin()
                params = builtin_catalog().get('subagent').descriptor.normalize_parameters({})
                tools = {t.name: t for t in create_tools(service, params)}
                async def call(name, args):
                    result = await tools[name].execute(ToolCallContext('call-' + name, name, args, env=None))
                    return result, json.loads(result.content[0].text)
                error, _ = await call('subagent_spawn', {'task': 'too long task'})
                self.assertTrue(error.is_error)
                self.assertEqual((), service.snapshot()['executions'])
                self.assertFalse(tools['subagent_wait'].validate_arguments(
                    {'executions': [{'agent_id': 'a', 'run_id': 'r'}], 'timeout_seconds': 2}).is_ok)
                _, row = await call('subagent_spawn', {'task': 'Inspect'})
                ref = {key: row[key] for key in ('agent_id', 'run_id')}
                await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=1)
                _, detail = await call('subagent_status', {**ref, 'output_offset': 3})
                self.assertEqual('ld ', detail['output'])
                self.assertEqual(6, detail['next_output_offset'])
                self.assertEqual('chil', detail['summary'])
                retained = service.detail(row['agent_id'])
                self.assertEqual('child ', retained['summary'])
                self.assertEqual('child result', service.store.read_result(retained)['output'])
            finally:
                await service.close()

    def test_protocol_and_result_cross_field_constraints_reject_invalid_configuration(self):
        from fruitfly_agent.lab.agents.subagent.configuration import ProtocolSettings, ResultSettings
        for values in ({'default_wait_seconds': 2, 'max_wait_seconds': 1},
                {'max_context_characters': True}, {'max_wait_seconds': float('nan')}):
            with self.subTest(protocol=values), self.assertRaises(ValueError):
                ProtocolSettings(**values)
        for values in ({'default_list_entries': 3, 'max_list_entries': 2},
                {'summary_characters': 2, 'summary_preview_characters': 3}):
            with self.subTest(results=values), self.assertRaises(ValueError):
                ResultSettings(**values)

    def test_inheritance_configuration_rejects_ambiguous_or_recursive_grants(self):
        from fruitfly_agent.lab.agents.subagent.configuration import InheritanceSettings
        for values in ({'mode': 'all'}, {'components': ['read-tool']},
                {'mode': 'explicit', 'components': ['read-tool', 'read-tool']},
                {'mode': 'explicit', 'components': ['subagent']}):
            with self.subTest(inheritance=values), self.assertRaises(ValueError):
                InheritanceSettings(**values)

    def test_named_worker_grammar_rejects_unknown_fields_and_permission_expansion(self):
        from copy import deepcopy
        from fruitfly_agent.lab.agents.subagent.workers import worker_definitions
        definition = builtin_catalog().get('subagent')
        defaults = definition.descriptor.normalize_parameters({})['workers']
        for change in ('unknown', 'write', 'tool', 'inheritance', 'count', 'result'):
            value = deepcopy(defaults['evidence-reader'])
            if change == 'unknown': value['unexpected'] = True
            elif change == 'write': value['capabilities']['writes'] = 'allow'
            elif change == 'tool': value['capabilities']['tools'] = ['bash']
            elif change == 'inheritance': value['inheritance']['conversation'] = 'parent'
            elif change == 'count': value['limits']['model_requests'] = True
            else: value['result']['contract'] = 'candidate'
            with self.subTest(change=change), self.assertRaises(ValueError):
                worker_definitions({'workers': {'custom': value}})
        self.assertEqual({'evidence-reader', 'record-organizer', 'cross-record-reader', 'counterexample-reader'}, set(worker_definitions({})))
