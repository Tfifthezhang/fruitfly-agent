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
from tests.support.harbor import prepared_harbor


TASKS = tuple("terminal-bench/" + name for name in ("fix-git", "log-summary-date-ranges", "regex-log", "cancel-async-tasks", "fix-code-vulnerability"))


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
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for variant in ("starter", "no_gpu", "gpu"):
            with self.subTest(variant=variant):
                host, preparation = prepared_harbor(root, TASKS if variant == "starter" else (*TASKS, "another-task"))
                command = adapter._command(executable="harbor", dataset=adapter.descriptor.dataset,
                    variant=variant, execution={"attempts": 1, "concurrency": 1},
                    jobs_dir=root, job_name="job",
                    config_path=Path("/tmp/config"), model_catalog=Path("/tmp/models"), profile="test", secret_names=(),
                    host=host, preparation=preparation)
                config = json.loads(Path(command[3]).read_text())
                self.assertEqual([t["path"] for t in config["tasks"]], [t["path"] for t in preparation["tasks"]])
                self.assertNotIn("datasets", config)  # Full runs also consume the frozen task list.
                self.assertEqual(len(config["tasks"]), 5 if variant == "starter" else 6)

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
                host, preparation = prepared_harbor(root, TASKS)
                with patch.object(adapter, "preflight", return_value=PreflightResult(True, (), ("offline-harbor",))), patch(
                    "eval.benchmarks.harbor.prepare_runtime", return_value=(root / "config", root / "models", ())), patch(
                    "eval.benchmarks.harbor.load_env", return_value={}
                ), patch("eval.benchmarks.harbor.run_harbor_job", return_value=(0, "")), patch(
                    "eval.benchmarks.harbor.HostConfig.read", return_value=host
                ), patch("eval.benchmarks.harbor.load_preparation", return_value=preparation), patch(
                    "eval.benchmarks.harbor.inspect_preparation", return_value={"available": True}):
                    if passes:
                        adapter.run(request_path=request_path, result_path=result_path, variant="starter")
                        result = json.loads(result_path.read_text())
                        self.assertEqual([t["task_id"] for t in result["trials"]], list(names))
                        self.assertEqual(result["trials"][1]["status"], "failed")
                    else:
                        adapter.run(request_path=request_path, result_path=result_path, variant="starter")
                        result = json.loads(result_path.read_text())
                        self.assertEqual(result["status"], "failed")
                        self.assertIn("prepared task set", result["errors"]["coverage"])
                        self.assertEqual(len(result["trials"]), len(names))
                        self.assertEqual(result["metrics"], [])
