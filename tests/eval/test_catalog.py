from __future__ import annotations

import unittest
import json
import tempfile
from unittest.mock import patch

from fruitfly_eval.catalog import builtin_catalog


class BenchmarkCatalogTests(unittest.TestCase):
    def test_terminal_bench_uses_the_21_hub_dataset(self):
        descriptor = builtin_catalog().get("terminal-bench").descriptor
        self.assertEqual(descriptor.version, "2.1")
        self.assertEqual(descriptor.dataset, "terminal-bench/terminal-bench-2-1")
        self.assertEqual(descriptor.variants[0].task_names, ("terminal-bench/fix-git",))

    def test_terminal_bench_4_is_a_separate_version_pinned_declaration(self):
        descriptor = builtin_catalog().get("terminal-bench-4").descriptor
        self.assertEqual(descriptor.version, "4.0.0")
        self.assertEqual(descriptor.dataset, "terminal-bench/terminal-bench@4.0.0")
        self.assertEqual(descriptor.variants[0].task_names, ("terminal-bench/interleaved-vigenere",))

    def test_another_harbor_benchmark_reuses_execution_without_named_branches(self):
        from pathlib import Path
        from fruitfly_eval.benchmarks.harbor import HarborBenchmarkAdapter, harbor_descriptor
        from tests.support.harbor import prepared_harbor
        adapter = HarborBenchmarkAdapter(harbor_command="harbor", docker_command="docker")
        adapter.descriptor = harbor_descriptor(benchmark_id="other", label="Other", description="Fixture",
            version="1", dataset="example/tasks", smoke_task="example/task")
        with patch("fruitfly_eval.benchmarks.harbor._docker_check", return_value={"ok": True, "detail": "ready"}):
            self.assertTrue(adapter.preflight("full").available)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        host, preparation = prepared_harbor(root, ("example/task",))
        command = adapter._command(executable="harbor", dataset=adapter.descriptor.dataset,
            variant="full", execution={"attempts": 1, "concurrency": 1}, jobs_dir=root,
            job_name="fixture", config_path=Path("config"),
            model_catalog=Path("models"), profile="default", secret_names=(), host=host, preparation=preparation)
        config = json.loads(Path(command[3]).read_text())
        self.assertEqual(config["tasks"][0]["source"], "example/tasks")
        self.assertEqual(config["agents"][0]["import_path"], "fruitfly_eval.harbor_agent:FruitFlyHarborAgent")

    def test_standardized_benchmarks_and_modes_are_registered(self) -> None:
        with patch("fruitfly_eval.benchmarks.harbor._harbor_executable", return_value=None):
            with patch("fruitfly_eval.benchmarks.harbor.shutil.which", return_value=None):
                payload = builtin_catalog().to_dict()
        self.assertNotIn("modes", payload)
        self.assertEqual(
            [item["id"] for item in payload["benchmarks"]],
            ["swe-bench", "terminal-bench", "terminal-bench-4"],
        )
        for item in payload["benchmarks"]:
            self.assertEqual([v["id"] for v in item["variants"]], ["smoke", "no_gpu", "full"])
        swe_bench = payload["benchmarks"][0]
        self.assertEqual(swe_bench["version"], "Verified")
        self.assertEqual(
            [item["id"] for item in swe_bench["variants"]],
            ["smoke", "no_gpu", "full"],
        )
        self.assertFalse(swe_bench["variants"][0]["preflight"]["available"])

    def test_unknown_benchmark_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown benchmark"):
            builtin_catalog().get("missing")


if __name__ == "__main__":
    unittest.main()
