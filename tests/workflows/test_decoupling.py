"""Public-contract substitution through the real terminal and runtime lifecycle."""
import asyncio
from dataclasses import replace
import io
from pathlib import Path
from queue import Queue
import tempfile
import unittest
from unittest.mock import Mock, patch

from fruitfly_agent.interactive import AgentApplication, TerminalFrontend
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismDefinition, MechanismDescriptor, MechanismContribution, ParameterDescriptor, MechanismSelection
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models, _write_cases
from tests.support.faux_provider import FauxProvider
from tests.support.improvers import offline_factory, improve








class DecouplingTests(unittest.IsolatedAsyncioTestCase):
    factory = staticmethod(offline_factory)



    async def test_failed_candidate_start_keeps_active_runtime_and_closes_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self.factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            candidate_record = (await improve(app, factory))[0]
            previous = app._handle
            old_manifest = app.runtime_manifest
            closed = []

            class BrokenCandidate:
                session = previous.session
                manifest = {'digest': 'candidate'}
                activate_callback = None
                async def start(self):
                    raise RuntimeError('candidate startup failed')
                async def close(self):
                    closed.append(True)

            async def prepare(manifest, candidate_id):
                self.assertEqual(candidate_id, candidate_record.candidate_id)
                return BrokenCandidate()

            factory.prepare_candidate = prepare
            with self.assertRaisesRegex(RuntimeError, 'candidate startup failed'):
                await app.adopt_candidate(candidate_record.candidate_id)
            self.assertIs(app._handle, previous)
            self.assertEqual(app.runtime_manifest, old_manifest)
            self.assertEqual(app.state.value, 'idle')
            self.assertEqual(closed, [True])
            await app.close()

    async def test_partial_candidate_commit_is_reconciled_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            factory = self.factory(root)
            app = AgentApplication(factory)
            await app.start()
            candidate = (await improve(app, factory))[0]
            original_update = factory.candidate_store.update

            def fail_final_commit(candidate_id, **changes):
                if changes.get('status') == 'adopted':
                    raise OSError('simulated inbox write failure')
                return original_update(candidate_id, **changes)

            factory.candidate_store.update = fail_final_commit
            with self.assertRaisesRegex(OSError, 'inbox write failure'):
                await app.adopt_candidate(candidate.candidate_id)
            self.assertEqual(factory.candidate_store.read(candidate.candidate_id).status,
                             'selected_for_next_session')
            self.assertNotEqual(factory._current_targets['base_prompt'].snapshot().content_hash,
                                candidate.artifact_id)
            factory.candidate_store.update = original_update
            await app.close()

            factory.reload_configuration()
            restarted = AgentApplication(factory)
            await restarted.start()
            try:
                record = factory.candidate_store.read(candidate.candidate_id)
                self.assertEqual(record.status, 'adopted')
                self.assertEqual(record.activated_manifest_digest, restarted.runtime_manifest['digest'])
                self.assertEqual(factory._current_targets['component-bundle'].snapshot().content_hash,
                                 candidate.artifact_id)
            finally:
                await restarted.close()


    async def test_rebuild_start_failure_preserves_active_handle_and_factory(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self.factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            previous = app.runtime_manifest
            original = factory.open
            class Broken:
                def start(self):
                    raise RuntimeError('candidate start failed')
                def close(self):
                    pass
            async def fail(**kwargs):
                handle = await original(**kwargs)
                handle.components = {**handle.components, 'broken': Broken()}
                return handle
            with patch.object(factory, 'open', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'candidate start failed'):
                    await app.rebuild()
            self.assertEqual(app.runtime_manifest, previous)
            self.assertEqual(factory._current_runtime_manifest.digest, previous['digest'])
            factory._current_runtime_config.provider.respond_text('still usable')
            self.assertFalse((await app.submit('continue')).is_error)
            await app.close()

    async def test_activation_rejected_during_run_keeps_running_state_and_closes_candidate(self):
        from fruitfly_agent.interactive import InteractiveSession, RuntimeHandle, ApplicationState
        from fruitfly_agent.core.config import AgentLoopConfig
        from fruitfly_agent.core.data_model import AgentLoopResult
        from tests.support import application as fixtures
        started = asyncio.Event()
        retired = []
        async def run(config, messages, *, signal, context_pipeline):
            started.set()
            await signal.wait()
            return AgentLoopResult(messages=list(messages), stop_reason='aborted', model='offline')
        session = InteractiveSession(AgentLoopConfig(provider=FauxProvider(), model='offline'), run_loop=run)
        app = AgentApplication(fixtures._Factory([session]))
        await app.start()
        candidate = RuntimeHandle(InteractiveSession(AgentLoopConfig(provider=FauxProvider(), model='candidate')), {}, close_callback=lambda: retired.append('candidate'))
        task = asyncio.create_task(app.submit('run'))
        await started.wait()
        with self.assertRaisesRegex(RuntimeError, 'finish active work'):
            await app.activate_runtime(candidate, expected_manifest_digest=app.runtime_manifest['digest'])
        self.assertEqual(app.state, ApplicationState.RUNNING)
        self.assertEqual(retired, ['candidate'])
        app.cancel()
        await task
        await app.close()
