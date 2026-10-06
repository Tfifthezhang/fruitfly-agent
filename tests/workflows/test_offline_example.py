"""The published extension example runs through the real host, without keys."""
import os
import subprocess
import sys
import unittest

from tests.architecture.checks import ROOT


class OfflineExampleTests(unittest.TestCase):
    def test_documented_example_is_executable_without_real_credentials(self):
        environment = {key: value for key, value in os.environ.items()
                       if not key.endswith('_API_KEY') and not key.startswith('FRUITFLY_')}
        completed = subprocess.run(
            [sys.executable, '-m', 'examples.extensions.offline_guidance'],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual('Offline response: example-guidance is active.', completed.stdout.strip())
