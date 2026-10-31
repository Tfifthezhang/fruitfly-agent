"""Harbor results behavior and failure contracts."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
import tempfile
from fruitfly_eval.results import load_harbor_job_result, parse_harbor_job_result
from tests.support.harbor import load_harbor_agent


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_official_rewards_become_trials_and_aggregate_metrics(self) -> None:
        trials, metrics = parse_harbor_job_result(
            {
                "trial_results": [
                    {
                        "id": "trial-1",
                        "task_name": "task-a",
                        "verifier_result": {"rewards": {"reward": 1}},
                        "agent_result": {
                            "n_input_tokens": 10,
                            "n_output_tokens": 4,
                            "cost_usd": 0.02,
                        },
                        "agent_execution": {
                            "started_at": "2026-01-01T00:00:00Z",
                            "finished_at": "2026-01-01T00:00:02Z",
                        },
                    },
                    {
                        "id": "trial-2",
                        "task_name": "task-b",
                        "verifier_result": {"rewards": {"reward": 0}},
                        "agent_result": {
                            "n_input_tokens": 8,
                            "n_output_tokens": 3,
                        },
                    },
                ]
            },
            job_id="current",
        )
        self.assertEqual([item["status"] for item in trials], ["passed", "failed"])
        values = {item["name"]: item["value"] for item in metrics}
        self.assertEqual(values["success_rate"], 0.5)
        self.assertEqual(values["official_reward"], 0.5)
        self.assertEqual(values["input_tokens"], 18)
        self.assertEqual(values["latency_ms"], 2000)

    def test_reward_shapes_preserve_unknown_values_and_single_metric_fallback(self) -> None:
        for name, verifier, reward, status in (
            ("missing", None, None, "error"),
            ("non-mapping rewards", {"rewards": []}, None, "error"),
            ("null rewards", {"rewards": None}, None, "error"),
            ("single official metric", {"rewards": {"score": 1}}, 1.0, "passed"),
            ("ambiguous metrics", {"rewards": {"a": 1, "b": 0}}, None, "error"),
            ("explicit reward", {"rewards": {"reward": 0, "other": 1}}, 0.0, "failed"),
        ):
            with self.subTest(shape=name):
                trials, metrics = parse_harbor_job_result(
                    {"trial_results": [{"verifier_result": verifier}]}, job_id="current")
                values = {item["name"]: item["value"] for item in metrics}
                self.assertEqual(status, trials[0]["status"])
                self.assertEqual(reward, values["official_reward"])
                self.assertIsNone(values["input_tokens"])
                self.assertIsNone(values["cost_usd"])

    def test_timeout_is_reported_and_retains_available_usage(self) -> None:
        trials, metrics = parse_harbor_job_result({"trial_results": [{
            "verifier_result": {"rewards": {"reward": 1}},
            "agent_result": {"n_input_tokens": 0, "cost_usd": 0.0},
            "exception_info": {"exception_type": "AgentTimeout", "exception_message": "deadline"},
        }]}, job_id="current")
        self.assertEqual("AgentTimeout", trials[0]["error"]["type"])
        self.assertEqual([], trials[0]["metrics"])
        values = {item["name"]: item["value"] for item in metrics}
        self.assertIsNone(values["official_reward"])
        self.assertEqual(1.0, values["error_rate"])
        self.assertEqual(1.0, values["timeout_rate"])
        self.assertEqual(0, values["input_tokens"])
        self.assertEqual(0.0, values["cost_usd"])

    def test_empty_harbor_job_is_not_reported_as_a_completed_benchmark(self) -> None:
        with self.assertRaisesRegex(ValueError, "no trials"):
            parse_harbor_job_result({"trial_results": []}, job_id="current")

    def test_harbor_job_loads_separate_trial_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory)
            trial_dir = job / "fix-git__attempt"
            trial_dir.mkdir()
            (job / "result.json").write_text(
                json.dumps({"n_total_trials": 1, "stats": {"n_completed_trials": 1}}),
                encoding="utf-8",
            )
            (trial_dir / "result.json").write_text(
                json.dumps(
                    {
                        "id": "trial-1",
                        "task_name": "fix-git",
                        "verifier_result": {"rewards": {"reward": 1.0}},
                        "agent_result": {
                            "metadata": {"runtime_manifest_digest": "sha256:frozen"},
                            "n_input_tokens": 13,
                            "n_output_tokens": 5,
                        },
                    }
                ),
                encoding="utf-8",
            )

            trials, metrics = parse_harbor_job_result(
                load_harbor_job_result(job / "result.json"),
                job_id="current",
            )

            self.assertEqual(trials[0]["status"], "passed")
            values = {item["name"]: item["value"] for item in metrics}
            self.assertEqual(values["official_reward"], 1.0)
            self.assertEqual(values["input_tokens"], 13)

    def test_harbor_job_rejects_missing_trial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"n_total_trials": 1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "0 of 1 trial result files"):
                load_harbor_job_result(path)

    def test_actual_runtime_is_reported_without_comparing_it_to_a_frozen_identity(self):
        actual = {"digest": "sha256:actual", "models": {"main": {"model": "actual-model"}}}
        trials, metrics = parse_harbor_job_result({"trial_results": [{
            "id": "trial-1", "task_name": "task-a", "verifier_result": {"rewards": {"reward": 1}},
            "agent_result": {"metadata": {"runtime_manifest": actual}},
        }]}, job_id="current")
        self.assertEqual("passed", trials[0]["status"])
        self.assertEqual(actual, trials[0]["runtime"])
        self.assertIsNone(trials[0]["error"])
        self.assertNotIn("condition_id", trials[0])
        self.assertEqual(1.0, next(item["value"] for item in metrics if item["name"] == "success_rate"))

    def test_harbor_setup_error_is_reported_without_runtime_metadata(self) -> None:
        trials, metrics = parse_harbor_job_result(
            {
                "trial_results": [
                    {
                        "id": "trial-1",
                        "task_name": "fix-git",
                        "agent_result": None,
                        "exception_info": {
                            "exception_type": "RuntimeError",
                            "exception_message": "Docker Hub connection failed",
                        },
                    }
                ]
            },
            job_id="current",
        )
        self.assertEqual(trials[0]["error"]["type"], "RuntimeError")
        self.assertIn("Docker Hub", trials[0]["error"]["message"])
        self.assertEqual(
            next(item["value"] for item in metrics if item["name"] == "error_rate"),
            1.0,
        )
