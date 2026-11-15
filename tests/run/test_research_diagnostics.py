"""Portable role diagnostics remain attributable without granting them to readers."""
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.improvement.contracts.activities import ActivityResult
from fruitfly_agent.run.improvement.service import ResearchService
from fruitfly_agent.run.storage.research_bundles import ResearchOutputs, ArtifactPort
from tests.support.stages import proposal_fixture


class ResearchDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_survives_publication_and_cross_study_copy_without_reader_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = ResearchOutputs(root, 'source')
            _, plan, _, _ = proposal_fixture()
            async def organize(spec):
                async with service.create_services() as services:
                    session = service.artifacts.put(b'{"message":"offline transcript"}\n')
                    services.record('research-session', session_id='session', artifact_id=session)
                    services.record('request', id='request', model='fake')
                return ActivityResult((service.put('view.json', {'resources': []}),))
            service = ResearchService(root, 'source', ArtifactPort(outputs.artifacts), plan=plan,
                journal=outputs.journal(), external_stages={'organize': organize})
            service.run_id = 'organize-fixture'
            service.revise({'stage': 'organize'})
            result = await service.perform('organize', ())
            trace = next(r for r in result.outputs if r.path == 'diagnostics/trace.json')
            manifest = service.read(trace)
            self.assertEqual('organize-fixture', manifest['run_id'])
            events = [json.loads(service.artifacts.read(r['artifact_id'])) for r in manifest['events']]
            self.assertTrue(all(e['attempt_id'] and e['activity_id'] for e in events))
            self.assertTrue(all(e['run_id'] == 'organize-fixture' for e in events))
            config = outputs.artifacts.put_bytes(b'{}').artifact_id
            bundle, path = outputs.publish('organize', service.run_id, result, (), config)
            destination = ResearchOutputs(root, 'destination')
            granted, _ = destination.inputs((str(path),), 'propose')
            self.assertNotIn('diagnostics/trace.json', {r.path for r in granted})
            session = events[0]['artifact_id']
            self.assertEqual(service.artifacts.read(session), destination.artifacts.read_bytes(session))
            self.assertIn(session, bundle.dependencies)

    async def test_failure_keeps_event_manifest_and_does_not_publish_success(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = ResearchOutputs(directory, 'failure')
            _, plan, _, _ = proposal_fixture()
            async def broken(spec):
                async with service.create_services() as services:
                    services.record('request', id='request', model='fake')
                    raise RuntimeError('offline failure')
            service = ResearchService(directory, 'failure', ArtifactPort(outputs.artifacts), plan=plan,
                journal=outputs.journal(), external_stages={'organize': broken})
            service.revise({})
            with self.assertRaisesRegex(RuntimeError, 'offline failure'):
                await service.perform('organize', ())
            self.assertTrue(service.read(service.last_diagnostics)['events'])
            self.assertEqual('failed', next(iter(service.controller.state().attempts.values()))['status'])

    def test_missing_declared_trace_event_blocks_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = ResearchOutputs(directory, 'missing')
            port = ArtifactPort(outputs.artifacts)
            trace = {'run_id': 'fixture', 'events': [{'artifact_id': 'sha256:' + '1' * 64}]}
            from fruitfly_agent.improvement.contracts.tasks import Resource
            result = ActivityResult((Resource('diagnostics/trace.json', port.put(json.dumps(trace).encode())),))
            with self.assertRaisesRegex(ValueError, 'required research artifact'):
                outputs.publish('propose', 'fixture', result, (), port.put(b'{}'))
            self.assertFalse((outputs.root / 'candidates/fixture/bundle.json').exists())
