"""Independent preparation retains source scope and rejects drift before execution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fruitfly_eval.benchmarks.harbor import harbor_descriptor
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.workbuddy.preparation import WorkBuddyPreparation
from tests.support.workbuddy import fixture, Engine


class WorkBuddyPreparationTests(unittest.TestCase):
    def test_inventory_full_prepare_and_check_use_isolated_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            host = fixture(root)
            descriptor = harbor_descriptor(benchmark_id='fixture', label='Fixture', description='Fixture',
                dataset='wb-bench-code-v1.0', version='1.0', smoke_task='first')
            request = EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
                'benchmark': {'id': 'fixture', 'variant': 'full', 'task_names': ['first']}})
            client = Engine()
            backend = WorkBuddyPreparation()
            runtime = {'id': 'runtime-fixture', 'source': str(root), 'mounts': [], 'host': host.identity()}
            with patch('fruitfly_eval.workbuddy.preparation.engine', return_value=client), \
                 patch('fruitfly_eval.workbuddy.preparation.inspect_images', return_value=[]), \
                 patch('fruitfly_eval.workbuddy.preparation.prepare_material', return_value=runtime) as material, \
                 patch('fruitfly_eval.workbuddy.preparation.prepare_dependencies', return_value={'images': {}}), \
                 patch('fruitfly_eval.workbuddy.preparation.check_material'), \
                 patch('fruitfly_eval.workbuddy.preparation.check_dependencies'), \
                 patch('fruitfly_eval.workbuddy.preparation.image_identity', return_value='sha256:fixture'):
                result = backend.prepare(request, descriptor, host, package=None, tasks_only=True, progress=None)
                self.assertEqual(result['task_count'], 1)
                material.assert_not_called()
                self.assertNotIn('probe', [op for op, _ in client.calls])
                result = backend.prepare(request, descriptor, host, package=root, tasks_only=False, progress=None)
                self.assertTrue(Path(result['receipt']).is_file())
                receipt = backend.load(host, descriptor, 'full')
                self.assertEqual([t['id'] for t in receipt['tasks']], ['first'])
                self.assertEqual(receipt['selection']['excluded'], [{'id': 'second', 'reason': 'outside explicit task_names'}])
                self.assertEqual([value['task']['id'] for op, value in client.calls if op == 'probe'], ['first'])
                self.assertTrue(backend.inspect(request, descriptor, host)['available'])
                unrestricted = EvaluationRequest.from_dict({'runtime': {'working_directory': str(root)},
                    'benchmark': {'id': 'fixture', 'variant': 'full'}})
                self.assertFalse(backend.inspect(unrestricted, descriptor, host)['available'])
                self.assertIn('probe', [op for op, _ in client.calls])
                shared = Path(receipt['dataset_material']['root']) / 'shared/verifier/plugin.py'
                shared.write_text('drift')
                self.assertFalse(backend.inspect(request, descriptor, host)['available'])
