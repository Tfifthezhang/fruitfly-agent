"""Idle maintenance yields to foreground work and obeys shutdown ownership."""
import asyncio
from pathlib import Path
import unittest
from fruitfly_agent.interactive import AgentApplication
from tests.support.application import _Factory, offline_session
from fruitfly_agent.interactive.terminal.features.retained_state.commands import retained_handler
from fruitfly_agent.interactive.contracts.commands import InteractiveCommand


class RetainedApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_submission_cancels_and_retires_idle_maintenance(self):
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
        await asyncio.wait_for(app.submit('two'), 1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual([True, True], maintenance.observations)
        await app.close()

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
