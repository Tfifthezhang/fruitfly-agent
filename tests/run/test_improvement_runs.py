"""Run summaries preserve empty outcomes, scope, and verified journal access."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive.contracts.candidates import CandidateSection
from fruitfly_agent.interactive.contracts.improvement import ImprovementRunView
from fruitfly_agent.run.storage.improvement_runs import ImprovementRunStore


class ImprovementRunStoreTests(unittest.TestCase):
    def test_atomic_round_trip_and_configuration_profile_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = ImprovementRunStore(root)
            scope = (str(root / 'config.yaml'), 'default')
            row = ImprovementRunView('a' * 32, 'completed', 'method', 'target', direction='Improve',
                started_at='2026-01-01T00:00:00Z', stop_reason='no_improvement',
                sections=(CandidateSection('Result', 'No candidate'),))
            store.save(row, scope)
            self.assertEqual((row,), store.list(scope))
            self.assertEqual((), store.list((scope[0], 'other')))
            store.save(replace(row, status='failed', stop_reason='error'), scope)
            self.assertEqual('failed', store.list(scope)[0].status)
            self.assertEqual(1, len(tuple(store.root.iterdir())))

    def test_journal_reads_validate_identity_hash_and_owned_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = ImprovementRunStore(root)
            journal = root / '.fruitfly/improvement/searches/search.jsonl'
            journal.parent.mkdir(parents=True)
            journal.write_text('{"kind":"search-result","status":"no_improvement"}\n')
            scope = ('config', 'profile')
            row = ImprovementRunView('a' * 32, 'completed', evidence=(
                ('Search history', str(journal.relative_to(root))),
                ('Search history hash', 'sha256:' + hashlib.sha256(journal.read_bytes()).hexdigest())))
            store.save(row, scope)
            self.assertEqual(journal.read_text(), store.logs(row.run_id, scope))
            with self.assertRaisesRegex(ValueError, 'configuration/profile'):
                store.logs(row.run_id, ('other', 'profile'))
            journal.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                store.logs(row.run_id, scope)
            store.save(replace(row, evidence=(('Search history', '../outside'),)), scope)
            with self.assertRaisesRegex(ValueError, 'owned workspace'):
                store.logs(row.run_id, scope)

    def test_symlinks_invalid_records_and_identity_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = ImprovementRunStore(root)
            row = ImprovementRunView('a' * 32, 'completed')
            with self.assertRaisesRegex(ValueError, 'identity'):
                store.save(replace(row, run_id='../escape'), ('config', 'profile'))
            store.root.mkdir(parents=True)
            (store.root / (row.run_id + '.json')).symlink_to(root / 'outside')
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                store.save(row, ('config', 'profile'))
            (store.root / (row.run_id + '.json')).unlink()
            store.save(row, ('config', 'profile'))
            path = store.root / (row.run_id + '.json')
            payload = json.loads(path.read_text())
            payload['run']['evidence'] = [[1, 'invalid']]
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'evidence'):
                store.list(('config', 'profile'))
