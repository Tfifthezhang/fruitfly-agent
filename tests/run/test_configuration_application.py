"""Apply saved settings through real recovery and a single Session writer."""
from pathlib import Path
import io
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.core.session.storage import Session
from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.storage.sessions import SessionLeases
from fruitfly_agent.providers.registry import default_registry, load_model_specs
from fruitfly_agent.run.configuration.profile import load_harness_config
from fruitfly_agent.run.runtime.recovery import record_session_manifest
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog
from tests.support.terminal import MenuScriptedLines


class ConfigurationApplicationTest(unittest.IsolatedAsyncioTestCase):
    async def fixture(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        _write_catalog(root / '.fruitfly/models.yaml', {'a': 'model-a', 'b': 'model-b'})
        provider = FauxProvider()
        registry = Mock()
        registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'a'}, provider_registry=registry)
        factory.configuration.save()
        app = AgentApplication(factory)
        await app.start()
        self.addAsyncCleanup(app.close)
        return app, provider

    async def test_draft_applies_without_prior_save_and_uses_new_model_on_next_turn(self):
        app, provider = await self.fixture()
        provider.respond_text('first answer')
        await app.submit('first question')
        original = app.conversation()
        path = Path(app.status.session_path)
        controller = app.configuration
        saved = controller.config_path.read_bytes()
        controller.select_model('b')
        self.assertEqual(controller.config_path.read_bytes(), saved)
        await app.apply_configuration()
        self.assertIs(app.configuration, controller)
        self.assertEqual(app.status.session_path, str(path))
        self.assertEqual(app.conversation(), original)
        self.assertFalse(controller.changed)
        self.assertEqual(load_harness_config(controller.config_path).select().model_profile, 'b')
        provider.respond_text('next answer')
        await app.submit('next question')
        self.assertEqual(provider.calls[-1]['model'], 'model-b')
        self.assertEqual(len(provider.calls[-1]['messages']), 3)

    async def test_failed_draft_application_keeps_files_history_and_draft_for_retry(self):
        for phase in ('construction', 'startup', 'saving', 'recording'):
            with self.subTest(phase=phase):
                app, provider = await self.fixture()
                controller = app.configuration
                saved = controller.config_path.read_bytes()
                path = Path(app.status.session_path)
                history = path.read_bytes()
                controller.select_model('b')
                if phase == 'construction':
                    failure = patch('fruitfly_agent.run.application.build_runtime', side_effect=ValueError('injected failure'))
                elif phase == 'startup':
                    failure = patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('injected failure')))
                elif phase == 'saving':
                    failure = patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('injected failure'))
                else:
                    def fail_after_record(*args, **kwargs):
                        record_session_manifest(*args, **kwargs)
                        raise OSError('injected failure')
                    failure = patch('fruitfly_agent.run.runtime.preparation.record_session_manifest', side_effect=fail_after_record)
                with failure, self.assertRaisesRegex((ValueError, RuntimeError, OSError), 'injected failure'):
                    await app.apply_configuration()
                self.assertEqual(controller.config_path.read_bytes(), saved)
                self.assertEqual(path.read_bytes(), history)
                self.assertEqual(app.status.model, 'model-a')
                self.assertTrue(controller.changed)
                self.assertEqual(controller.profile().model_profile, 'b')
                provider.respond_text('old runtime works')
                await app.submit('continue')
                self.assertEqual(provider.calls[-1]['model'], 'model-a')
                await app.apply_configuration()
                self.assertEqual(app.status.model, 'model-b')
                self.assertFalse(controller.changed)
                self.assertEqual(app.status.message_count, 2)
                await app.close()

    async def test_new_model_and_credentials_are_private_until_activation_and_survive_failure(self):
        app, _ = await self.fixture()
        controller = app.configuration
        setup = controller.model_setup
        setup.registry = default_registry()
        setup.stage('openai', dict(profile='new', model='model-new', context_window='8192',
            max_output_tokens='1024', api_key_env='NEW_TEST_KEY'), 'offline-placeholder')
        catalog = setup.config_path.parent / 'models.yaml'
        secret_file = setup.config_path.parent / 'secrets.env'
        before = catalog.read_bytes()
        for failure in ('startup', 'saving', 'recording'):
            with self.subTest(failure=failure):
                if failure == 'startup':
                    fault = patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('injected failure')))
                elif failure == 'saving':
                    fault = patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('injected failure'))
                else:
                    fault = patch('fruitfly_agent.run.runtime.preparation.record_session_manifest', side_effect=OSError('injected failure'))
                with fault, self.assertRaisesRegex((RuntimeError, OSError), 'injected failure'):
                    await app.apply_configuration()
                self.assertEqual(catalog.read_bytes(), before)
                self.assertFalse(secret_file.exists())
                self.assertNotIn('NEW_TEST_KEY', setup.environment)
                self.assertTrue(setup.changed)
                self.assertEqual(controller.profile().model_profile, 'new')
        await app.apply_configuration()
        self.assertEqual(app.status.model, 'model-new')
        self.assertIn('new', load_model_specs(catalog))
        self.assertEqual(setup.environment['NEW_TEST_KEY'], 'offline-placeholder')
        self.assertEqual(secret_file.stat().st_mode & 0o777, 0o600)
        self.assertFalse(setup.changed)

    async def test_algorithm_replacement_is_assembled_without_terminal_or_parameter_edits(self):
        app, provider = await self.fixture()
        provider.respond_text('answer')
        await app.submit('question')
        original = app.conversation()
        path = app.status.session_path
        for algorithm in ('working-memory-reduction', 'compaction'):
            app.configuration.select_algorithm('reduction', algorithm)
            await app.apply_configuration()
            self.assertEqual(app.status.session_path, path)
            self.assertEqual(app.conversation(), original)
            self.assertIn(algorithm, [c['id'] for c in app.runtime_manifest['components']])
        self.assertEqual(len(provider.calls), 1)

    async def test_terminal_model_change_keeps_transcript_and_only_prints_one_welcome(self):
        app, provider = await self.fixture()
        provider.respond_text('retained answer')
        await app.submit('retained question')
        path = app.status.session_path
        output = io.StringIO()
        reader = MenuScriptedLines(output, '/config', '@model', '@b', 'back',
            '@Save and apply to this conversation', '/exit')
        await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=reader).run()
        text = output.getvalue()
        self.assertEqual(text.count('FruitFlyAgent interactive'), 1)
        self.assertEqual(text.count('retained question'), 1)
        self.assertEqual(text.count('retained answer'), 1)
        self.assertNotIn('Save only', text)
        self.assertIn('configuration applied; conversation retained', text)
        self.assertEqual(app.status.session_path, path)
        self.assertEqual(app.status.model, 'model-b')
        self.assertEqual(app.status.message_count, 2)
        self.assertEqual(len(provider.calls), 1)

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
