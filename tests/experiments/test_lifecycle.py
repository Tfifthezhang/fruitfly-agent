"""Owned stop requests do not signal arbitrary processes or replay dead work."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from fruitfly_agent.experiments.records import RunRecords
from fruitfly_agent.experiments.menu import select_operation


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.records = RunRecords(self.root)

    def test_menu_check_and_exit_are_only_selection(self):
        values = iter(('2', '1'))
        self.assertEqual(select_operation(read=lambda prompt: next(values), write=lambda text: None), ('improvement', 'check'))
        self.assertIsNone(select_operation(read=lambda prompt: '', write=lambda text: None))

    def test_stop_targets_only_the_live_owner_and_cleanup_is_not_assumed(self):
        record = self.records.create('improvement', {})
        other = self.records.create('improvement', {})
        notified = threading.Event()
        with patch('fruitfly_agent.experiments.records.os.kill', side_effect=lambda pid, signum: notified.set()) as kill:
            with self.records.owner(record):
                self.assertEqual(self.records.stop(record['id'])['state'], 'stop_requested')
                self.assertTrue(notified.wait(2))
                self.assertEqual(kill.call_args.args[0], os.getpid())
                self.assertFalse((self.records.directory(other['id']) / 'stop.request').exists())
        self.assertEqual(self.records.read(record['id'])['status'], 'completed')

    def test_failed_and_interrupted_records_are_not_treated_as_running(self):
        record = self.records.create('rsi', {})
        self.assertEqual(self.records.stop(record['id'])['state'], 'interrupted')
        with self.assertRaisesRegex(ValueError, 'failure'):
            with self.records.owner(record):
                raise ValueError('failure')
        self.assertEqual(self.records.read(record['id'])['status'], 'failed')

    def test_escaping_ids_and_symlink_records_are_rejected(self):
        for run_id in ('../other', '.', '/tmp/other'):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                self.records.read(run_id)
        record = self.records.create('eval', {})
        path = self.records.directory(record['id']) / 'record.json'
        path.unlink()
        path.symlink_to(self.root / 'outside.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.records.read(record['id'])
