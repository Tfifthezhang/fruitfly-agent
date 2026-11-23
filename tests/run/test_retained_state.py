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

    def test_runtime_retry_and_legacy_end_use_scoped_storage(self):
        from types import SimpleNamespace
        from fruitfly_agent.run.storage.retained_scopes import RetainedScopes
        from fruitfly_agent.run.runtime.maintenance import RetainedRuntimeService
        scopes = RetainedScopes(self.store, self.store, {'memory-library'})
        service = RetainedRuntimeService(session=None, session_id='test', store=scopes,
            components={'maintenance-workers': (SimpleNamespace(library_id='memory-library'),)})
        identity = self.store.begin('extract', 'legacy')
        self.store.finish(identity, status='unknown')
        self.assertEqual('retry-authorized', service.review(identity, 'retry'))
        self.assertEqual('retry-authorized', service.review(identity, 'retry'))
        self.assertEqual('ended', service.review(identity, 'discard'))
        self.assertEqual('discarded', self.store.read()['operations'][identity]['status'])

    def test_skills_status_excludes_memory_counters_and_errors(self):
        from types import SimpleNamespace
        from fruitfly_agent.run.runtime.maintenance import RetainedRuntimeService
        from fruitfly_agent.interactive.terminal.features.retained_state.views import render_state
        service = RetainedRuntimeService(session=None, session_id='test', components={}, store=self.store)
        service.collections['skill'] = SimpleNamespace(library_id='skills', view_entries=lambda: [])
        service.error = 'memory maintenance failed'
        state = service.describe('skill')
        self.assertNotIn('user_chars', state)
        self.assertEqual('', state['error'])
        self.assertEqual('No retained documents.\n', render_state(state, kind='skill'))

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
        self.assertEqual('retry-authorized', restored.allow_retry(first))
        next_operation = restored.begin('extract', 'same-request')
        restored.finish(next_operation, status='failed')

    def test_active_maintenance_excludes_other_workers_and_retry(self):
        peer = RetainedStateStore(self.store.root, self.artifacts)
        with self.store.maintenance_lease() as acquired:
            self.assertTrue(acquired)
            operation = self.store.begin('extract', 'active')
            with peer.maintenance_lease() as peer_acquired:
                self.assertFalse(peer_acquired)
            with self.assertRaisesRegex(ValueError, 'still running'):
                peer.allow_retry(operation)
            self.assertEqual('running', peer.read()['operations'][operation]['status'])
        self.assertEqual('retry-authorized', peer.allow_retry(operation))

    def test_legacy_batch_without_journal_can_be_ended_without_losing_evidence(self):
        operation = self.store.begin('extract', 'legacy')
        self.store.finish(operation, status='unknown')
        self.store.allow_retry(operation)
        before = self.store.read()
        self.assertEqual('ended', self.store.end_legacy_operation(operation))
        after = self.store.read()
        self.assertEqual(before['evidence'], after['evidence'])
        self.assertEqual('discarded', after['operations'][operation]['status'])
        self.assertEqual('legacy-no-journal', after['operations'][operation]['end_reason'])
        self.assertEqual('retry-authorized', before['operations'][operation]['status'])

    def test_publication_is_durable_and_rejects_duplicate_adoption(self):
        operation = self.store.begin('extract', 'publication')
        self.store.finish(operation, status='completed', key='memory-library', text='[]')
        self.store.publish(operation)
        restored = RetainedStateStore(self.store.root, self.artifacts)
        self.assertEqual('[]', restored.library('memory-library'))
        with self.assertRaisesRegex(ValueError, 'not pending'):
            restored.publish(operation)

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
