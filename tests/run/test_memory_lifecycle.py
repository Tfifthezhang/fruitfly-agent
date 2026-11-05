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
        for key in ('memory-extractor', 'memory-consolidator', 'memory-maintenance'):
            factory.configuration.set_mechanism(key, enabled=True)
        factory.configuration.set_parameter('memory-maintenance', 'extract_after_user_chars', '1')
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
        from fruitfly_agent.lab.context_manager.augmentation.information.file_memory.methods.threshold_maintenance.algorithm import ThresholdMaintenance
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

    async def test_verified_skill_candidate_changes_only_s_and_recovers_exact_resources(self):
        from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
        from fruitfly_agent.lab.improvement.api import WorkflowBindings
        from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
        from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
        from fruitfly_agent.improvement.contracts.components import HarnessSnapshot
        from fruitfly_agent.improvement.contracts.editing import ProposalResult
        from tests.support.configuration import component_parameters, with_component_parameters
        from tests.support.improvers import FirstSelector, SyntheticVerification
        from tests.support.model_evaluation import RoleProvider
        from tests.support.task_execution import TaskApplicationFixture
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write_catalog(root / '.fruitfly/models.yaml', {'offline': 'fake'})
        class Generator:
            generator_id = 'library-fixture'
            required_capabilities = frozenset()
            async def propose(self, request, services):
                document = request.baseline.component('skill-library')
                parameters = component_parameters(document)
                entries = json.loads(parameters['content']['documents'])
                entries[0]['description'] = 'Use this skill when the RETAINED_CANDIDATE marker applies.'
                entries[0]['body'] = 'CANDIDATE RESOURCE BODY'
                parameters['content']['documents'] = json.dumps(entries)
                changed = with_component_parameters(document, parameters)
                harness = HarnessSnapshot(tuple(changed if c.component_id == 'skill-library' else c
                    for c in request.baseline.components))
                return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness,
                    self.generator_id, (EditReason('skill-library', 'Exercise retained content.',
                        (request.records[0].run_id,), expected_effect='Candidate descriptions and resources load.'),)),))
        generators = GeneratorRegistry(); generators.register(Generator.generator_id, Generator)
        provider = RoleProvider(); provider.respond_text('reference'); provider.respond_text('candidate')
        registry = Mock(); registry.create.return_value = provider
        bindings = WorkflowBindings(generators=generators, selector=lambda *args: FirstSelector(),
            verifier=SyntheticVerification())
        factory = TaskApplicationFixture(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry,
            improvement_bindings=bindings)
        factory.configuration.save(); factory.reload_configuration()
        app = AgentApplication(factory); self.addAsyncCleanup(app.close); await app.start()
        parent = factory.system_version()
        request = WorkflowRequest('Review a coding change.', component_ids=('skill-library',),
            generator_id=Generator.generator_id, scope='persistent', retain_experience=False)
        candidates = await app.improve('', preview_token=app.workflow_preview(request).preview_token)
        self.assertEqual(1, len(candidates))
        version = factory._versions.versions.read_candidate(dict(candidates[0].evidence)['Version candidate']).version
        self.assertEqual((parent.harness, parent.improver), (version.harness, version.improver))
        self.assertNotEqual(parent.state, version.state)
        self.assertTrue(any('RETAINED_CANDIDATE' in call['system_prompt'] for call in provider.calls))
        await app.adopt_candidate(candidates[0].candidate_id)
        self.assertEqual(version, factory.system_version())
        self.assertEqual('CANDIDATE RESOURCE BODY', app.retained_state('skill')['entries'][0]['body'])
        await app.close()
        fresh_factory = TaskApplicationFixture(cwd=root, environment={'FRUITFLY_MODEL_PROFILE': 'offline'}, provider_registry=registry,
            improvement_bindings=bindings)
        fresh = AgentApplication(fresh_factory); self.addAsyncCleanup(fresh.close); await fresh.start()
        self.assertEqual(version, fresh_factory.system_version())
        self.assertEqual('CANDIDATE RESOURCE BODY', fresh.retained_state('skill')['entries'][0]['body'])

    async def test_instruction_parameter_identity_changes_only_i(self):
        from fruitfly_agent.lab.catalog import bind_component_changes
        from fruitfly_agent.improvement.contracts.components import ComponentBinding
        from fruitfly_agent.improvement.contracts.versions import canonical_json
        _, factory, app, _, _ = await self.fixture()
        parent = factory.system_version()
        target = factory._current_targets['memory-extractor']
        parameters = json.loads(target.snapshot().text)
        parameters['instructions']['prompt'] = 'CANDIDATE INSTRUCTIONS'
        text = canonical_json(parameters)
        version = factory._versions.text_candidate(parent, target.snapshot(), text).version
        profile = bind_component_changes(factory._active_profile, (ComponentBinding('memory-extractor',
            'configuration', 'component.memory-extractor', target.export_text(text)),))
        candidate = await factory._prepare_profile(profile)
        try:
            self.assertEqual(version, factory._versions.freeze(manifest=candidate.manifest))
            worker = candidate.components['maintenance-workers'][0]
            self.assertEqual('CANDIDATE INSTRUCTIONS', worker.extraction)
            self.assertEqual((parent.harness, parent.state), (version.harness, version.state))
            self.assertNotEqual(parent.improver, version.improver)
        finally:
            await candidate.close()
