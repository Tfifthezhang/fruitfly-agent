"""External stdio tools through preparation, Application and current-config recovery."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand
from fruitfly_agent.interactive.interaction.commands import CommandRouter
from fruitfly_agent.lab.catalog import builtin_catalog, resolve_harness
from fruitfly_agent.lab.mcp.tools import tool_name
from fruitfly_agent.run import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.mcp import HAS_MCP, PEER, write_mcp_config
from tests.support.run import _write_catalog


@unittest.skipUnless(HAS_MCP, 'install the optional [mcp] extra')
class McpApplicationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        _write_catalog(self.root / '.fruitfly/models.yaml', {'offline': 'offline-model'})
        self.provider = FauxProvider()
        self.registry = Mock()
        self.registry.create.return_value = self.provider
        self.starts, self.prompts = [], []

    async def approve(self, plan):
        self.starts.append(plan)
        return True

    async def confirm(self, prompt):
        self.prompts.append(prompt)
        return 'session'

    def factory(self, *, approve=True, **options):
        factory = RunApplicationFactory(cwd=self.root, environment={'FIXTURE_SECRET': 'fixture-private-value'},
            provider_registry=self.registry, tool_service_startup_approval=self.approve if approve else None, **options)
        factory.configuration.set_mechanism('compaction', enabled=False)
        factory.configuration.set_mechanism('mcp-tools', enabled=True)
        factory.configuration.save()
        factory.reload_configuration()
        return factory

    async def application(self, factory):
        app = AgentApplication(factory)
        self.addAsyncCleanup(app.close)
        app.set_authorization_handler(self.confirm)
        await app.start(session_path=self.root / '.fruitfly/sessions/mcp.jsonl')
        return app

    async def test_selected_tools_execute_and_recovery_rebinds_current_config_without_grants(self):
        write_mcp_config(self.root, secret_env={'SERVICE_KEY': 'FIXTURE_SECRET'})
        factory = self.factory()
        with self.assertRaisesRegex(ValueError, 'preparation'):
            resolve_harness(factory.configuration.profile(), builtin_catalog())
        app = await self.application(factory)
        self.assertEqual([], self.provider.calls)
        self.assertEqual(8, app.runtime_manifest['schema_version'])
        declaration = app.runtime_manifest['tool_services'][0]
        self.assertEqual([tool_name('fixture', 'echo'), tool_name('fixture', 'retained_result')], declaration['tools'])
        snapshot = factory.artifact_store.read_text(declaration['artifact'])
        self.assertIn('FIXTURE_SECRET', snapshot)
        self.assertNotIn('fixture-private-value', snapshot)
        status = app.status
        self.assertEqual('ready', status.tool_services[0].state)
        self.assertEqual('Local host', status.tool_services[0].location)
        panel = CommandRouter().execute(InteractiveCommand('lab'), app).text
        self.assertIn('Tool services', panel)
        self.assertIn('stdio', panel)
        self.assertEqual(('SERVICE_KEY',), self.starts[0].environment_names)
        for _ in range(2):
            self.provider.respond_tool_call(tool_name('fixture', 'echo'), {'value': None})
            self.provider.respond_text('done')
            result = await app.submit('echo')
            reply = next(m for m in result.messages if m.role == 'toolResult')
            self.assertFalse(reply.is_error)
            self.assertIn('"value": null', reply.text)
        self.assertEqual(1, len(self.prompts))
        self.assertEqual(1, app.status.permission_grants)
        path = Path(app.status.session_path)
        original = app.runtime_manifest['digest']
        await app.close()
        write_mcp_config(self.root, tools=('large',))
        await app.start(resume=True, session_path=path)
        self.assertEqual(2, len(self.starts))
        self.assertEqual(0, app.status.permission_grants)
        self.assertNotEqual(original, app.runtime_manifest['digest'])
        self.assertNotIn(tool_name('fixture', 'echo'), app.status.tool_names)
        self.assertIn(tool_name('fixture', 'large'), app.status.tool_names)
        history = path.read_text()
        self.assertNotIn('fixture-private-value', history)
        self.assertIn('external_tool', history)

    async def test_startup_default_denies_before_process_or_provider_creation(self):
        pidfile = self.root / 'peer.pid'
        write_mcp_config(self.root, args=[str(PEER), '--pidfile', str(pidfile)])
        factory = self.factory(approve=False)
        app = AgentApplication(factory)
        self.addAsyncCleanup(app.close)
        with self.assertRaisesRegex(PermissionError, 'startup'):
            await app.start()
        self.assertFalse(pidfile.exists())
        self.registry.create.assert_not_called()

    async def test_failure_in_second_service_cleans_first_process_and_releases_session(self):
        path = write_mcp_config(self.root)
        data = yaml.safe_load(path.read_text())
        first = data['servers']['fixture']
        pidfile = self.root / 'peer.pid'
        first['args'] = [str(PEER), '--pidfile', str(pidfile)]
        second = {**first, 'args': [str(PEER), '--mode', 'duplicate']}
        data['servers']['second'] = second
        path.write_text(yaml.safe_dump(data))
        factory = self.factory()
        app = AgentApplication(factory)
        self.addAsyncCleanup(app.close)
        session_path = self.root / '.fruitfly/sessions/failed.jsonl'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            await app.start(session_path=session_path)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)
        self.registry.create.assert_not_called()
        write_mcp_config(self.root)
        await app.start(session_path=session_path)
        self.assertEqual('ready', app.status.tool_services[0].state)

    async def test_failed_configuration_apply_keeps_active_process_and_frozen_tools(self):
        write_mcp_config(self.root)
        factory = self.factory()
        app = await self.application(factory)
        original = app.runtime_manifest
        write_mcp_config(self.root, tools=('absent',))
        with self.assertRaisesRegex(ValueError, 'absent'):
            await app.apply_configuration()
        self.assertEqual(original, app.runtime_manifest)
        self.assertEqual('ready', app.status.tool_services[0].state)
        self.provider.respond_tool_call(tool_name('fixture', 'echo'), {'value': 'old runtime'})
        self.provider.respond_text('done')
        result = await app.submit('continue')
        self.assertFalse(next(m for m in result.messages if m.role == 'toolResult').is_error)

    async def test_external_call_defaults_to_deny_even_with_unrestricted_local_policy(self):
        from fruitfly_agent.lab.catalog import PermissionPolicy
        write_mcp_config(self.root)
        factory = self.factory(permission_policy=PermissionPolicy.unrestricted(self.root))
        app = await self.application(factory)
        app.set_authorization_handler(None)
        self.provider.respond_tool_call(tool_name('fixture', 'echo'), {'value': 'no grant'})
        self.provider.respond_text('denied')
        result = await app.submit('try')
        self.assertTrue(next(m for m in result.messages if m.role == 'toolResult').is_error)
        self.assertEqual(0, app.status.permission_grants)

    async def test_catalog_change_is_visible_and_does_not_silently_replace_tools(self):
        write_mcp_config(self.root, tools=('change',))
        app = await self.application(self.factory())
        original = app.runtime_manifest
        self.provider.respond_tool_call(tool_name('fixture', 'change'), {'value': 'changed'})
        self.provider.respond_text('done')
        await app.submit('change catalog')
        await asyncio.sleep(0.05)
        self.assertIn('catalog changed', app.status.tool_services[0].state)
        self.assertEqual(original, app.runtime_manifest)

    async def test_recovery_rejects_missing_declaration_artifact_before_startup(self):
        write_mcp_config(self.root)
        factory = self.factory()
        app = await self.application(factory)
        self.provider.respond_text('saved conversation')
        await app.submit('save')
        reference = app.runtime_manifest['tool_services'][0]['artifact']
        path = Path(app.status.session_path)
        await app.close()
        (self.root / '.fruitfly/artifacts' / reference.removeprefix('sha256:')).unlink()
        with self.assertRaisesRegex(ValueError, 'artifact is unavailable'):
            await app.start(resume=True, session_path=path)
        self.assertEqual(1, len(self.starts))
