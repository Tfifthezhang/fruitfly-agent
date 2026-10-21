from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval.__main__ import main
from tests.support.evaluation import request_payload


class EvalCliTests(unittest.TestCase):
    def test_improvement_only_commands_and_catalog_option_are_rejected(self) -> None:
        for command in (["prepare"], ["trial"], ["catalog", "--improvement"]):
            with self.subTest(command=command), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as raised:
                main(command)
            self.assertEqual(raised.exception.code, 2)

    def test_removed_plan_command_is_rejected(self) -> None:
        errors = StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            main(["plan", "--request", "request.json"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", errors.getvalue())

    def test_legacy_reports_are_read_without_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "legacy"
            report_dir.mkdir()
            payload = {"schema_version": 1, "status": "completed", "conditions": []}
            report_path = report_dir / "report.json"
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            report_dir.joinpath("report.md").write_text("# Saved legacy report\n", encoding="utf-8")
            original = report_path.read_bytes()
            for suffix, expected in ((["--json"], payload), ([], "# Saved legacy report\n")):
                output = StringIO()
                with redirect_stdout(output):
                    result = main(["report", "legacy", "--output-root", directory, *suffix])
                self.assertEqual(result, 0)
                actual = json.loads(output.getvalue()) if suffix else output.getvalue()
                self.assertEqual(actual, expected)
            self.assertEqual(report_path.read_bytes(), original)

    def test_catalog_json_is_machine_readable(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["catalog", "--json"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["schema_version"], 1)

    def test_catalog_text_explains_missing_dependencies(self) -> None:
        output = StringIO()
        with patch("eval.benchmarks.harbor._harbor_executable", return_value=None):
            with patch("eval.benchmarks.harbor.shutil.which", return_value=None):
                with redirect_stdout(output):
                    result = main(["catalog"])
        self.assertEqual(result, 0)
        self.assertIn("install the benchmark extra", output.getvalue())
        self.assertIn("Docker CLI was not found", output.getvalue())

    def test_unavailable_runner_produces_blocked_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = request_payload()
            payload["runtime"]["working_directory"] = str(root)
            request = root / "request.json"
            request.write_text(json.dumps(payload), encoding="utf-8")
            output = StringIO()
            with patch("eval.execution.builtin_catalog") as catalog:
                from eval.benchmarks.base import PreflightResult
                from eval.benchmarks.swe_bench import SWEBenchAdapter
                from eval.catalog import BenchmarkCatalog

                adapter = SWEBenchAdapter()
                adapter.preflight = lambda variant: PreflightResult(
                    False, ({"id": "fixture", "ok": False, "detail": "not ready"},)
                )
                catalog.return_value = BenchmarkCatalog((adapter,))
                with redirect_stdout(output):
                    result = main(
                        ["run", "--request", str(request), "--events", "jsonl"]
                    )
            self.assertEqual(result, 3)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(events[-1]["status"], "blocked")
            report = Path(events[-1]["report_json"])
            self.assertTrue(report.is_file())
            self.assertEqual(json.loads(report.read_text())["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
