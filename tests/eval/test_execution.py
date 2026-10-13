from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval.benchmarks import BenchmarkDescriptor, BenchmarkVariant, PreflightResult
from eval.catalog import BenchmarkCatalog
from eval.contracts import EvaluationRequest
from eval.execution import execute_request
from eval.report import report_from_runner_result
from tests.support.evaluation import request_payload


class FakeAdapter:
    descriptor = BenchmarkDescriptor(
        "swe-bench",
        "SWE-bench",
        "fixture",
        "Verified",
        "1",
        (BenchmarkVariant("smoke", "Smoke", "fixture"),),
        ("accuracy",),
        "fixture/dataset",
        {"provider": False},
        "fixture",
    )

    def preflight(self, variant: str) -> PreflightResult:
        return PreflightResult(True, ({"id": "fixture", "ok": True},))

    def run(self, *, request_path: Path, result_path: Path, variant: str, progress=None) -> None:
        result_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "status": "completed",
                    "metrics": [
                        {
                            "name": "accuracy",
                            "value": 0.75,
                            "unit": "ratio",
                            "direction": "higher_is_better",
                            "scope": "benchmark",
                            "aggregation": "mean",
                            "sample_count": 4,
                        }
                    ],
                    "errors": {},
                    "artifacts": [],
                    "trials": [
                        {
                            "trial_id": "t1",
                            "task_id": "task-1",
                            "status": "passed",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )


class ExecutionTests(unittest.TestCase):
    def test_runner_and_result_failures_still_produce_readable_reports(self) -> None:
        request = EvaluationRequest.from_dict(request_payload())
        cases = (
            (None, "runner"),
            ({"schema_version": 1, "status": "completed"}, "runner"),
            ({"schema_version": 2, "status": "completed",
              "metrics": [{"name": "score", "value": "not numeric"}]}, "result_validation"),
        )
        for payload, error_key in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                adapter = FakeAdapter()

                def run(**kwargs):
                    if payload is None:
                        raise RuntimeError("offline runner failed")
                    kwargs["result_path"].write_text(json.dumps(payload), encoding="utf-8")

                with patch.object(adapter, "run", side_effect=run):
                    report, store = execute_request(request, output_root=Path(directory),
                                                    catalog=BenchmarkCatalog((adapter,)))
                self.assertEqual(report.status, "failed")
                self.assertIn(error_key, report.errors)
                self.assertEqual(json.loads((store.path / "report.json").read_text())["status"], "failed")
                self.assertIn(error_key, (store.path / "report.md").read_text())

    def test_completed_report_surfaces_trial_errors(self) -> None:
        catalog = BenchmarkCatalog((FakeAdapter(),))
        request = EvaluationRequest.from_dict(request_payload())
        report = report_from_runner_result(
            request,
            {
                "status": "completed",
                "metrics": [],
                "errors": {},
                "trials": [
                    {
                        "task_id": "task-1",
                        "status": "error",
                        "error": {"type": "DockerError", "message": "pull failed"},
                    }
                ],
            },
            evaluation_id="fixture", benchmark={"benchmark": "swe-bench", "variant": "smoke"},
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
        )
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.errors["trials"][0]["path"], "trials/000000.json")
        self.assertIn("trials/000000.json", report.render_markdown())
        self.assertIn("DockerError", report.render_markdown())

    def test_fixed_artifact_layout_and_reports(self) -> None:
        adapter = FakeAdapter()
        catalog = BenchmarkCatalog((adapter,))
        request = EvaluationRequest.from_dict(request_payload())
        with tempfile.TemporaryDirectory() as directory:
            report, store = execute_request(
                request, output_root=Path(directory), catalog=catalog
            )
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.metrics[0].value, 0.75)
            self.assertFalse((store.path / "plan.json").exists())
            self.assertEqual(json.loads((store.path / "request.json").read_text()), request.to_dict())
            self.assertEqual(
                set(report.to_dict()),
                {
                    "schema_version",
                    "evaluation_id",
                    "status",
                    "started_at",
                    "completed_at",
                    "benchmark",
                    "runtime",
                    "execution",
                    "metrics",
                    "errors",
                    "artifacts",
                },
            )
            for relative in (
                "request.json",
                "trials/000000.json",
                "report.json",
                "report.md",
            ):
                self.assertTrue((store.path / relative).is_file())
            markdown = (store.path / "report.md").read_text(encoding="utf-8")
            for heading in (
                "## Summary",
                "## Configuration",
                "## Results",
                "## Task Results",
                "## Failures",
                "## Artifacts",
            ):
                self.assertIn(heading, markdown)


if __name__ == "__main__":
    unittest.main()
