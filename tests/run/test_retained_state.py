"""Atomic retained commits, source counters and recovery semantics."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.retained_state import RetainedStateStore


class RetainedStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.artifacts = DataArtifactStore(self.root / '.fruitfly/artifacts')
        self.store = RetainedStateStore(self.root / '.fruitfly/retained/project', self.artifacts)

    def test_read_only_discovery_creates_nothing(self):
        self.assertEqual({}, self.store.read()['libraries'])
        self.assertFalse(self.store.root.exists())

    def test_empty_success_and_invalid_response_preserve_old_content(self):
        first = self.store.begin('extract', 'request-a')
        self.store.finish(first, status='completed', key='memory-library', text='[]')
        self.store.review(first, 'commit')
        previous = self.store.read()
        second = self.store.begin('consolidate', 'request-b')
        self.store.finish(second, status='completed')
        self.assertEqual(previous['libraries'], self.store.read()['libraries'])

    def test_review_is_idempotence_guarded_and_parent_conflicts_are_explicit(self):
        first = self.store.begin('extract', 'request-a')
        self.store.finish(first, status='completed', key='memory-library', text='[]')
        self.assertIsNone(self.store.library('memory-library'))
        self.store.review(first, 'commit')
        self.assertEqual('[]', self.store.library('memory-library'))
        with self.assertRaisesRegex(ValueError, 'not pending'):
            self.store.review(first, 'commit')

    def test_failed_atomic_replace_keeps_confirmed_checkpoint(self):
        first = self.store.begin('extract', 'request-a')
        previous = self.store.read()
        with patch('fruitfly_agent.run.storage.retained_state.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.store.finish(first, status='completed', key='memory-library', text='[]')
        self.assertEqual(previous, self.store.read())

    def test_unknown_requests_are_not_replayed_and_recovery_does_not_advance(self):
        first = self.store.begin('extract', 'same-request')
        self.store.finish(first, status='unknown')
        restored = RetainedStateStore(self.store.root, self.artifacts)
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            restored.begin('extract', 'same-request')
        self.assertEqual(0, restored.read()['processed'])
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            restored.begin('extract', 'different-request-after-new-input')
        self.assertEqual('retry-authorized', restored.allow_retry(first))
        next_operation = restored.begin('extract', 'same-request')
        restored.finish(next_operation, status='failed')

    def test_duplicate_source_observation_counts_once(self):
        row = {'identity': 'a:1', 'session_id': 'a', 'message_id': '1',
            'artifact': self.artifacts.put_text('hello').artifact_id, 'chars': 5, 'completed': True}
        self.store.observe([row]); self.store.observe([row])
        self.assertEqual(1, len(self.store.read()['evidence']))

    def test_activation_failure_rolls_back_review_and_adoption(self):
        update = self.store.begin('extract', 'proposal')
        self.store.finish(update, status='completed', key='memory-library', text='[]')
        previous = self.store.read()
        def fail():
            raise RuntimeError('activation failed')
        with self.assertRaisesRegex(RuntimeError, 'activation failed'):
            self.store.review_with_activation(update, 'commit', fail)
        self.assertEqual(previous, self.store.read())
        with self.assertRaisesRegex(RuntimeError, 'activation failed'):
            self.store.adopt_with_activation({'memory-library': '[]'}, previous['libraries'], fail)
        self.assertEqual(previous, self.store.read())

    def test_corrupt_evidence_and_impossible_progress_fail_before_publication(self):
        row = {'identity': 'session:1', 'session_id': 'session', 'message_id': '1',
            'artifact': self.artifacts.put_text('hello').artifact_id, 'chars': 5, 'completed': True}
        self.store.observe([row])
        operation = self.store.begin('extract', 'proposal')
        previous = self.store.read()
        with self.assertRaisesRegex(ValueError, 'progress'):
            self.store.finish(operation, status='completed', processed=2)
        self.assertEqual(previous, self.store.read())
        (self.artifacts.root / row['artifact'][7:]).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.store.read()
