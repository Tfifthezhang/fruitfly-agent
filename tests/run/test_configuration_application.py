"""Apply saved settings through real recovery and a single Session writer."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.core.session.storage import Session
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.storage.sessions import SessionLeases
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class ConfigurationApplicationTest(unittest.IsolatedAsyncioTestCase):
    async def fixture(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        _write_catalog(root / 'models.yaml', {'a': 'model-a', 'b': 'model-b'})
        provider = FauxProvider()
        registry = Mock()
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'a'}, provider_registry=registry)
        app = AgentApplication(factory)
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, provider

    async def test_repeated_apply_keeps_history_path_lock_and_next_request_uses_new_model(self):
        app, provider = await self.fixture()
        path = Path(app.status.session_path)
        provider.respond_text('first answer')
        await app.submit('first question')
        original = app.conversation()
        approvals = app.authorization
        for model in ('b', 'a', 'b'):
            app.configuration.select_model(model)
            app.configuration.save()
            self.assertEqual(app.status.model, 'model-' + ('a' if model == 'b' else 'b'))
            await app.apply_configuration()
            self.assertEqual(app.status.session_path, str(path))
            self.assertEqual(app.conversation(), original)
            self.assertEqual(app.status.message_count, 2)
            self.assertTrue(Session.inspect(path).locked)
            self.assertIsNot(app.authorization, approvals)
            self.assertEqual(app.status.permission_grants, 0)
            approvals = app.authorization
        provider.respond_text('second answer')
        await app.submit('second question')
        self.assertEqual(provider.calls[-1]['model'], 'model-b')
        self.assertEqual(len(provider.calls[-1]['messages']), 3)
        entries = Session.inspect(path).read_all()
        self.assertEqual([e.id for e in entries], list(range(1, len(entries) + 1)))
        self.assertEqual(len(Session.inspect(path).canonical_messages()), 4)
        await app.close()
        with Session(path) as reopened:
            self.assertEqual(len(reopened.canonical_messages()), 4)

    async def test_empty_current_session_can_apply_but_empty_standalone_resume_cannot(self):
        app, _ = await self.fixture()
        path = app.status.session_path
        app.configuration.select_model('b')
        app.configuration.save()
        await app.apply_configuration()
        self.assertEqual(app.status.model, 'model-b')
        self.assertEqual(app.status.session_path, path)
        self.assertEqual(app.status.message_count, 0)
        await app.close()
        other = AgentApplication(RunApplicationFactory(cwd=Path(path).parents[2], environment={}, provider_registry=Mock()))
        with self.assertRaisesRegex(ValueError, 'nothing to resume'):
            await other.start(resume=True, session_path=Path(path))

    async def test_candidate_failure_keeps_writer_and_active_runtime_then_allows_retry(self):
        app, provider = await self.fixture()
        path = Path(app.status.session_path)
        before = path.read_bytes()
        app.configuration.select_model('b')
        app.configuration.save()
        with patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('startup failed'))):
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                await app.apply_configuration()
        self.assertEqual(app.status.model, 'model-a')
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue(Session.inspect(path).locked)
        provider.respond_text('still available')
        await app.submit('continue with old runtime')
        self.assertEqual(provider.calls[-1]['model'], 'model-a')
        await app.apply_configuration()
        self.assertEqual(app.status.model, 'model-b')
        self.assertEqual(app.status.message_count, 2)
        await app.close()
        with Session(path):
            pass

    async def test_construction_failure_releases_only_candidate_lease(self):
        app, provider = await self.fixture()
        path = Path(app.status.session_path)
        before = path.read_bytes()
        app.configuration.select_model('b')
        app.configuration.save()
        with patch('fruitfly_agent.run.application.build_runtime', side_effect=ValueError('invalid component settings')):
            with self.assertRaisesRegex(ValueError, 'invalid component settings'):
                await app.apply_configuration()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(app.status.model, 'model-a')
        self.assertTrue(Session.inspect(path).locked)
        provider.respond_text('old runtime remains usable')
        await app.submit('continue')
        await app.apply_configuration()
        self.assertEqual(app.status.model, 'model-b')
        self.assertEqual(app.status.message_count, 2)

    async def test_changed_components_rebuild_projection_without_copying_original_messages(self):
        app, provider = await self.fixture()
        provider.respond_text('original answer')
        await app.submit('original question')
        original = app.conversation()
        app.configuration.set_mechanism('compaction', enabled=False)
        app.configuration.save()
        await app.apply_configuration()
        self.assertEqual(app.conversation(), original)
        saved = Session.inspect(app.status.session_path)
        self.assertEqual(len(saved.canonical_messages()), 2)
        self.assertEqual(saved.messages(), saved.canonical_messages())
        self.assertIn('contextProjection', saved.read_all()[-1].payload)


class SessionLeaseTest(unittest.TestCase):
    def test_shared_lease_preserves_exclusive_lock_until_final_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'session.jsonl'
            pool = SessionLeases()
            first = pool.acquire(path, resume=False)
            first.session.append('meta', {'test': True})
            candidate = pool.acquire(path, resume=True)
            self.assertIs(first.session, candidate.session)
            self.assertTrue(candidate.shared)
            with self.assertRaisesRegex(ValueError, 'requires recovery'):
                pool.acquire(path, resume=False)
            first.release()
            first.release()
            self.assertTrue(Session.inspect(path).locked)
            candidate.release()
            self.assertFalse(Session.inspect(path).locked)
