"""Dataset snapshots preserve official shared resources and exact selected scope."""
from pathlib import Path
import tempfile
import unittest

from fruitfly_eval.benchmarks.harbor import harbor_descriptor
from fruitfly_eval.workbuddy.tasks import freeze_dataset, check_dataset, inventory


def resources(row):
    return {"gpu_requirements": [], "images": [{"reference": row["configuration"]["environment"]["docker_image"]}], "builds": []}


class WorkBuddyTaskTests(unittest.TestCase):
    def test_gpu_exclusions_retain_reason_and_original_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, descriptor = self.fixture(Path(directory))
            def requirements(row):
                return {**resources(row), 'gpu_requirements': ['GPU required'] if row['id'] == 'second' else []}
            excluded = []
            rows = inventory(dataset, descriptor, 'no_gpu', inspect_resources=requirements, excluded=excluded)
            self.assertEqual([r['id'] for r in rows], ['first'])
            self.assertEqual(excluded[0]['id'], 'second')
            self.assertEqual(excluded[0]['requirements'], ['GPU required'])

    def test_official_name_must_match_directory_without_rewriting_material(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset, descriptor = self.fixture(Path(directory))
            path = dataset / 'tasks/first/task.toml'
            path.write_text(path.read_text().replace('workbuddy/first', 'workbuddy/second'))
            with self.assertRaisesRegex(ValueError, 'must match'):
                inventory(dataset, descriptor, 'full', inspect_resources=resources)

    def fixture(self, root):
        dataset = root / 'wb-code'
        dataset.mkdir()
        (dataset / 'dataset.toml').write_text('[verifier]\nengine="composite"\n')
        shared = dataset / 'shared/verifier'
        shared.mkdir(parents=True)
        (shared / 'plugin.py').write_text('# Dataset-owned official verifier\n')
        for name in ('first', 'second'):
            task = dataset / 'tasks' / name
            task.mkdir(parents=True)
            (task / 'task.toml').write_text('[task]\nname="workbuddy/' + name + '"\n[environment]\ndocker_image="fixture/code:v1"\n')
            (task / 'instruction.md').write_text('Implement ' + name)
        descriptor = harbor_descriptor(benchmark_id='fixture', label='Fixture', description='Fixture',
            version='1', dataset='fixture/code', smoke_task='first')
        return dataset, descriptor

    def test_smoke_freezes_dataset_and_shared_resources_without_changing_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, descriptor = self.fixture(root)
            original = {p.relative_to(dataset): p.read_bytes() for p in dataset.rglob('*') if p.is_file()}
            receipt = freeze_dataset(dataset, root / 'cache', descriptor, 'smoke', inspect_resources=resources)
            self.assertEqual([r['id'] for r in receipt['tasks']], ['first'])
            self.assertEqual(receipt['tasks'][0]['name'], 'workbuddy/first')
            self.assertTrue((Path(receipt['root']) / 'shared/verifier/plugin.py').is_file())
            self.assertTrue((Path(receipt['root']) / 'dataset.toml').is_file())
            check_dataset(receipt, descriptor, 'smoke', inspect_resources=resources)
            self.assertEqual(original, {p.relative_to(dataset): p.read_bytes() for p in dataset.rglob('*') if p.is_file()})
            (Path(receipt['root']) / 'shared/verifier/plugin.py').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                check_dataset(receipt, descriptor, 'smoke', inspect_resources=resources)
            with self.assertRaisesRegex(ValueError, 'frozen dataset changed'):
                freeze_dataset(dataset, root / 'cache', descriptor, 'smoke', inspect_resources=resources)

    def test_missing_shared_verifier_and_external_links_fail_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, descriptor = self.fixture(root)
            outside = root / 'outside'; outside.write_text('private')
            (dataset / 'external').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                freeze_dataset(dataset, root / 'cache', descriptor, 'smoke', inspect_resources=resources)
            (dataset / 'external').unlink()
            (dataset / 'shared/verifier/plugin.py').unlink()
            with self.assertRaisesRegex(ValueError, 'plugin.py'):
                freeze_dataset(dataset, root / 'cache', descriptor, 'smoke', inspect_resources=resources)

    def test_full_scope_and_cache_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, descriptor = self.fixture(root)
            receipt = freeze_dataset(dataset, root / 'cache', descriptor, 'full', inspect_resources=resources)
            self.assertEqual([r['id'] for r in receipt['tasks']], ['first', 'second'])
            with self.assertRaisesRegex(ValueError, 'outside'):
                freeze_dataset(dataset, dataset / 'cache', descriptor, 'full', inspect_resources=resources)
