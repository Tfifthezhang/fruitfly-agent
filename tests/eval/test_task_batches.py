"""Fixed subsets use official tasks and cannot silently become full evaluations."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval.benchmarks.base import BenchmarkVariant, PreflightResult
from eval.benchmarks.terminal_bench import TerminalBenchAdapter
from eval.catalog import builtin_catalog
from tests.support.evaluation import request_payload


TASKS = ("fix-git", "log-summary-date-ranges", "regex-log", "cancel-async-tasks", "fix-code-vulnerability")


class TaskBatchTests(unittest.TestCase):
    def test_catalog_exposes_fixed_batch_without_network_requests(self):
        with patch("eval.benchmarks.harbor._harbor_executable", return_value=None), patch(
            "eval.benchmarks.harbor.shutil.which", return_value=None
        ):
            terminal = next(b for b in builtin_catalog().to_dict()["benchmarks"] if b["id"] == "terminal-bench")
        starter = next(v for v in terminal["variants"] if v["id"] == "starter")
        self.assertEqual(starter["task_names"], list(TASKS))
        self.assertIn("5 CPU tasks", starter["label"])

    def test_task_filters_are_exact_and_full_profiles_remain_unfiltered(self):
        adapter = TerminalBenchAdapter()
        for variant in ("starter", "no_gpu", "gpu"):
            with self.subTest(variant=variant):
                command = adapter._command(executable="harbor", dataset=adapter.descriptor.dataset,
                    variant=variant, execution={"attempts": 1, "concurrency": 1},
                    jobs_dir=Path("/tmp/jobs"), job_name="job", source_root=Path("/tmp/source"),
                    config_path=Path("/tmp/config"), model_catalog=Path("/tmp/models"), profile="test", secret_names=())
                names = tuple(command[i + 1] for i, arg in enumerate(command) if arg == "--include-task-name")
                self.assertEqual(names, TASKS if variant == "starter" else ())
                self.assertIn("eval.harbor_agent:FruitFlyHarborAgent", command)
                if variant == "starter":
                    self.assertEqual(command[command.index("--n-tasks") + 1], "5")
                else:
                    self.assertNotIn("--n-tasks", command)

    def test_generic_variant_rejects_patterns_duplicates_and_invalid_names(self):
        for names in (("*",), ("valid", "valid"), ("../task",), ("--flag",), ("a\nb",), ([],)):
            with self.subTest(names=names), self.assertRaises(ValueError):
                BenchmarkVariant("subset", "Subset", "test", task_names=names)
        self.assertEqual(BenchmarkVariant("subset", "Subset", "test", ["repo/task-1"]).task_names,
                         ("repo/task-1",))

    def test_official_results_must_cover_selected_tasks_and_attempts(self):
        for names, attempts, passes in ((TASKS, 1, True), ((*TASKS, *TASKS), 2, True),
                                       (TASKS, 2, False), (TASKS[:-1], 1, False),
                                       ((*TASKS[:-1], "unexpected"), 1, False), ((*TASKS, TASKS[0]), 1, False)):
            with self.subTest(names=names, attempts=attempts), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                request = request_payload()
                request["benchmark"] = {"id": "terminal-bench", "variant": "starter"}
                request["execution"]["attempts"] = attempts
                request["runtime"]["working_directory"] = str(root)
                request_path, result_path = root / "request.json", root / "result.json"
                request_path.write_text(json.dumps(request))
                job = root / "harbor/terminal-bench"
                job.mkdir(parents=True)
                (job / "result.json").write_text(json.dumps({"trial_results": [
                    {"task_name": name, "verifier_result": {"rewards": {"reward": int(i == 0)}}}
                    for i, name in enumerate(names)]}))
                adapter = TerminalBenchAdapter()
                with patch.object(adapter, "preflight", return_value=PreflightResult(True, (), ("offline-harbor",))), patch(
                    "eval.benchmarks.harbor.resolve_installation", return_value=root
                ), patch("eval.benchmarks.harbor._runtime_files", return_value=(root / "config", root / "models", ())), patch(
                    "eval.benchmarks.harbor.load_env", return_value={}
                ), patch("eval.benchmarks.harbor._run_harbor_job", return_value=(0, "")):
                    if passes:
                        adapter.run(request_path=request_path, result_path=result_path, variant="starter")
                        result = json.loads(result_path.read_text())
                        self.assertEqual([t["task_id"] for t in result["trials"]], list(names))
                        self.assertEqual(result["trials"][1]["status"], "failed")
                    else:
                        with self.assertRaisesRegex(ValueError, "selected task batch"):
                            adapter.run(request_path=request_path, result_path=result_path, variant="starter")
                        self.assertFalse(result_path.exists())
