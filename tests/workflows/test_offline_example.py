"""The published extension example runs through the real host, without keys."""
import os
from pathlib import Path
import runpy
import tempfile
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

    def test_installed_check_model_wizard_uses_current_public_input_flow(self):
        example = runpy.run_path(str(ROOT / 'examples/packaging/check_installed.py'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example['check_model_setup'](root)
            from fruitfly_agent.providers.registry import load_model_specs
            models = load_model_specs(root / '.fruitfly/models.yaml')
            self.assertEqual({'wheel-check'}, set(models))
            self.assertEqual('offline-model', models['wheel-check'].model)
