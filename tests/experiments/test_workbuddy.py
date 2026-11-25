"""WorkBuddy initialization consumes backend-owned templates without model access."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from fruitfly_agent.experiments.scaffolding import initialize_workspace
from fruitfly_eval.benchmarks.workbuddy import WorkBuddyCodeAdapter
from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.workbuddy.configuration import RunnerSettings


class WorkBuddyWorkspaceTests(unittest.TestCase):
    def test_init_writes_backend_references_and_generic_collection_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(WorkBuddyCodeAdapter, 'preflight', side_effect=AssertionError('preflight')), \
                 patch('fruitfly_agent.providers.registry.ProviderRegistry.create', side_effect=AssertionError('model')):
                initialize_workspace(root, source='task-set', benchmark='workbuddy-code')
            state = root / '.fruitfly'
            main = yaml.safe_load((state / 'experiment.yaml').read_text())
            self.assertEqual(main['stages']['execute']['tasks']['file'], 'tasks/benchmark.yaml')
            request = json.loads((state / 'eval-request.json').read_text())
            self.assertEqual(request['benchmark']['id'], 'workbuddy-code')
            self.assertEqual(request['benchmark']['variant'], 'smoke')
            variables = {'FRUITFLY_EVAL_PYTHON_ROOT': '/runtime/python',
                         'FRUITFLY_EVAL_VENV': '/runtime/agent', 'WORKBUDDY_DATASET_ROOT': '/datasets/wb-code'}
            with patch.dict('os.environ', variables):
                host = HostConfig.read(root)
            self.assertEqual(host.task_directory, Path('/datasets/wb-code'))
            self.assertEqual(host.backend_file, state / 'workbuddy-runner.yaml')
            runner = RunnerSettings.read(host.backend_file)
            with self.assertRaisesRegex(ValueError, 'missing'):
                runner.validate()
            self.assertNotIn('generic', (state / 'models.yaml').read_text())
