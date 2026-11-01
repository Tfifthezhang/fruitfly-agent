"""History is a working-memory resource, accessed through the ordinary read tool."""
import json
import tempfile
from pathlib import Path
import unittest
from fruitfly_agent.core.data_model import ContextItem, AssistantMessage, ThinkingBlock, TextBlock
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest, ToolPermission
from fruitfly_agent.lab.context_manager.resources import SessionHistory
from fruitfly_agent.lab.context_manager.resources.views import history_view
from fruitfly_agent.lab.tools.resources import ResourceRegistry, ResourceAuthorizer
from fruitfly_agent.lab.tools.read import create_read_tool


class ContextHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_sources_use_read_without_thinking_or_filesystem_fallback(self):
        history = SessionHistory()
        history.bind((ContextItem('session:1', AssistantMessage([ThinkingBlock('private thought'), TextBlock('middle evidence')])),))
        resources = ResourceRegistry()
        history.resource_prefix = resources.mount('memory', lambda path: history_view(history, path))
        tool = create_read_tool(resources=resources)
        authorizer = ResourceAuthorizer(resources, None)
        path = history.resource_prefix + 'messages/session:1'
        async with authorizer.authorize(AuthorizationRequest('c', 'read', {'path':path}, tool.permission)) as grant:
            self.assertTrue(grant.allowed)
            result = await tool.execute(ToolCallContext('c', 'read', {'path':path}, env=None))
        self.assertIn('middle evidence', result.content[0].text)
        self.assertNotIn('private thought', result.content[0].text)
        directory = json.loads(resources.read(history.resource_prefix + 'index'))
        self.assertEqual(directory['messages'][0]['reference'], path)
        for operation, reference in (('write',path), ('edit',path), ('read',ResourceRegistry().mount('memory', lambda p:b'private')+'index'),
                                     ('read',history.resource_prefix+'../file'), ('read',history.resource_prefix+'messages/%2fetc')):
            async with authorizer.authorize(AuthorizationRequest('c', operation, {'path':reference}, ToolPermission(operation, ('path',)))) as grant:
                self.assertFalse(grant.allowed)
        resources.close()
        with self.assertRaisesRegex(ValueError, 'retired'):
            resources.read(path)

    async def test_artifact_pages_hash_corruption_and_session_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            history = SessionHistory(Path(directory))
            text = 'x' * 100 + 'MIDDLE' + 'y' * 100
            ref = history.put(text)
            self.assertEqual(ref, history.put(text))
            self.assertIn('Continue at offset=100', history.read(ref, limit=100))
            self.assertEqual('MIDDLE', history.read(ref, offset=100, limit=6).split('\n')[0])
            with self.assertRaises(KeyError): SessionHistory().read(ref)
            (Path(directory) / (ref[7:] + '.txt')).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'identity'): history.read(ref)

    def test_resource_scope_is_stable_for_recovery_and_distinct_across_sessions(self):
        first = ResourceRegistry(scope='/sessions/first.jsonl')
        restored = ResourceRegistry(scope='/sessions/first.jsonl')
        other = ResourceRegistry(scope='/sessions/second.jsonl')
        self.assertEqual(first.mount('memory',lambda path:b'original'), restored.mount('memory',lambda path:b'original'))
        with self.assertRaises(ValueError):
            other.read(first.mount('another',lambda path:b'private')+'index')

    async def test_large_single_line_history_can_be_recovered_with_character_pages(self):
        resources=ResourceRegistry();history=SessionHistory()
        history.bind((ContextItem('one',AssistantMessage([TextBlock('x'*100000+'MIDDLE'+'y'*100000)])),))
        history.resource_prefix=resources.mount('memory',lambda path:history_view(history,path))
        tool=create_read_tool(resources=resources)
        reference=history.resource_prefix+'messages/one'
        original=resources.read(reference).decode()
        offset=original.index('MIDDLE')
        result=await tool.execute(ToolCallContext('c','read',{'path':reference,'character_offset':offset,'character_limit':6},env=None))
        self.assertTrue(result.content[0].text.startswith('MIDDLE\n['))
        for args in ({'character_offset':True},{'character_limit':0},{'character_limit':24001},
                     {'character_offset':0,'offset':1}):
            with self.subTest(args=args),self.assertRaises(ValueError):
                await tool.execute(ToolCallContext('c','read',{'path':reference,**args},env=None))
