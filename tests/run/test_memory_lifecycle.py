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
        factory = RunApplicationFactory(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry)
        factory.configuration.set_parameter('file-memory', 'extract_after_user_chars', '1')
        factory.configuration.save()
        factory.reload_configuration()
        app = AgentApplication(factory); self.addAsyncCleanup(app.close)
        await app.start()
        return root, factory, app, provider, registry

    async def test_threshold_candidate_requires_review_and_survives_a_new_application(self):
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
        self.assertEqual(1, len(state['pending']), state)
        self.assertEqual(1, sum(e['completed'] for e in factory.retained_store.read()['evidence']))
        identity = state['pending'][0]['id']
        session_path = app.status.session_path
        saved_config = factory.configuration.config_path.read_bytes()
        # Failed preparation must leave review status, active runtime and history intact.
        history = Path(session_path).read_bytes()
        with patch.object(RuntimeHandle, 'start', AsyncMock(side_effect=RuntimeError('startup failed'))):
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                await app.retained_action(identity, 'commit')
        self.assertEqual('pending', factory.retained_store.read()['pending'][identity]['status'])
        self.assertEqual([], app.retained_state('memory')['entries'])
        self.assertEqual(history, Path(session_path).read_bytes())
        await app.retained_action(identity, 'commit')
        self.assertEqual(session_path, app.status.session_path)
        self.assertEqual('Prefer tabs.', app.retained_state('memory')['entries'][0]['body'])
        self.assertEqual(saved_config, factory.configuration.config_path.read_bytes())
        await app.close()
        restored_factory = RunApplicationFactory(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry)
        restored = AgentApplication(restored_factory); self.addAsyncCleanup(restored.close)
        await restored.start()
        self.assertNotEqual(session_path, restored.status.session_path)
        self.assertEqual('Prefer tabs.', restored.retained_state('memory')['entries'][0]['body'])
        self.assertEqual(0, restored.retained_state('memory')['user_chars'])

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
                    components={'maintenance-workers': (object(),)}, store=store)
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
