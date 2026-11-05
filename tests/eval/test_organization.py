"""Automatic and independent archive organization share real evidence layers."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from fruitfly_eval.__main__ import main
from fruitfly_eval.organization import organize_run


class OrganizationTests(unittest.TestCase):
    def test_cli_retains_originals_and_portable_export_survives_archive_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            trial = root / 'artifacts/harbor/job/trial'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            raw = json.dumps({'type': 'message', 'message': {'role': 'assistant',
                'stopReason': 'stop', 'content': [{'type': 'text', 'text': 'done\u0085ok'}]}}, ensure_ascii=False) + '\n'
            (agent / 'session.jsonl').write_text(raw)
            (agent / 'events.jsonl').write_text('{"type":"run_finished"}\n')
            (trial / 'result.json').write_text('{}')
            private = trial / 'verifier'; private.mkdir(); (private / 'answer').write_text('PRIVATE')
            output = Path(directory) / 'export'
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(['organize', '--run', str(root), '--output', str(output), '--portable']), 0)
            first = json.loads(stdout.getvalue())
            second = organize_run(root, output=output, portable=True)
            self.assertEqual(first, second)
            self.assertEqual((agent / 'session.jsonl').read_text(), raw)
            item = second['trials'][0]
            overview = json.loads((output / item['directory'] / 'overview.json').read_text())
            self.assertEqual(overview['output_excerpt'], 'done\u0085ok')
            self.assertFalse(overview['complete'])
            shutil.rmtree(root)
            sources = json.loads((output / item['directory'] / 'sources.json').read_text())['sources']
            for source in sources:
                data = (output / source['location']).read_bytes()
                self.assertEqual('sha256:' + hashlib.sha256(data).hexdigest(), source['artifact_id'])
                self.assertNotIn(b'PRIVATE', data)

    def test_pre_session_failure_remains_a_trial_and_active_runs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/startup'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            (trial / 'result.json').write_text('{"exception_info":{"exception_type":"SetupError"}}')
            result = organize_run(root)
            self.assertEqual(len(result['trials']), 1)
            self.assertEqual(result['trials'][0]['status'], 'partial')
            control = root / 'artifacts/harbor/control.json'; control.write_text('{"state":"running"}')
            with self.assertRaisesRegex(ValueError, 'retirement'):
                organize_run(root)
