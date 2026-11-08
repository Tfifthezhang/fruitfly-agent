"""Activities resume by their own dependencies, never by benchmark quality."""
from dataclasses import asdict
import tempfile
import unittest
from fruitfly_agent.improvement.contracts.activities import ActivitySpec, ActivityResult
from fruitfly_agent.improvement.contracts.research import ResearchRevision
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.stages.controller import ResearchController
from fruitfly_agent.run.storage.research import ResearchStore
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts


class ResearchRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfirmed_cleanup_keeps_intent_unresolved_and_prevents_implicit_replay(self):
        from fruitfly_agent.improvement.contracts.activities import UnresolvedActivity
        with tempfile.TemporaryDirectory() as directory:
            store, artifacts = ResearchStore(directory, 'research'), MemoryArtifacts()
            calls = []
            async def work(spec):
                calls.append(spec.identity)
                raise UnresolvedActivity('external retirement is not confirmed')
            controller = ResearchController(store, artifacts, {('execute', 'external'): work})
            spec = ActivitySpec('execute', 'external')
            with store.owner():
                controller.revise(ResearchRevision())
                with self.assertRaises(UnresolvedActivity):
                    await controller.perform(spec)
                self.assertEqual(len(controller.state().unresolved), 1)
                with self.assertRaisesRegex(ValueError, 'unresolved'):
                    await controller.perform(spec, fresh=True)
            self.assertEqual(len(calls), 1)

    async def test_revisions_reuse_outputs_missing_quality_and_explicit_fresh_trials(self):
        with tempfile.TemporaryDirectory() as directory:
            store, artifacts, calls = ResearchStore(directory, 'research'), MemoryArtifacts(), []
            async def work(spec):
                calls.append(spec.identity)
                return ActivityResult((Resource('out.txt', artifacts.put(b'original')),), 'unavailable')
            controller = ResearchController(store, artifacts, {('assess', 'fixture'): work})
            spec = ActivitySpec('assess', 'fixture')
            with store.owner():
                revision = controller.revise(ResearchRevision({'editor': 'first'}))
                before = await controller.perform(spec)
                controller.revise(ResearchRevision({'editor': 'changed'}, revision))
                after = await controller.perform(spec)
                self.assertEqual(before, after)
                self.assertEqual(len(calls), 1)
                await controller.perform(spec, fresh=True)
                self.assertEqual(len(calls), 2)
                controller.note('investigation', 'Next inspect task output spans.')
            restored = ResearchController(ResearchStore(directory, 'research'), artifacts, {})
            self.assertEqual(restored.state().notes['investigation'], 'Next inspect task output spans.')
            self.assertEqual(len(restored.state().revisions), 2)
            fork = store.fork('branch')
            self.assertEqual(fork.events(), store.events())

    async def test_lost_process_intent_is_not_automatically_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            store, artifacts = ResearchStore(directory, 'research'), MemoryArtifacts()
            controller = ResearchController(store, artifacts, {})
            spec = ActivitySpec('execute', 'external')
            with store.owner():
                controller.revise(ResearchRevision())
                store.append({'type': 'activity-started', 'data': {'attempt_id': 'lost',
                    'revision_id': controller.state().revisions[-1]['identity'],
                    'spec_identity': spec.identity, 'spec': spec.to_dict()}})
                with self.assertRaisesRegex(ValueError, 'unresolved'):
                    await controller.perform(spec)
            self.assertEqual(controller.state().unresolved, ('lost',))

    async def test_journal_tampering_and_unowned_writes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(directory, 'research')
            with self.assertRaises(ValueError):
                store.append({'type': 'note', 'data': {'key': 'x', 'text': 'y'}})
            with store.owner():
                ResearchController(store, MemoryArtifacts(), {}).revise(ResearchRevision({'purpose': 'original'}))
            path = store.directory / 'research-events.jsonl'
            path.write_text(path.read_text().replace('original', 'tampered'))
            with self.assertRaisesRegex(ValueError, 'integrity'):
                store.events()

    async def test_abandoned_owner_file_does_not_block_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(directory, 'research')
            store.directory.mkdir(parents=True)
            (store.directory / '.research-owner').write_text('{"pid":99999999}')
            with store.owner():
                ResearchController(store, MemoryArtifacts(), {}).revise(ResearchRevision({'recovered': True}))
            self.assertEqual(len(store.events()), 1)
