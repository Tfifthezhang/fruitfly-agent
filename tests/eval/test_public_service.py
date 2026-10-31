"""Public Eval services retain fixed-version results and bounded record paths."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_eval.api import read_report, stop_evaluation


class PublicServiceTests(unittest.TestCase):
    def test_saved_reports_are_read_without_model_or_runtime_construction(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        directory = root / 'saved'
        directory.mkdir()
        payload = {'schema_version': 1, 'status': 'completed'}
        (directory / 'report.json').write_text(json.dumps(payload))
        (directory / 'report.md').write_text('Saved report')
        self.assertEqual(read_report('saved', output_root=root), payload)
        self.assertEqual(read_report('saved', output_root=root, as_json=False), 'Saved report')

    def test_report_and_stop_reject_escaping_ids(self):
        for operation in (read_report, stop_evaluation):
            for value in ('..', '../other', '/tmp/other'):
                with self.subTest(operation=operation, value=value), self.assertRaises(ValueError):
                    operation(value, output_root='/tmp/owned')
