from __future__ import annotations

import unittest
from unittest.mock import patch

from eval.catalog import builtin_catalog


class BenchmarkCatalogTests(unittest.TestCase):
    def test_terminal_bench_uses_the_21_hub_dataset(self):
        descriptor = builtin_catalog().get("terminal-bench").descriptor
        self.assertEqual(descriptor.version, "2.1")
        self.assertEqual(descriptor.dataset, "terminal-bench/terminal-bench-2-1")
        self.assertEqual(descriptor.variants[0].task_names, ("terminal-bench/fix-git",))

    def test_another_harbor_benchmark_reuses_execution_without_named_branches(self):
        from dataclasses import replace
        from pathlib import Path
        from eval.benchmarks.base import BenchmarkVariant
        from eval.benchmarks.harbor import HarborBenchmarkAdapter, harbor_descriptor
        adapter = HarborBenchmarkAdapter(harbor_command="harbor", docker_command="docker")
        adapter.descriptor = harbor_descriptor(benchmark_id="other", label="Other", description="Fixture",
            version="1", dataset="example/tasks", smoke_task="example/task")
        adapter.descriptor = replace(adapter.descriptor, variants=(
            BenchmarkVariant("accelerator", "Accelerator", "Fixture", requires_gpu=True),))
        with patch("eval.benchmarks.harbor._docker_check", return_value={"ok": True, "detail": "ready"}), \
                patch("eval.benchmarks.harbor.shutil.which", return_value=None):
            self.assertFalse(adapter.preflight("accelerator").available)
        command = adapter._command(executable="harbor", dataset=adapter.descriptor.dataset,
            variant="accelerator", execution={"attempts": 1, "concurrency": 1}, jobs_dir=Path("jobs"),
            job_name="fixture", source_root=Path("source"), config_path=Path("config"),
            model_catalog=Path("models"), profile="default", secret_names=())
        self.assertEqual(command[command.index("--dataset") + 1], "example/tasks")
        self.assertIn("eval.harbor_agent:FruitFlyHarborAgent", command)

    def test_standardized_benchmarks_and_modes_are_registered(self) -> None:
        with patch("eval.benchmarks.harbor._harbor_executable", return_value=None):
            with patch("eval.benchmarks.harbor.shutil.which", return_value=None):
                payload = builtin_catalog().to_dict()
        self.assertNotIn("modes", payload)
        self.assertEqual(
            [item["id"] for item in payload["benchmarks"]],
            ["swe-bench", "terminal-bench"],
        )
        swe_bench = payload["benchmarks"][0]
        self.assertEqual(swe_bench["version"], "Verified")
        self.assertEqual(
            [item["id"] for item in swe_bench["variants"]],
            ["smoke", "no_gpu", "gpu"],
        )
        self.assertFalse(swe_bench["variants"][0]["preflight"]["available"])

    def test_unknown_benchmark_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown benchmark"):
            builtin_catalog().get("missing")


if __name__ == "__main__":
    unittest.main()
