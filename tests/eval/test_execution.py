from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from eval.benchmarks import BenchmarkDescriptor, BenchmarkVariant, PreflightResult
from eval.catalog import BenchmarkCatalog
from eval.contracts import EvaluationRequest
from eval.execution import execute_plan
from eval.planning import create_plan
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

    def run(self, *, plan_path: Path, result_path: Path, variant: str, progress=None) -> None:
        result_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "completed",
                    "metrics": [
                        {
                            "name": "accuracy",
                            "value": 0.75,
                            "unit": "ratio",
                            "direction": "higher_is_better",
                            "scope": "benchmark",
                            "condition_id": "current",
                            "aggregation": "mean",
                            "sample_count": 4,
                        }
                    ],
                    "comparisons": [],
                    "errors": {},
                    "artifacts": [],
                    "trials": [
                        {
                            "trial_id": "t1",
                            "condition_id": "current",
                            "task_id": "task-1",
                            "status": "passed",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )


class ExecutionTests(unittest.TestCase):
    def test_completed_report_surfaces_trial_errors(self) -> None:
        catalog = BenchmarkCatalog((FakeAdapter(),))
        plan = create_plan(
            EvaluationRequest.from_dict(request_payload()), catalog=catalog
        )
        report = report_from_runner_result(
            plan,
            {
                "status": "completed",
                "metrics": [],
                "comparisons": [],
                "errors": {},
                "trials": [
                    {
                        "task_id": "task-1",
                        "status": "error",
                        "error": {"type": "DockerError", "message": "pull failed"},
                    }
                ],
            },
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:00:01Z",
        )
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.errors["trials"][0]["path"], "trials/000000.json")
        self.assertIn("Trial errors: 1", report.render_markdown())
        self.assertIn("DockerError", report.render_markdown())

    def test_fixed_artifact_layout_and_reports(self) -> None:
        adapter = FakeAdapter()
        catalog = BenchmarkCatalog((adapter,))
        plan = create_plan(
            EvaluationRequest.from_dict(request_payload()), catalog=catalog
        )
        with tempfile.TemporaryDirectory() as directory:
            report, store = execute_plan(
                plan, output_root=Path(directory), catalog=catalog
            )
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.metrics[0].value, 0.75)
            self.assertEqual(
                set(report.to_dict()),
                {
                    "schema_version",
                    "evaluation_id",
                    "status",
                    "mode",
                    "started_at",
                    "completed_at",
                    "benchmark",
                    "runtime",
                    "execution",
                    "conditions",
                    "metrics",
                    "comparisons",
                    "errors",
                    "artifacts",
                },
            )
            for relative in (
                "request.json",
                "plan.json",
                "trials/000000.json",
                "report.json",
                "report.md",
            ):
                self.assertTrue((store.path / relative).is_file())
            markdown = (store.path / "report.md").read_text(encoding="utf-8")
            for heading in (
                "## Summary",
                "## Experimental Conditions",
                "## Primary Results",
                "## Quality, Cost, and Reliability",
                "## Comparison",
                "## Task Results",
                "## Failures",
                "## Reproducibility",
                "## Artifacts",
            ):
                self.assertIn(heading, markdown)


if __name__ == "__main__":
    unittest.main()
