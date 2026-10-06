from __future__ import annotations

import unittest
from unittest.mock import patch

from eval.catalog import builtin_catalog


class BenchmarkCatalogTests(unittest.TestCase):
    def test_standardized_benchmarks_and_modes_are_registered(self) -> None:
        with patch("eval.benchmarks.harbor._harbor_executable", return_value=None):
            with patch("eval.benchmarks.harbor.shutil.which", return_value=None):
                payload = builtin_catalog().to_dict()
        self.assertEqual(
            [item["id"] for item in payload["modes"]],
            ["current_setup", "mechanism_comparison"],
        )
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
