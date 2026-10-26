"""MCP schemas, attributed content and retained reply access through Core tools."""
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.lab.mcp.client import McpClient
from fruitfly_agent.lab.mcp.config import load_config
from fruitfly_agent.lab.mcp.schemas import compile_schema
from fruitfly_agent.lab.mcp.results import ResultStore
from fruitfly_agent.lab.mcp.tools import make_tools, tool_name
from tests.support.mcp import HAS_MCP, write_mcp_config, MemoryArtifacts


@unittest.skipUnless(HAS_MCP, 'install the optional [mcp] extra')
class McpToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    async def tools(self, selected, **options):
        config = load_config(write_mcp_config(self.root, tools=selected, **options), self.root)[0]
        client = McpClient(config, {})
        self.addAsyncCleanup(client.close)
        await client.start()
        self.artifacts = MemoryArtifacts()
        store = ResultStore(config, self.artifacts.write, self.artifacts.read)
        tools, _ = make_tools(client, store)
        return tools, store

    async def test_refs_unions_nulls_and_integer_types_are_validated_without_coercion(self):
        tools, _ = await self.tools(('echo',))
        validate = tools[0].validate_arguments
        self.assertEqual({'value': None}, validate({'value': None}).unwrap())
        for args in ({'value': 1}, {'value': 'ok', 'count': '3'}, {'value': 'ok', 'extra': 1}):
            self.assertFalse(validate(args).is_ok)
        reply = await tools[0].execute(ToolCallContext('1', tools[0].name, {'value': None}, None))
        self.assertIn('"value": null', reply.content[0].text)
        self.assertEqual(1, reply.content[0].text.count('"value"'), 'duplicate text and structured output should be merged')

    async def test_large_result_is_complete_and_can_be_paged_only_from_issued_references(self):
        tools, store = await self.tools(('large',), inline_result_chars=100)
        result = await tools[0].execute(ToolCallContext('1', tools[0].name, {'value': 'large'}, None))
        self.assertIn('truncated', result.content[0].text)
        reference = next(iter(store.references))
        self.assertIn('x' * 25000, self.artifacts.read(reference))
        page = tools[-1].execute(ToolCallContext('2', tools[-1].name, {'reference': reference, 'limit': 12000}, None))
        self.assertIn('next_offset', page.content[0].text)
        denied = store.read({'reference': 'sha256:' + '0' * 64})
        self.assertTrue(denied.is_error)

    async def test_error_and_image_results_keep_their_meaning(self):
        tools, _ = await self.tools(('fail', 'image'))
        failure = await tools[0].execute(ToolCallContext('1', tools[0].name, {'value': 'fail'}, None))
        image = await tools[1].execute(ToolCallContext('2', tools[1].name, {'value': 'image'}, None))
        self.assertTrue(failure.is_error)
        self.assertEqual('image', image.content[1].type)

    async def test_missing_or_duplicate_catalog_fails_instead_of_silently_skipping(self):
        for options in ({'selected': ('absent',)}, {'selected': ('echo',), 'mode': 'duplicate'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                await self.tools(**options)

    def test_remote_references_and_unknown_dialects_are_rejected(self):
        for schema in ({'type': 'object', 'properties': {'v': {'$ref': 'https://example.com/schema'}}},
                       {'type': 'object', '$schema': 'https://example.com/draft'}):
            with self.assertRaises(ValueError):
                compile_schema(schema)

    def test_names_are_bounded_stable_and_collision_resistant(self):
        name = tool_name('service-' * 6, 'original-' * 20)
        self.assertLessEqual(len(name), 64)
        self.assertEqual(name, tool_name('service-' * 6, 'original-' * 20))
        self.assertNotEqual(tool_name('a', 'x.y'), tool_name('a', 'x_y'))
