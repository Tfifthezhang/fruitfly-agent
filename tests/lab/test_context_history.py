"""Session-only public retrieval, bounded pagination and immutable identity."""
import json
import tempfile
from pathlib import Path
import unittest
from fruitfly_agent.core.data_model import ContextItem, AssistantMessage, ThinkingBlock, TextBlock
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest
from fruitfly_agent.lab.environment.permissions import PermissionPolicy, PermissionAuthorizer
from fruitfly_agent.lab.context_manager.history import SessionHistory
from fruitfly_agent.lab.tools.context import context_tools


class ContextHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_sources_are_retrievable_without_thinking_or_paths(self):
        history = SessionHistory()
        history.bind((ContextItem('session:1', AssistantMessage([ThinkingBlock('private thought'), TextBlock('middle evidence')])) ,))
        tools = {t.name: t for t in context_tools(history)}
        authorizer = PermissionAuthorizer(PermissionPolicy(Path.cwd()))
        search = tools['context_search']
        async with authorizer.authorize(AuthorizationRequest('c', search.name, {'query': 'evidence'}, search.permission)) as grant:
            self.assertTrue(grant.allowed)
            result = await search.execute(ToolCallContext('c', search.name, {'query': 'evidence'}, env=None))
        found = json.loads(result.content[0].text)
        self.assertEqual('session:1', found[0]['reference'])
        text = history.read('session:1')
        self.assertNotIn('private thought', text)
        self.assertIn('middle evidence', text)
        with self.assertRaises(ValueError): history.read('/etc/passwd')
        with self.assertRaises(ValueError): history.read('session:1', limit=1000000)

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
