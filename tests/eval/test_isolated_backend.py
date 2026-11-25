"""Optional engines exchange data through owned subprocesses, never shell interpolation."""
from pathlib import Path
import sys
import tempfile
import unittest
from fruitfly_eval.backends.isolated import IsolatedPython


class IsolatedBackendTests(unittest.TestCase):
    def test_real_subprocess_preserves_literal_data_and_retires_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'fixture_engine.py').write_text('''import argparse, json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--response');a=p.parse_args()
r=json.loads(Path(a.request).read_text())
Path(a.response).write_text(json.dumps({'ok':True,'result':{'payload':r['payload'],'request':a.request}}))
''')
            client = IsolatedPython(Path(sys.executable).absolute(), 'fixture_engine', (root,))
            payload = {'literal': '`touch NEVER` $(touch NEVER); "\nnext line'}
            response = client.call('fixture', payload)
            self.assertEqual(response['payload'], payload)
            self.assertFalse(Path(response['request']).exists())
            self.assertFalse((root / 'NEVER').exists())
            env = client.environment({'PYTHONHOME': 'invalid', 'PYTHONPATH': 'unowned'})
            self.assertNotIn('PYTHONHOME', env)
            self.assertEqual(env['PYTHONPATH'], str(root))

    def test_timeout_and_missing_response_are_explicit_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'empty.py').write_text('pass')
            client = IsolatedPython(Path(sys.executable).absolute(), 'empty', (root,))
            with self.assertRaisesRegex(ValueError, 'no response'):
                client.call('fixture', {})
            (root / 'slow.py').write_text('import time\ntime.sleep(30)')
            client = IsolatedPython(Path(sys.executable).absolute(), 'slow', (root,))
            with self.assertRaisesRegex(ValueError, 'timed out'):
                client.call('fixture', {}, timeout=.05)
