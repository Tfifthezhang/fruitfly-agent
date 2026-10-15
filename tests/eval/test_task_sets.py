"""Task discovery freezes official material without baseline Agent calls."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from eval.task_sets import prepare_task_set, improvement_catalog
from eval.catalog import builtin_catalog
from eval.benchmarks.base import PreflightResult
from eval.benchmarks.terminal_bench import TerminalBenchAdapter
from fruitfly_agent.lab.optimization.experiments import TaskReference
from eval.evidence import material_hash


class TaskSetTests(unittest.IsolatedAsyncioTestCase):
    def originals(self, root, names):
        result=[]
        for name in names:
            source=root/name
            (source/'tests').mkdir(parents=True)
            (source/'instruction.md').write_text('Complete '+name)
            (source/'task.toml').write_text('[environment]\ncpus = 1\n')
            (source/'tests/test.sh').write_text('exit 0\n')
            result.append((name,source,'fixed-revision'))
        return result

    async def test_fixed_batch_copies_complete_source_without_execution_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            adapter=TerminalBenchAdapter()
            names=adapter.descriptor.variants[1].task_names
            resolver=AsyncMock(return_value=self.originals(root,names))
            with patch('eval.task_sets.builtin_catalog',return_value=SimpleNamespace(get=lambda _:adapter)), patch.object(
                adapter,'preflight',return_value=PreflightResult(True,(),('harbor',))):
                bundle=await prepare_task_set('terminal-bench','starter',5,output_root=root/'prepared',resolver=resolver)
            self.assertEqual(len(bundle['tasks']),5)
            self.assertNotIn('runs',bundle)
            self.assertNotIn('score',repr(bundle))
            for row in bundle['tasks']:
                task=TaskReference.from_dict(row)
                copied=root/'prepared'/bundle['materials'][task.reference_id]
                self.assertEqual(material_hash(copied),task.material_hash)
                self.assertEqual(task.source_revision,'fixed-revision')
            resolver.assert_awaited_once()
            self.assertEqual(resolver.call_args.args[1],names)

    async def test_unavailable_environment_or_wrong_batch_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            adapter=TerminalBenchAdapter()
            resolver=AsyncMock()
            with patch('eval.task_sets.builtin_catalog',return_value=SimpleNamespace(get=lambda _:adapter)), patch.object(
                adapter,'preflight',return_value=PreflightResult(False,({'ok':False,'detail':'Start Docker'},))):
                with self.assertRaisesRegex(RuntimeError,'Start Docker'):
                    await prepare_task_set('terminal-bench','starter',5,output_root=root/'prepared',resolver=resolver)
                with self.assertRaisesRegex(ValueError,'batch size'):
                    await prepare_task_set('terminal-bench','starter',3,output_root=root/'wrong',resolver=resolver)
                with self.assertRaises(ValueError):
                    await prepare_task_set('terminal-bench','smoke',5,output_root=root/'smoke',resolver=resolver)
            resolver.assert_not_awaited()

    def test_improvement_catalog_offers_only_valid_bounded_cpu_batches(self):
        with patch('eval.benchmarks.harbor.HarborBenchmarkAdapter.preflight',return_value=PreflightResult(True,())):
            payload=improvement_catalog(builtin_catalog())
        for benchmark in payload['benchmarks']:
            self.assertTrue(benchmark['variants'])
            self.assertTrue(all(v['id'] in {'starter','no_gpu'} for v in benchmark['variants']))
            for variant in benchmark['variants']:
                if variant['id']=='no_gpu':
                    self.assertIn('5 tasks',variant['label'])
