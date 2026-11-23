"""Production host stages, atomically activates and restores retained S offline."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.runtime.maintenance import RetainedRuntimeService
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.retained_state import RetainedStateStore
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog


class MemoryLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def fixture(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(root / '.fruitfly/models.yaml', {'offline': 'fake'})
        provider = FauxProvider()
        registry = Mock(); registry.create.return_value = provider
        factory = RunApplicationFactory(cwd=root, user_root=(root) / '.fruitfly-user', environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry)
        factory.configuration.set_parameter('file-memory', 'extract_after_user_chars', '1')
        factory.configuration.save()
        factory.reload_configuration()
        app = AgentApplication(factory); self.addAsyncCleanup(app.close)
        await app.start()
        return root, factory, app, provider, registry

    async def test_threshold_auto_publication_survives_a_new_application(self):
        root, factory, app, provider, registry = await self.fixture()
        self.assertEqual(1, registry.create.call_count, 'auxiliary model must be lazy')
        provider.respond_text('Understood.')
        # Evidence identity is assigned by the Session, so derive it from the
        # actual bounded maintenance request rather than guessing a position.
        from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.maintenance import ThresholdMaintenance
        original = ThresholdMaintenance.generate
        async def generate(worker, request, checkpoint, read, **kwargs):
            row = checkpoint['evidence'][0]
            provider.respond_text(json.dumps([{'operation': 'add', 'entry': {
                'kind': 'preference', 'subject': 'Editing', 'description': 'Read for editor preferences.',
                'body': 'Prefer tabs.', 'applicability': 'Editing project code.', 'supersedes': []},
                'evidence_ids': [row['identity']]}]))
            return await original(worker, request, checkpoint, read, **kwargs)
        with patch.object(ThresholdMaintenance, 'generate', generate):
            await app.submit('Prefer tabs.')
            await asyncio.wait_for(app._maintenance_task, 3)
        state = app.retained_state('memory')
        self.assertEqual([], state['entries'])
        self.assertEqual([], state['pending'])
        self.assertTrue(state['refresh_pending'])
        self.assertEqual(1, factory.retained_store.read()['processed'])
        session_path = app.status.session_path
        saved_config = factory.configuration.config_path.read_bytes()
        provider.respond_text('Understood.')
        await app.submit('Use the saved preference.')
        self.assertEqual('Prefer tabs.', app.retained_state('memory')['entries'][0]['body'])
        self.assertEqual(session_path, app.status.session_path)
        await app._maintenance_task
        self.assertEqual(saved_config, factory.configuration.config_path.read_bytes())
        await app.close()
        restored_factory = RunApplicationFactory(cwd=root, user_root=root / '.fruitfly-user',
            environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry)
        restored = AgentApplication(restored_factory)
        self.addAsyncCleanup(restored.close)
        await restored.start()
        self.assertNotEqual(session_path, restored.status.session_path)
        self.assertEqual('Prefer tabs.', restored.retained_state('memory')['entries'][0]['body'])

    async def test_manual_pending_review_rolls_back_failed_runtime_preparation(self):
        from tests.support.retained import memory
        _, factory, app, _, _ = await self.fixture()
        operation = factory.retained_store.begin('extract', 'manual-proposal')
        factory.retained_store.finish(operation, status='completed', key='memory-library',
            text=json.dumps([memory(body='Prefer tabs.')]))
        session_path = app.status.session_path
        history = Path(session_path).read_bytes()
        with patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('startup failed'))):
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                await app.retained_action(operation, 'commit')
        self.assertEqual('pending', factory.retained_store.read()['pending'][operation]['status'])
        self.assertEqual([], app.retained_state('memory')['entries'])
        self.assertEqual(history, Path(session_path).read_bytes())
        await app.retained_action(operation, 'commit')
        self.assertEqual('Prefer tabs.', app.retained_state('memory')['entries'][0]['body'])

    async def test_external_publication_refreshes_before_the_next_submission(self):
        from tests.support.retained import memory
        _, factory, app, provider, _ = await self.fixture()
        note = memory(body='Read the published preference.')
        operation = factory.retained_store.begin('extract', 'external-publication')
        factory.retained_store.finish(
            operation, status='completed', key='memory-library',
            text=json.dumps([note]),
        )
        factory.retained_store.publish(operation)
        session_path = app.status.session_path
        provider.respond_text('Understood.')
        await app.submit('hello')
        self.assertEqual(session_path, app.status.session_path)
        self.assertEqual(
            note['body'], app.retained_state('memory')['entries'][0]['body'],
        )

    def test_observation_uses_canonical_completion_and_deduplicates_across_restarts(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        store = RetainedStateStore(root / '.fruitfly/retained/test', DataArtifactStore(root / '.fruitfly/artifacts'))
        with Session(root / 'session.jsonl') as session:
            session.append('message', {'message': UserMessage('interrupted').to_dict()})
            session.append('meta', {'kind': 'runRecord', 'schema_version': 1, 'run_id': 'one', 'event': 'start', 'data': {}})
            session.append('message', {'message': UserMessage('completed').to_dict()})
            session.append('meta', {'kind': 'runRecord', 'schema_version': 1, 'run_id': 'two', 'event': 'start', 'data': {}})
            session.append('meta', {'kind': 'runRecord', 'schema_version': 1, 'run_id': 'two', 'event': 'end',
                'data': {'is_error': False, 'stop_reason': 'stop'}})
            for _ in range(2):
                service = RetainedRuntimeService(session=session, session_id='test',
                    components={'maintenance-workers': (Mock(library_id='memory-library'),)}, store=store)
                service.observe(completed=True)
            evidence = store.read()['evidence']
            self.assertEqual([False, True], [e['completed'] for e in evidence])
            self.assertEqual(len('interruptedcompleted'), sum(e['chars'] for e in evidence))


    async def test_maintenance_instruction_identity_changes_only_h(self):
        from fruitfly_agent.lab.catalog import bind_component_changes
        from fruitfly_agent.improvement.contracts.components import ComponentBinding
        from fruitfly_agent.improvement.contracts.versions import canonical_json
        _, factory, app, _, _ = await self.fixture()
        parent = factory.system_version()
        target = factory._current_targets['file-memory']
        parameters = json.loads(target.snapshot().text)
        parameters['instructions']['extraction'] = 'CANDIDATE INSTRUCTIONS'
        text = canonical_json(parameters)
        version = factory._versions.text_candidate(parent, target.snapshot(), text).version
        profile = bind_component_changes(factory._active_profile, (ComponentBinding('file-memory',
            'configuration', 'component.file-memory', target.export_text(text)),))
        candidate = await factory._prepare_profile(profile)
        try:
            self.assertEqual(version, factory._versions.freeze(manifest=candidate.manifest))
            worker = candidate.components['maintenance-workers'][0]
            self.assertEqual('CANDIDATE INSTRUCTIONS', worker.extraction)
            self.assertEqual((parent.improver, parent.state), (version.improver, version.state))
            self.assertNotEqual(parent.harness, version.harness)
        finally:
            await candidate.close()

    async def recovery_fixture(self, text='abcdef'):
        from fruitfly_agent.lab.catalog import ProviderBinding
        from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.maintenance import ThresholdMaintenance
        from fruitfly_agent.lab.context_manager.augmentation.memory.methods.file_memory.config import MaintenanceConfig
        root, factory, app, _, _ = await self.fixture()
        provider = FauxProvider()
        worker = ThresholdMaintenance(MaintenanceConfig(extract_after_user_chars=1, max_input_chars=3),
            'extract', 'consolidate', lambda: ProviderBinding(provider, 'fake', 'offline'))
        store = factory.retained_store
        store.observe([{'identity': 'source:message', 'session_id': 'source', 'message_id': 'message',
            'artifact': store.artifacts.put_text(text).artifact_id, 'chars': len(text), 'completed': True}])
        def service():
            return RetainedRuntimeService(session=None, session_id='recovery',
                components={'target': factory._current_targets['memory-library'], 'maintenance-workers': (worker,)}, store=store)
        return factory, provider, worker, service

    async def test_unknown_late_batch_reuses_received_response_after_explicit_retry(self):
        factory, provider, _, service = await self.recovery_fixture()
        provider.respond_text('[]')
        provider.respond_fatal('lost response')
        await service().run()
        store = factory.retained_store
        state = store.read()
        identity, operation = next(iter(state['operations'].items()))
        self.assertEqual('unknown', operation['status'])
        self.assertEqual(0, state['processed'])
        self.assertEqual(2, len(provider.calls))
        await service().run()
        self.assertEqual(2, len(provider.calls), 'new scheduling cannot authorize replay')
        journal = store.read_journal(operation)
        self.assertIn('response', journal['calls'][0])
        self.assertNotIn('response', journal['calls'][1])
        store.allow_retry(identity)
        provider.respond_text('[]')
        resumed = service()
        self.assertEqual('completed', await resumed.run(manual=True, operation_id=identity))
        self.assertEqual('', resumed.error)
        self.assertEqual(3, len(provider.calls), 'first batch must be reused')
        self.assertEqual(1, store.read()['processed'])
        self.assertEqual('completed', store.read()['operations'][identity]['status'])

    async def test_received_response_recovers_after_failure_to_publish_checkpoint(self):
        factory, provider, _, service = await self.recovery_fixture('abc')
        provider.respond_text('[]')
        store = factory.retained_store.user
        original = store.finish
        def fail_publication(*args, **kwargs):
            if kwargs['status'] == 'completed':
                raise OSError('checkpoint unavailable')
            return original(*args, **kwargs)
        with patch.object(store, 'finish', side_effect=fail_publication):
            await service().run()
        identity = next(iter(store.read()['operations']))
        self.assertEqual(0, store.read()['processed'])
        # A crash after durable response storage and before final commit leaves
        # the operation running. Reconstruct that persisted recovery boundary.
        store.mutate(lambda state: state['operations'][identity].update(status='running'))
        await service().run()
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(1, store.read()['processed'])

    async def test_invalid_batch_requires_retry_and_preserves_earlier_response(self):
        factory, provider, _, service = await self.recovery_fixture()
        provider.respond_text('[]')
        provider.respond_text('[{}]')
        await service().run()
        store = factory.retained_store
        identity, operation = next(iter(store.read()['operations'].items()))
        self.assertEqual('failed', operation['status'])
        self.assertEqual(0, store.read()['processed'])
        await service().run()
        self.assertEqual(2, len(provider.calls))
        store.allow_retry(identity)
        provider.respond_text('[]')
        await service().run()
        self.assertEqual(3, len(provider.calls))
        self.assertEqual(1, store.read()['processed'])

    async def test_saved_memory_survives_refresh_failure_and_chat_continues(self):
        from tests.support.retained import memory
        _, factory, app, provider, _ = await self.fixture()
        operation = factory.retained_store.begin('extract', 'publication')
        factory.retained_store.finish(operation, status='completed', key='memory-library',
            text=json.dumps([memory(body='Saved fact')]), publish=True)
        saved = factory.retained_store.read()['libraries']
        provider.respond_text('The task completed.')
        with patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('MCP startup failed'))):
            result = await app.submit('Continue with the current runtime.')
        self.assertFalse(result.is_error)
        self.assertIn('MCP startup failed', app.retained_state('memory')['refresh_error'])
        self.assertEqual(saved, factory.retained_store.read()['libraries'])
        self.assertEqual([], app.retained_state('memory')['entries'])

    async def test_two_workspaces_share_memory_and_read_body_through_resource_tool(self):
        from tests.support.retained import memory
        root, factory, app, _, registry = await self.fixture()
        note = memory(body='SHARED BODY')
        operation = factory.retained_store.begin('extract', 'publication')
        factory.retained_store.finish(operation, status='completed', key='memory-library',
            text=json.dumps([note]), publish=True)
        other = root / 'other-project'
        _write_catalog(other / '.fruitfly/models.yaml', {'offline': 'fake'})
        provider = FauxProvider()
        registry.create.return_value = provider
        second_factory = RunApplicationFactory(cwd=other, user_root=factory.user_root,
            environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry)
        second = AgentApplication(second_factory)
        self.addAsyncCleanup(second.close)
        await second.start()
        resources = second_factory._current_runtime_config.readable_resources
        provider.respond_tool_call('read', {'path': f'resource://{resources.scope}/retained-memory/{note["id"]}.md'})
        provider.respond_text('Used the shared note.')
        result = await second.submit('Use the saved preference.')
        self.assertFalse(result.is_error)
        self.assertTrue(any('SHARED BODY' in message.text for message in result.messages if message.role == 'toolResult'))
        self.assertFalse((other / '.fruitfly/retained').exists())
        self.assertEqual(factory.retained_store.user.root, second_factory.retained_store.user.root)
        self.assertEqual(root, factory.cwd)

    async def test_old_workspace_import_is_idempotent_and_preserves_unknown_operation(self):
        from tests.support.retained import memory
        root, factory, app, _, _ = await self.fixture()
        old = factory.retained_store.workspace
        evidence = {'identity': 'old:message', 'session_id': 'old', 'message_id': 'message',
            'artifact': old.artifacts.put_text('Legacy evidence').artifact_id,
            'chars': len('Legacy evidence'), 'completed': True}
        old.observe([evidence])
        note = memory()
        operation = old.begin('extract', 'completed-old')
        old.finish(operation, status='completed', key='memory-library', text=json.dumps([note]), publish=True)
        unknown = old.begin('extract', 'unknown-old')
        old.finish(unknown, status='unknown')
        before = (old.root / 'state.json').read_bytes()
        self.assertEqual('imported', await app.retained_action(str(root), 'import'))
        self.assertEqual('imported', await app.retained_action(str(root), 'import'))
        state = factory.retained_store.read()
        self.assertEqual(1, len(state['evidence']))
        self.assertEqual(0, state['processed'])
        self.assertEqual('unknown', state['operations'][unknown]['status'])
        self.assertEqual('project', json.loads(factory.retained_store.library('memory-library'))[0]['scope'])
        self.assertEqual(before, (old.root / 'state.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            factory.retained_store.begin('extract', 'new-request')

    async def test_isolated_host_never_reads_or_changes_personal_checkpoint(self):
        root, factory, _, provider, registry = await self.fixture()
        path = factory.user_root / 'memory/state.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('deliberately invalid personal state')
        isolated = RunApplicationFactory(cwd=root, user_root=factory.user_root,
            environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry,
            retained_state_enabled=False)
        app = AgentApplication(isolated)
        self.addAsyncCleanup(app.close)
        await app.start()
        provider.respond_text('Isolated task completed.')
        result = await app.submit('Execute with only declared initial state.')
        self.assertFalse(result.is_error)
        candidate = await isolated._prepare_profile(isolated._active_profile)
        await candidate.close()
        self.assertEqual('deliberately invalid personal state', path.read_text())

    async def test_revision_conflict_retains_response_and_requires_explicit_discard(self):
        from tests.support.retained import memory
        factory, provider, _, service = await self.recovery_fixture('abc')
        provider.respond_text('[]')
        store = factory.retained_store.user
        original_finish = store.finish
        changed = False
        def concurrent_publication(identity, **kwargs):
            nonlocal changed
            if kwargs['status'] == 'completed' and not changed:
                changed = True
                store.adopt_with_activation({'memory-library': json.dumps([memory()])}, {}, lambda: None)
            return original_finish(identity, **kwargs)
        with patch.object(store, 'finish', side_effect=concurrent_publication):
            await service().run()
        identity, operation = next(iter(store.read()['operations'].items()))
        self.assertEqual('failed', operation['status'])
        self.assertEqual(0, store.read()['processed'])
        self.assertIn('response', store.read_journal(operation)['calls'][0])
        await service().run()
        self.assertEqual(1, len(provider.calls))
        self.assertEqual('discarded', store.discard(identity))
        self.assertEqual('discarded', store.read()['operations'][identity]['status'])
