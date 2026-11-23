"""Idle maintenance yields to foreground work and obeys shutdown ownership."""
import asyncio
from pathlib import Path
import unittest
from fruitfly_agent.interactive import AgentApplication
from tests.support.application import _Factory, offline_session
from fruitfly_agent.interactive.terminal.features.retained_state.commands import retained_handler
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand


class RetainedApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_overview_explains_authorized_and_legacy_batches(self):
        from fruitfly_agent.interactive.terminal.features.retained_state.views import render_state
        authorized = render_state({'memory_path': '/memory', 'auto_enabled': True,
            'automatic_due': True, 'blocked': True, 'can_run_manually': True,
            'operations': [{'id': 'batch-1', 'status': 'retry-authorized', 'operation': 'extract'}]},
            kind='memory')
        self.assertIn('blocked by unresolved batches', authorized)
        self.assertIn('Retry is already authorized. Use /memory run', authorized)
        self.assertNotIn('To authorize retry', authorized)

    async def test_foreground_submission_proceeds_without_cancelling_maintenance(self):
        started = asyncio.Event(); cancelled = asyncio.Event()
        class Maintenance:
            def __init__(self):
                self.observations = []
            def observe(self, *, completed):
                self.observations.append(completed)
            async def run(self):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
        maintenance = Maintenance()
        class Factory(_Factory):
            async def open(self, **kwargs):
                handle = await super().open(**kwargs)
                handle.maintenance = maintenance
                return handle
        from tests.support.faux_provider import FauxProvider
        provider = FauxProvider(); provider.respond_text('one'); provider.respond_text('two')
        app = AgentApplication(Factory([offline_session(provider=provider)]))
        await app.start(session_path=Path('offline.jsonl'))
        self.addAsyncCleanup(app.close)
        await app.submit('one')
        await asyncio.wait_for(started.wait(), 1)
        with self.assertRaisesRegex(RuntimeError, 'already running'):
            await app.retained_action('operation', 'retry')
        self.assertFalse(cancelled.is_set())
        await asyncio.wait_for(app.submit('two'), 1)
        self.assertFalse(cancelled.is_set())
        self.assertEqual([True, True], maintenance.observations)
        await app.close()
        self.assertTrue(cancelled.is_set())

    async def test_document_commands_only_use_injected_operations(self):
        calls = []
        async def review(identity, action):
            calls.append((identity, action)); return 'committed'
        handler = retained_handler(kind='memory', describe=lambda kind: {'entries': [], 'pending': []},
            read=lambda kind, identity: 'body', review=review)
        result = await handler(InteractiveCommand('memory', ('read', 'note')))
        self.assertIn('body', result.text)
        await handler(InteractiveCommand('memory', ('commit', 'batch')))
        self.assertEqual([('batch', 'commit')], calls)

    async def test_manual_memory_command_uses_injected_run_capability(self):
        calls = []
        async def run(kind, operation_id=None):
            calls.append((kind, operation_id)); return 'completed'
        handler = retained_handler(kind='memory', describe=lambda kind: {}, read=lambda *args: '',
            review=lambda *args: 'ok', run=run)
        result = await handler(InteractiveCommand('memory', ('run',)))
        self.assertEqual([('memory', None)], calls)
        self.assertIn('completed', result.text)

    async def test_manual_memory_command_can_resume_a_specific_batch(self):
        calls = []
        async def run(kind, operation_id=None):
            calls.append((kind, operation_id)); return 'completed'
        handler = retained_handler(kind='memory', describe=lambda kind: {}, read=lambda *args: '',
            review=lambda *args: 'ok', run=run)
        result = await handler(InteractiveCommand('memory', ('run', 'batch-1')))
        self.assertEqual([('memory', 'batch-1')], calls)
        self.assertIn('completed', result.text)

    async def test_new_input_defers_refresh_while_maintenance_owns_its_runtime(self):
        from unittest.mock import AsyncMock
        from tests.support.faux_provider import FauxProvider
        started, release = asyncio.Event(), asyncio.Event()
        class Maintenance:
            def observe(self, *, completed):
                pass
            async def run(self):
                started.set()
                await release.wait()
        class Factory(_Factory):
            async def open(self, **kwargs):
                handle = await super().open(**kwargs)
                handle.maintenance = Maintenance()
                return handle
        provider = FauxProvider()
        provider.respond_text('one')
        provider.respond_text('two')
        factory = Factory([offline_session(provider=provider)])
        factory.prepare_retained_refresh = AsyncMock(return_value=None)
        app = AgentApplication(factory, shutdown_timeout=.1)
        self.addAsyncCleanup(app.close)
        await app.start(session_path=Path('offline.jsonl'))
        await app.submit('one')
        await started.wait()
        factory.prepare_retained_refresh.reset_mock()
        await app.submit('two')
        factory.prepare_retained_refresh.assert_not_awaited()
        self.assertFalse(app._maintenance_task.done())
        release.set()
        await app._maintenance_task
