"""Shared task selection excludes GPU resources before any environment starts."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eval.benchmarks.base import BenchmarkVariant, PreflightResult
from eval.benchmarks.harbor import HarborBenchmarkAdapter, harbor_descriptor
from eval.catalog import builtin_catalog
from eval.contracts import EvaluationRequest
from eval.harbor.preparation import load_preparation, prepare
from eval.harbor.selection import inspect_images, task_requirements
from eval.harbor.tasks import prepare_tasks
from tests.support.evaluation import request_payload
from tests.support.harbor import prepared_harbor


TASKS = tuple("example/" + name for name in ("task-a", "task-b", "task-c"))


class TaskBatchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.host, _ = prepared_harbor(self.root)
        self.inputs = self.root / "inputs"
        self.host = replace(self.host, task_directory=self.inputs)
        self.descriptor = harbor_descriptor(benchmark_id="example", label="Example", description="Fixture",
            version="1", dataset="example/tasks@1", smoke_task="example/task-a")
        for name in ("task-a", "task-b", "task-c"):
            root = self.inputs / name
            (root / "environment").mkdir(parents=True)
            (root / "task.toml").write_text('[environment]\ndocker_image = "' + name + ':v1"\n')
            (root / "instruction.md").write_text("Do the task.")

    def definitions(self, task):
        return [{"role": "agent", "step": None, "configuration": task["configuration"]["environment"],
                 "context": str(Path(task["path"]) / "environment")}]

    def test_catalog_exposes_only_three_selections_for_every_benchmark(self):
        with patch("eval.benchmarks.harbor._harbor_executable", return_value=None), patch(
            "eval.benchmarks.harbor.shutil.which", return_value=None
        ):
            payload = builtin_catalog().to_dict()
        for benchmark in payload["benchmarks"]:
            self.assertEqual([v["id"] for v in benchmark["variants"]], ["smoke", "no_gpu", "full"])

    def test_no_gpu_excludes_agent_verifier_and_step_resources_before_image_checks(self):
        def definitions(task):
            name = Path(task["path"]).name
            base = self.definitions(task)
            if name == "task-b":
                base.append({**base[0], "role": "verifier", "step": "grade", "configuration": {"gpus": 1}})
            if name == "task-c":
                base[0]["configuration"] = {"gpu_types": ["example-accelerator"]}
            return base
        payload = request_payload()
        payload["benchmark"] = {"id": "example", "variant": "no_gpu"}
        with patch("eval.harbor.selection.environment_definitions", side_effect=definitions), patch(
            "eval.harbor.preparation.image_identity", side_effect=AssertionError("unexpected probe")
        ), patch("eval.harbor.selection.image_identity", return_value="sha256:cpu") as images, patch(
            "eval.harbor.preparation.prepare_material", side_effect=AssertionError("unexpected runtime preparation")
        ), patch("eval.harbor.preparation.probe_environment", side_effect=AssertionError("unexpected container")):
            result = prepare(EvaluationRequest.from_dict(payload), self.descriptor, self.host, tasks_only=True)
        self.assertEqual(result["selection"]["selected"], ["task-a"])
        self.assertEqual([t["id"] for t in result["selection"]["excluded"]], ["task-b", "task-c"])
        self.assertEqual(result["selection"]["excluded"][0]["requirements"][0]["step"], "grade")
        images.assert_called_once_with("docker", "task-a:v1")
        self.assertTrue(Path(result["inventory"]).is_file())
        with self.assertRaisesRegex(ValueError, "not prepared"):
            load_preparation(self.host, self.descriptor, "no_gpu")

    def test_full_retains_gpu_tasks_and_smoke_selects_one_exact_task(self):
        (self.inputs / "task-b/task.toml").write_text('[environment]\ngpus = 1\ndocker_image = "gpu:v1"\n')
        with patch("eval.harbor.selection.environment_definitions", side_effect=self.definitions):
            full = prepare_tasks(self.host, self.descriptor, "full")
            smoke = prepare_tasks(self.host, self.descriptor, "smoke")
        self.assertEqual(len(full["tasks"]), 3)
        self.assertEqual(full["selection"]["excluded"], [])
        self.assertEqual(smoke["selection"]["selected"], ["example/task-a"])
        for task in full["tasks"]:
            self.assertEqual((Path(task["path"]) / "task.toml").read_bytes(),
                             (self.inputs / task["name"] / "task.toml").read_bytes())

    def test_compose_auxiliary_gpu_and_unresolved_inheritance_are_not_selected_as_cpu(self):
        context = self.inputs / "task-b/environment"
        cases = (
            'services: {main: {image: cpu:v1}, helper: {image: gpu:v1, gpus: all}}',
            'services: {main: {image: cpu:v1}, helper: {deploy: {resources: {reservations: {devices: [{driver: nvidia, capabilities: [compute]}]}}}}}',
            'services: {main: {extends: {file: elsewhere.yaml, service: main}}}',
            'include: [elsewhere.yaml]\nservices: {main: {image: cpu:v1}}',
        )
        for content in cases:
            with self.subTest(content=content):
                (context / "docker-compose.yaml").write_text(content)
                with patch("eval.harbor.selection.environment_definitions", side_effect=self.definitions):
                    result = prepare_tasks(self.host, self.descriptor, "no_gpu")
                self.assertEqual(result["selection"]["selected"], ["task-a", "task-c"])
                self.assertEqual(result["selection"]["excluded"][0]["id"], "task-b")

    def test_inventory_includes_compose_services_builds_and_full_digest_references(self):
        context = self.inputs / "task-a/environment"
        reference = "example/image:tag@sha256:" + "a" * 64
        (context / "docker-compose.yaml").write_text(
            'services:\n  main:\n    image: ' + reference + '\n  helper:\n    image: helper:v1\n    build: .\n')
        task = {"path": str(context.parent), "configuration": {"environment": {}}}
        with patch("eval.harbor.selection.environment_definitions", side_effect=self.definitions):
            requirements = task_requirements(task)
        self.assertEqual(requirements["gpu_requirements"], [])
        self.assertEqual(len(requirements["builds"]), 1)
        with patch("eval.harbor.selection.image_identity", side_effect=[ValueError("not cached"), "sha256:helper"]) as inspect:
            result = inspect_images([{"requirements": requirements}], "docker")
        self.assertEqual(inspect.call_args_list[0].args, ("docker", reference))
        self.assertEqual([r["status"] for r in result], ["unavailable", "cached"])

    def test_nested_local_task_export_has_actionable_error(self):
        nested = self.root / "nested/task/revision"
        nested.mkdir(parents=True)
        (nested / "task.toml").write_text("[environment]\n")
        host = replace(self.host, task_directory=self.root / "nested")
        with self.assertRaisesRegex(ValueError, "immediate.*registry resolution"):
            prepare_tasks(host, self.descriptor, "full")

    def test_all_gpu_selection_fails_without_starting_environments(self):
        for name in ("task-a", "task-b", "task-c"):
            (self.inputs / name / "task.toml").write_text('[environment]\ngpus = 1\n')
        with patch("eval.harbor.selection.environment_definitions", side_effect=self.definitions), self.assertRaisesRegex(ValueError, "no tasks remain"):
            prepare_tasks(self.host, self.descriptor, "no_gpu")

    def test_variant_rejects_removed_categories_patterns_duplicates_and_invalid_names(self):
        for category in ("starter", "gpu", "cpu", "no_GPU"):
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, "smoke, no_gpu or full"):
                BenchmarkVariant(category, "Fixture", "test")
            payload = request_payload()
            payload["benchmark"]["variant"] = category
            with self.assertRaises(ValueError):
                EvaluationRequest.from_dict(payload)
        for names in (("*",), ("valid", "valid"), ("../task",), ("--flag",), ("a\nb",), ([],)):
            with self.subTest(names=names), self.assertRaises(ValueError):
                BenchmarkVariant("smoke", "Smoke", "test", task_names=names)
        self.assertEqual(BenchmarkVariant("smoke", "Smoke", "test", ["repo/task-1"]).task_names,
                         ("repo/task-1",))

    def test_official_results_must_cover_selected_tasks_and_attempts(self):
        for names, attempts, passes in ((TASKS, 1, True), ((*TASKS, *TASKS), 2, True),
                                       (TASKS, 2, False), (TASKS[:-1], 1, False),
                                       ((*TASKS[:-1], "unexpected"), 1, False), ((*TASKS, TASKS[0]), 1, False)):
            with self.subTest(names=names, attempts=attempts), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                request = request_payload()
                request["benchmark"] = {"id": "example", "variant": "full"}
                request["execution"]["attempts"] = attempts
                request["runtime"]["working_directory"] = str(root)
                request_path, result_path = root / "request.json", root / "result.json"
                request_path.write_text(json.dumps(request))
                job = root / "harbor/example"
                job.mkdir(parents=True)
                (job / "result.json").write_text(json.dumps({"trial_results": [
                    {"task_name": name, "verifier_result": {"rewards": {"reward": int(i == 0)}}}
                    for i, name in enumerate(names)]}))
                adapter = HarborBenchmarkAdapter()
                adapter.descriptor = self.descriptor
                host, preparation = prepared_harbor(root, TASKS)
                with patch.object(adapter, "preflight", return_value=PreflightResult(True, (), ("offline-harbor",))), patch(
                    "eval.benchmarks.harbor.prepare_runtime", return_value=(root / "config", root / "models", ())), patch(
                    "eval.benchmarks.harbor.load_env", return_value={}
                ), patch("eval.benchmarks.harbor.run_harbor_job", return_value=(0, "")), patch(
                    "eval.benchmarks.harbor.HostConfig.read", return_value=host
                ), patch("eval.benchmarks.harbor.load_preparation", return_value=preparation), patch(
                    "eval.benchmarks.harbor.inspect_preparation", return_value={"available": True}):
                    adapter.run(request_path=request_path, result_path=result_path, variant="full")
                result = json.loads(result_path.read_text())
                if passes:
                    self.assertEqual([t["task_id"] for t in result["trials"]], list(names))
                    self.assertEqual(result["trials"][1]["status"], "failed")
                else:
                    self.assertEqual(result["status"], "failed")
                    self.assertIn("prepared task set", result["errors"]["coverage"])
                    self.assertEqual(len(result["trials"]), len(names))
                    self.assertEqual(result["metrics"], [])
