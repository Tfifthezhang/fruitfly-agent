"""Runtime permissions behavior and failure contracts."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from fruitfly_agent.core.session import Session
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class RuntimePermissionWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_tools_confirm_and_restore_does_not_restore_grants(self):
        from fruitfly_agent.interactive import AgentApplication
        from fruitfly_agent.run import RunApplicationFactory
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            workspace = root / 'workspace'
            workspace.mkdir()
            _write_catalog(workspace / '.fruitfly/models.yaml', {'offline': 'offline-model'})
            provider = FauxProvider()
            registry = Mock()
            registry.create.return_value = provider
            factory = RunApplicationFactory(cwd=workspace,
                environment={'TEST_API_KEY': 'offline-placeholder'}, provider_registry=registry)
            factory.configuration.set_mechanism('compaction', enabled=False)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            self.addAsyncCleanup(app.close)
            prompts = []
            async def approve(prompt):
                prompts.append(prompt)
                return 'session'
            app.set_authorization_handler(approve)
            path = workspace / '.fruitfly' / 'sessions' / 'permissions.jsonl'
            await app.start(session_path=path)
            target = root / 'outside.txt'
            provider.respond_tool_call('write', {'path': str(target), 'content': 'first'})
            provider.respond_text('written')
            result = await app.submit('write external file')
            self.assertFalse(result.is_error)
            self.assertEqual('first', target.read_text())
            self.assertEqual(1, len(prompts))
            self.assertEqual(1, app.status.permission_grants)
            provider.respond_tool_call('read', {'path': str(target)})
            provider.respond_text('read')
            await app.submit('read approved directory')
            self.assertEqual(1, len(prompts))
            await app.close()
            await app.start(resume=True, session_path=path)
            self.assertEqual(0, app.status.permission_grants)
            provider.respond_tool_call('write', {'path': str(target), 'content': 'second'})
            provider.respond_text('written again')
            await app.submit('write after restore')
            self.assertEqual(2, len(prompts))
            self.assertEqual('second', target.read_text())
            app.clear_authorizations()
            self.assertEqual(0, app.status.permission_grants)
            await app.close()
            with Session(path) as durable:
                decisions = [e.payload for e in durable.read_all() if e.payload.get('kind') == 'authorization']
                self.assertEqual(3, len(decisions))
                self.assertTrue(all(e['allowed'] for e in decisions))
                self.assertTrue(all('arguments' not in e and 'command' not in e for e in decisions))
