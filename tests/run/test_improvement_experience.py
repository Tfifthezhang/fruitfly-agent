"""Experience updates and binary evidence have immutable, recoverable identities."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.lab.improvement.api import ComponentDocument, ComponentFile, HarnessSnapshot, ExperienceEntry, experience_id
from fruitfly_agent.run.storage.experience import ExperienceStore
from fruitfly_agent.run.storage.artifacts import DataArtifactStore


class ExperienceStoreTests(unittest.TestCase):
    def entry(self):
        harness = HarnessSnapshot((ComponentDocument('prompt', 'system-prompt', 'H', 'text-v1',
            (ComponentFile('instructions.txt', 'Check the result'),)),))
        return ExperienceEntry('entry', 'task', 'File deliverable', 'Read it back', ('before', 'after'), harness)

    def test_optimistic_commit_is_idempotent_and_enters_state_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = ExperienceStore(root / 'experience.json')
            empty = store.freeze()
            initial = experience_id(store.snapshot())
            entry = self.entry()
            new = store.commit((entry,), expected_snapshot=initial)
            self.assertNotEqual(empty.snapshot_id, store.freeze().snapshot_id)
            self.assertIn('Read it back', store.freeze().files[0].content)
            self.assertEqual(store.commit((entry,), expected_snapshot=new), new)
            with self.assertRaisesRegex(ValueError, 'changed'):
                store.commit((), expected_snapshot=initial)
            with self.assertRaisesRegex(ValueError, 'different contents'):
                store.commit((replace(entry, lesson='Different'),), expected_snapshot=new)
            self.assertEqual(store.snapshot(), (entry,))

    def test_symlink_store_and_binary_artifact_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            artifacts = DataArtifactStore(root / 'artifacts')
            resource = artifacts.put_bytes(b'\x00\xffbinary')
            self.assertEqual(artifacts.read_bytes(resource.artifact_id), b'\x00\xffbinary')
            (artifacts.root / resource.artifact_id.removeprefix('sha256:')).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                artifacts.read_bytes(resource.artifact_id)
            real = root / 'real'
            real.mkdir()
            (root / 'linked').symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                ExperienceStore(root / 'linked/experience.json').snapshot()
