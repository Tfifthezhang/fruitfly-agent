"""Native descriptions change actual requests while operation contracts stay fixed."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.loop import run_agent_loop
from fruitfly_agent.lab.catalog import AssemblyContext, MechanismSelection, assemble_lab, builtin_catalog
from fruitfly_agent.lab.tools.methods.write.algorithm import create_write_tool
from fruitfly_agent.core.tool_runtime import ToolCallContext
from tests.support.faux_provider import FauxProvider


class ToolInstructionTests(unittest.IsolatedAsyncioTestCase):
    async def test_candidate_description_reaches_native_tool_declaration_without_a_catalog_read(self):
        catalog = builtin_catalog()
        provider = FauxProvider()
        with tempfile.TemporaryDirectory() as directory:
            def assemble(parameters):
                return assemble_lab(AgentLoopConfig(provider), catalog=catalog,
                    selections=(MechanismSelection('local-env'), MechanismSelection('write-tool', parameters=parameters)),
                    context=AssemblyContext(Path(directory), None, 'fake', lambda *_: self.fail('auxiliary model')))
            baseline = assemble({})
            self.addCleanup(baseline.config.readable_resources.close)
            target = baseline.components['text-target:write-tool']
            payload = json.loads(target.snapshot().text)
            payload['instructions']['description'] = 'CANDIDATE_DESCRIPTION: write the requested final artifact.'
            target.validate(json.dumps(payload))
            candidate = assemble(target.parse(json.dumps(payload)))
            self.addCleanup(candidate.config.readable_resources.close)
            provider.respond_text('done')
            declarations = []
            def observe(view, *, signal=None):
                declarations.extend(view.tools)
                return provider(view, signal=signal)
            result = await run_agent_loop(replace(candidate.config, provider=observe), [UserMessage('Write an artifact')])
            self.assertFalse(result.is_error)
            self.assertEqual(payload['instructions']['description'], declarations[0].description)
            original, changed = baseline.config.tools[0], candidate.config.tools[0]
            self.assertEqual(original.parameters, changed.parameters)
            self.assertEqual(original.permission, changed.permission)
            self.assertEqual(original.name, changed.name)
            self.assertNotEqual(original.description, changed.description)
            self.assertNotIn('tool-catalog', candidate.components)
            self.assertIsNone(candidate.context_pipeline)
            self.assertIsNot(baseline.config.readable_resources, candidate.config.readable_resources)

    def test_tool_grants_reject_schema_permissions_and_unknown_parameters(self):
        definition = builtin_catalog().get('write-tool')
        for field in ('parameters.settings.schema', 'parameters.settings.permission', 'parameters.instructions.unknown'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                definition.configuration_edit([field], {})

    async def test_resource_references_remain_read_only_destinations(self):
        tool = create_write_tool()
        with self.assertRaisesRegex(ValueError, 'read-only'):
            await tool.execute(ToolCallContext('write', 'write',
                {'path': 'resource://scope/owner/file', 'content': 'changed'}, env=object()))

    async def test_write_rejects_missing_ambiguous_and_ungranted_sources_before_writing(self):
        from fruitfly_agent.lab.environment import LocalEnv
        provider = FauxProvider()
        requested = []
        def read_resource(identity):
            requested.append(identity)
            raise ValueError('resource is not granted')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arguments in ({'path': 'missing'},
                              {'path': 'ambiguous', 'content': 'text', 'resource_id': 'id'},
                              {'path': 'ungranted', 'resource_id': 'id'},
                              {'path': 'valid', 'content': ''}):
                provider.respond_tool_call('write', arguments)
            provider.respond_text('done')
            result = await run_agent_loop(AgentLoopConfig(provider, env=LocalEnv(str(root)),
                tools=(create_write_tool(read_resource),)), [UserMessage('Write the requested files')])
            self.assertFalse(result.is_error)
            self.assertEqual([True, True, True, False],
                [message.is_error for message in result.messages if message.role == 'toolResult'])
            self.assertEqual(['valid'], sorted(path.name for path in root.iterdir()))
            self.assertEqual('', (root / 'valid').read_text())
            self.assertEqual(['id'], requested, 'invalid source combinations never read media')

    async def test_media_save_byte_limit_fails_before_creating_a_destination(self):
        from fruitfly_agent.lab.environment import LocalEnv
        from fruitfly_agent.core.data_model.media import MAX_IMAGE_BYTES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool = create_write_tool(lambda _: b'x' * (MAX_IMAGE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, '10 MiB'):
                await tool.execute(ToolCallContext('save', 'write',
                    {'path': 'too-large', 'resource_id': 'granted'}, LocalEnv(str(root))))
            self.assertEqual([], list(root.iterdir()))
