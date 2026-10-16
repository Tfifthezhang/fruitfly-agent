"""Version scopes, snapshot isolation and learning-evidence boundaries."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.lab.algorithms.targets import SystemVersion, StateSnapshot, SnapshotFile, TargetChange, VersionCandidate, TargetRegistry, content_hash
from fruitfly_agent.lab.improvement.experiments import TaskReference, TaskRunEvidence, EvidenceArtifact, ExperimentTasks
from fruitfly_agent.lab.improvement.failure_processing.projection import EvidenceProjection
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.snapshots import SnapshotStore


class ExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.parent = SystemVersion(*(content_hash(v) for v in ('H', 'I', 'S')))
        self.task = TaskReference('data', 'task', 'revision', content_hash('material'), 'Complete task', 'verifier', 'environment')

    def test_version_roundtrip_and_declared_axes(self):
        new = replace(self.parent, harness=content_hash('H2'))
        change = TargetChange('H', 'workflow', 'workflow-v1', content_hash('a'), content_hash('b'))
        candidate = VersionCandidate(self.parent, new, (change,))
        self.assertEqual(VersionCandidate.from_dict(candidate.to_dict()), candidate)
        with self.assertRaisesRegex(ValueError, 'scope'):
            VersionCandidate(self.parent, replace(new, improver=content_hash('I2')), (change,))
        with self.assertRaisesRegex(ValueError, 'scope'):
            VersionCandidate(self.parent, self.parent, (change,))
        with self.assertRaises(ValueError):
            SystemVersion('mutable', self.parent.improver, self.parent.state)

    def test_registry_rejects_unknown_workflow_strategy_and_state_targets(self):
        for role, field in [('H', 'harness'), ('I', 'improver'), ('S', 'state')]:
            candidate = VersionCandidate(self.parent, replace(self.parent, **{field: content_hash('new')}),
                (TargetChange(role, 'unknown', 'code-v1', content_hash('a'), content_hash('b')),))
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                TargetRegistry().validate(candidate, self.parent)
        candidate = VersionCandidate(self.parent, replace(self.parent, state=content_hash('new')),
            (TargetChange('S', 'memory', 'state-v1', content_hash('a'), content_hash('b')),))
        with self.assertRaisesRegex(ValueError, 'stale'):
            TargetRegistry().validate(candidate, replace(self.parent, state=content_hash('other')))

    def test_snapshot_clones_have_independent_writes_and_verified_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            artifacts = DataArtifactStore(root/'artifacts')
            store = SnapshotStore(artifacts)
            snapshot = StateSnapshot((SnapshotFile('.fruitfly/memory/MEMORY.md', 'initial'),))
            reference = store.put(snapshot)
            a, b = store.materialize(reference, root/'a'), store.materialize(reference, root/'b')
            (a/'.fruitfly/memory/MEMORY.md').write_text('changed')
            self.assertEqual((b/'.fruitfly/memory/MEMORY.md').read_text(), 'initial')
            self.assertEqual(store.read(reference), snapshot)
            (artifacts.root/reference.removeprefix('sha256:')).write_text('tampered')
            with self.assertRaises(ValueError):
                store.read(reference)
        for path in ('../x', '/tmp/x', 'a/../b', 'a\\b'):
            with self.assertRaises(ValueError):
                SnapshotFile(path, '')

    def test_missing_scores_and_overlapping_partitions_are_rejected(self):
        with self.assertRaises(ValueError):
            TaskRunEvidence('run', self.task, 'error', 0)
        with self.assertRaises(ValueError):
            TaskRunEvidence('run', self.task, 'scored', True)
        with self.assertRaises(ValueError):
            ExperimentTasks((self.task,), (self.task,), (self.task,))
        other = replace(self.task, task_id='other')
        with self.assertRaises(ValueError):
            ExperimentTasks((self.task,), (other,), (replace(other, task_id='third'),))

    def test_projection_uses_only_authorized_training_and_canonical_messages(self):
        evidence = TaskRunEvidence('run', self.task, 'scored', 0, artifacts=(
            EvidenceArtifact('trajectory', 'session.jsonl', content_hash('trajectory')),))
        text = '\n'.join(json.dumps(row) for row in [
            {'type': 'meta', 'secrets': 'excluded'},
            *({'type': 'message', 'message': {'role': 'assistant', 'content': str(i)}} for i in range(9))])
        projection = EvidenceProjection()
        result = json.loads(projection.project(evidence, authorized={self.task.reference_id}, load_artifact=lambda _: text))
        self.assertEqual(result['trajectory_total_messages'], 9)
        self.assertEqual(len(result['trajectory_excerpt']), 6)
        self.assertNotIn('excluded', repr(result))
        self.assertEqual(result['source_task']['instruction'], self.task.instruction)
        with self.assertRaises(ValueError):
            projection.project(evidence, authorized=set(), load_artifact=lambda _: self.fail('must not read holdout'))
        with self.assertRaises(ValueError):
            projection.project(replace(evidence, status='unscored', score=None), authorized={self.task.reference_id}, load_artifact=lambda _: '')
