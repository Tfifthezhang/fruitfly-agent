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
from fruitfly_agent.lab.optimization.text_optimizer import SearchPreview, TextProposal, TEXT_OPTIMIZER_COMPONENT
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.materials import _write_models, _write_cases
from tests.support.faux_provider import FauxProvider
from tests.support.optimizers import QueueEditor, OfflineOptimizer, custom_definition, offline_factory








class DecouplingTests(unittest.IsolatedAsyncioTestCase):
    factory = staticmethod(offline_factory)

    async def test_two_algorithms_two_targets_use_same_terminal_and_recover(self):
        for algorithm in ('offline-search', 'opro',):
            for target in ('base_prompt', 'skill-catalog.guidance'):
                with self.subTest(algorithm=algorithm, target=target), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    factory = self.factory(root, algorithm, target)
                    choices = next(group for group in factory.configuration.snapshot().selection_groups
                                   if group.group_id == 'text-optimizer')
                    self.assertEqual(set(choices.option_ids), {'opro', 'offline-search'})
                    self.assertEqual(choices.selected_id, algorithm)
                    app = AgentApplication(factory)
                    await app.start()
                    if algorithm in ('opro',):
                        provider = factory._current_runtime_config.provider
                        for text in ('wrong', 'wrong', '["Improved target"]', 'A', 'B', '["Improved target"]'):
                            provider.respond_text(text)
                    editor = QueueEditor()
                    output = io.StringIO()
                    frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor)
                    async def drive():
                        editor.send('/optimize improve', '1', *(("1",) if algorithm in ('opro',) else ()), '1')
                        for _ in range(100):
                            if app._optimization_task is not None:
                                break
                            await asyncio.sleep(.001)
                        await app.wait_for_optimization()
                        self.assertIsNone(app.last_error)
                        candidate = app.candidates()[0]
                        editor.send('/optimize', '2', '1', 'up', 'up', 'up', '1', '1', '/exit')
                        return candidate
                    ui = asyncio.create_task(frontend.run())
                    candidate = await drive()
                    self.assertEqual(await ui, 0)
                    self.assertEqual(factory.candidate_store.read(candidate.candidate_id).status, 'adopted')
                    snapshot = factory._current_targets[target].snapshot()
                    self.assertEqual(snapshot.content_hash, candidate.artifact_id)
                    provider = factory._current_runtime_config.provider
                    provider.respond_text('done')
                    await app.submit('continue')
                    self.assertIn(snapshot.text, provider.calls[0]['system_prompt'])
                    path = Path(app.status.session_path)
                    await app.close()
                    restored = AgentApplication(factory)
                    await restored.start(resume=True, session_path=path)
                    self.assertEqual(factory._current_targets[target].snapshot().content_hash, candidate.artifact_id)
                    await restored.close()

    async def test_rejecting_confirmation_never_invokes_custom_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self.factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            editor = QueueEditor()
            editor.send('/optimize improve', '1', '', '/exit')
            output = io.StringIO()
            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor).run()
            self.assertEqual(factory._current_optimizer.calls, 0)
            self.assertEqual(app.candidates(), ())
            await app.close()

    async def test_failed_candidate_start_keeps_active_runtime_and_closes_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self.factory(Path(tmp))
            app = AgentApplication(factory)
            await app.start()
            candidate_record = (await app.optimize('improve'))[0]
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
            candidate = (await app.optimize('improve'))[0]
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
                self.assertEqual(factory._current_targets['base_prompt'].snapshot().content_hash,
                                 candidate.artifact_id)
            finally:
                await restarted.close()

    async def test_terminal_cancel_status_and_exit_during_optimization(self):
        started = asyncio.Event()
        cleaned = asyncio.Event()
        class Slow(OfflineOptimizer):
            async def search(self, text, direction, *, parent_manifest, task=None):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
        with tempfile.TemporaryDirectory() as tmp:
            factory = self.factory(Path(tmp), definition=custom_definition(Slow))
            app = AgentApplication(factory)
            await app.start()
            editor = QueueEditor()
            output = io.StringIO()
            frontend = TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=editor)
            editor.send('/optimize improve', '1', '1')
            task = asyncio.create_task(frontend.run())
            await started.wait()
            editor.send('/status', 'ordinary message', '/cancel', '/exit')
            await task
            await app.close()
            self.assertTrue(cleaned.is_set())
            self.assertEqual(app.candidates() if app.state.value != 'closed' else factory.candidates(), ())
            self.assertIn('state: optimizing', output.getvalue())
            self.assertIn('cannot submit', output.getvalue())
            self.assertIn('cancellation requested', output.getvalue())

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
