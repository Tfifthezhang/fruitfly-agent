"""Prepared Harbor material, mutable paths, and dependency boundaries offline."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
import sys
from types import ModuleType, SimpleNamespace

import yaml

from fruitfly_eval.benchmarks.harbor import harbor_descriptor
from fruitfly_eval.contracts import EvaluationRequest
from fruitfly_eval.harbor.dependencies import check_dependencies, dependency_mounts, prepare_dependencies
from fruitfly_eval.harbor.controller import environment_snapshot
from fruitfly_eval.harbor.docker import run_container
from fruitfly_eval.harbor.environments import environment_key, probe_environment
from fruitfly_eval.harbor.host import HostConfig
from fruitfly_eval.harbor.material import check_material, digest, prepare_material, tree_identity
from fruitfly_eval.harbor.preparation import inspect, load_preparation, prepare
from fruitfly_eval.harbor.tasks import prepare_tasks, validate_coverage
from tests.support.evaluation import request_payload
from tests.support.harbor import prepared_harbor


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch("fruitfly_eval.harbor.tasks.task_requirements", return_value={
            "gpu_requirements": [], "images": [{"reference": "fixture:v1", "role": "agent", "step": None}], "builds": []}))
        self.enterContext(patch("fruitfly_eval.harbor.preparation.inspect_images", return_value=[]))
        self.host, _ = prepared_harbor(self.root)
        runtime = self.root / "runtime/bin"
        runtime.mkdir(parents=True)
        (runtime / "python").write_text("fake runtime")
        self.descriptor = harbor_descriptor(benchmark_id="other", label="Other", description="Fixture",
            version="1", dataset="example/dataset", smoke_task="example/task-a")
        self.tasks = self.root / "task-inputs"
        self.tasks.mkdir()
        self.host = replace(self.host, task_directory=self.tasks)
        for name in ("task-a", "task-b"):
            directory = self.tasks / name
            (directory / "tests").mkdir(parents=True)
            (directory / "tests/test.sh").write_text("download-helper\nrun-verifier\n")
            (directory / "instruction.md").write_text("Do the task.")
            (directory / "task.toml").write_text('[environment]\ndocker_image = "fixture:v1"\n')
        payload = request_payload()
        payload["benchmark"] = {"id": "other", "variant": "no_gpu"}
        payload["runtime"]["working_directory"] = str(self.root)
        self.request = EvaluationRequest.from_dict(payload)

    def test_machine_paths_resolve_relative_variables_without_freezing_links(self):
        location = self.root / ".fruitfly"
        location.mkdir()
        config = location / "eval-host.yaml"
        config.write_text(yaml.safe_dump({"cache": "../cache", "agent": {
            "python": "/opt/runtime/bin/python", "mounts": [{"source": "${RUNTIME_LOCATION}", "target": "/opt/runtime"}]}}))
        link = self.root / "runtime-link"
        link.symlink_to(self.root / "runtime", target_is_directory=True)
        with patch.dict("os.environ", {"RUNTIME_LOCATION": str(link)}):
            host = HostConfig.read(self.root)
        self.assertEqual(host.mounts[0].source, link)
        self.assertEqual(host.mounts[0].source.resolve(), self.root / "runtime")
        self.assertEqual(host.cache, self.root / "cache")

    def test_controller_records_dependency_conflicts_without_importing_clients_or_saving_secrets(self):
        distributions = [SimpleNamespace(metadata={"Name": "fixture-controller"}, version="1",
                                        requires=["fixture-client>=2", "unused; extra == 'cloud'"]),
                         SimpleNamespace(metadata={"Name": "fixture-client"}, version="1", requires=[])]
        # The optional SDK owns packaging; exercise our audit without installing it.
        requirements = ModuleType("packaging.requirements")
        class Specifier:
            def contains(self, version):
                return False
            def __str__(self):
                return ">=2"
        requirements.Requirement = lambda text: SimpleNamespace(
            name="unused" if "extra" in text else "fixture-client", specifier=Specifier(),
            marker=SimpleNamespace(evaluate=lambda env: False) if "extra" in text else None)
        utils = ModuleType("packaging.utils")
        utils.canonicalize_name = lambda name: name.lower()
        with patch.dict(sys.modules, {"packaging.requirements": requirements, "packaging.utils": utils}), patch(
            "fruitfly_eval.harbor.controller.metadata.distributions", return_value=distributions
        ), patch.dict(
            "os.environ", {"MODEL_API_KEY": "placeholder-do-not-record"}
        ):
            snapshot = environment_snapshot()
        self.assertEqual(snapshot["dependency_check"], "conflicts")
        self.assertEqual(snapshot["dependency_issues"], [
            {"package": "fixture-controller", "requirement": "fixture-client>=2", "installed": "1"}])
        self.assertNotIn("placeholder-do-not-record", json.dumps(snapshot))

    def test_check_detects_controller_changes_and_keeps_declared_conflicts_visible(self):
        def probe(task, *args, **kwargs):
            return {"environment_key": environment_key(task), "images": []}
        with patch("fruitfly_eval.harbor.preparation.probe_environment", side_effect=probe):
            prepared = prepare(self.request, self.descriptor, self.host)
        receipt = json.loads(Path(prepared["receipt"]).read_text())
        conflict = {**receipt["controller"], "dependency_check": "conflicts", "dependency_issues": [{"package": "fixture"}]}
        receipt["controller"] = conflict
        with patch("fruitfly_eval.harbor.preparation.environment_snapshot", return_value=conflict):
            checked = inspect(self.request, self.descriptor, self.host, receipt=receipt)
        self.assertTrue(checked["available"])
        self.assertEqual(next(c for c in checked["checks"] if c["id"] == "controller_dependencies")["status"], "unverified")
        with patch("fruitfly_eval.harbor.preparation.environment_snapshot", return_value={**conflict, "python": "changed"}):
            self.assertFalse(inspect(self.request, self.descriptor, self.host, receipt=receipt)["available"])

    def test_invalid_host_fields_mounts_and_secrets_fail_early(self):
        valid = {"schema_version": 1, "agent": {"python": "/opt/runtime/bin/python", "mounts": [
            {"source": "runtime", "target": "/opt/runtime"}]}}
        variants = [
            {**valid, "unexpected": 1}, {**valid, "schema_version": True},
            {**valid, "environment": {"agent": {"API_KEY": "placeholder"}}},
            {**valid, "environment": {"verifier": {"INDEX_URL": "https://user:password@example.invalid"}}},
            {**valid, "agent": {**valid["agent"], "mounts": "invalid"}},
            {**valid, "agent": {**valid["agent"], "mounts": [{"source": "runtime", "target": "/"}]}},
            {**valid, "agent": {**valid["agent"], "mounts": [{"source": "runtime", "target": "/logs"}]}},
            {**valid, "agent": {**valid["agent"], "library_paths": ["/unmounted/libraries"]}},
            {**valid, "dependencies": {"assets": [{"url": "file:///tmp/asset", "path": "../escape", "sha256": "0" * 64}]}},
            {**valid, "task_patches": [{"task": "*", "path": "solution/solve.sh", "old": "a", "new": "b"}]},
        ]
        path = self.root / "host.yaml"
        for value in variants:
            with self.subTest(value=value):
                path.write_text(yaml.safe_dump(value))
                with self.assertRaises(ValueError):
                    HostConfig.read(self.root, path)

    def test_prepared_source_excludes_secrets_and_sessions(self):
        receipt = prepare_material(self.host, Path(__file__).resolve().parents[2])
        source = Path(receipt["source"])
        self.assertTrue((source / "fruitfly_agent/__init__.py").is_file())
        self.assertTrue((source / "fruitfly_eval/harbor/supervisor.py").is_file())
        self.assertFalse(any(p.name in {".fruitfly", ".venv", ".env", "secrets.env", ".git"} for p in source.rglob("*")))
        check_material(self.host, receipt)
        (source / "fruitfly_agent/__init__.py").write_text("changed")
        with self.assertRaisesRegex(ValueError, "source changed"):
            check_material(self.host, receipt)
        with self.assertRaisesRegex(ValueError, "source changed"):
            prepare_material(self.host, Path(__file__).resolve().parents[2])

    def test_runtime_content_and_link_target_changes_require_preparation(self):
        link = self.root / "current-runtime"
        link.symlink_to(self.root / "runtime", target_is_directory=True)
        host = replace(self.host, mounts=(replace(self.host.mounts[0], source=link),))
        receipt = prepare_material(host, Path(__file__).resolve().parents[2])
        other = self.root / "runtime-next"
        other.mkdir()
        link.unlink()
        link.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "link moved"):
            check_material(host, receipt)
        receipt = prepare_material(self.host, Path(__file__).resolve().parents[2])
        (self.root / "runtime/bin/python").write_text("new interpreter")
        with self.assertRaisesRegex(ValueError, "runtime changed"):
            check_material(self.host, receipt)

    def test_directory_link_contents_are_hashed_and_cycles_fail(self):
        shared = self.root / "shared"
        shared.mkdir()
        (shared / "library").write_text("before")
        (self.root / "runtime/library").symlink_to(shared, target_is_directory=True)
        before = tree_identity(self.root / "runtime")
        (shared / "library").write_text("after")
        self.assertNotEqual(before, tree_identity(self.root / "runtime"))
        (shared / "loop").symlink_to(self.root / "runtime", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "cycle"):
            tree_identity(self.root / "runtime")

    def test_prepare_freezes_full_tasks_and_exact_declared_name(self):
        (self.tasks / "task-b/task.toml").write_text('[task]\nname = "example/renamed"\n[environment]\ndocker_image = "fixture:v1"\n')
        tasks = prepare_tasks(self.host, self.descriptor, "full")["tasks"]
        self.assertEqual([t["id"] for t in tasks], ["task-a", "example/renamed"])
        (self.tasks / "task-a/tests/test.sh").write_text("upstream changed")
        self.assertIn("download-helper", (Path(tasks[0]["path"]) / "tests/test.sh").read_text())
        for names, attempts, valid in ((["task-a", "example/renamed"], 1, True),
                                      (["task-a"], 1, False), (["task-a", "example/renamed"], 2, False),
                                      (["task-a", "example/renamed"] * 2, 2, True)):
            with self.subTest(names=names, attempts=attempts):
                trials = [{"task_id": n} for n in names]
                if valid:
                    validate_coverage(tasks, trials, attempts)
                else:
                    with self.assertRaisesRegex(ValueError, "attempt count"):
                        validate_coverage(tasks, trials, attempts)

    def test_explicit_setup_patch_is_isolated_audited_and_exact(self):
        host = replace(self.host, task_patches=({"task": "example/task-a", "path": "tests/test.sh",
                                               "old": "download-helper", "new": "/opt/pinned/helper"},))
        tasks = prepare_tasks(host, self.descriptor, "smoke")["tasks"]
        self.assertEqual([t["id"] for t in tasks], ["example/task-a"])
        self.assertIn("+", tasks[0]["patches"][0]["diff"])
        self.assertIn("download-helper", (self.tasks / "task-a/tests/test.sh").read_text())
        self.assertIn("/opt/pinned/helper", (Path(tasks[0]["path"]) / "tests/test.sh").read_text())
        broken = replace(host, task_patches=({**host.task_patches[0], "old": "missing"},))
        with self.assertRaisesRegex(ValueError, "exactly once"):
            prepare_tasks(broken, self.descriptor, "smoke")
        (self.tasks / "task-a/tests/external").symlink_to(self.root / "runtime/bin/python")
        with self.assertRaisesRegex(ValueError, "external link"):
            prepare_tasks(host, self.descriptor, "smoke")

    def test_assets_are_hashed_read_only_and_cache_is_separate(self):
        binary = self.root / "uv"
        binary.write_bytes(b"pinned fixture executable")
        asset = {"url": binary.as_uri(), "path": "bin/uv", "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "executable": True}
        host = replace(self.host, assets=(asset,), uv="/opt/fruitfly-eval-dependencies/assets/bin/uv", offline=True)
        with patch("httpx.stream", side_effect=AssertionError("unexpected network")):
            receipt = prepare_dependencies(host, "unused-docker")
            check_dependencies(host, receipt)
            self.assertEqual(prepare_dependencies(host, "unused-docker")["id"], receipt["id"])
        mounts = dependency_mounts(host)
        self.assertTrue(mounts[0]["read_only"])
        self.assertNotIn("read_only", mounts[1])
        (host.cache / "dependencies/assets/bin/uv").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            check_dependencies(host, receipt)
        bad = replace(host, assets=({**asset, "sha256": "0" * 64},))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            prepare_dependencies(bad, "unused-docker")

    def test_cache_warming_runs_once_and_never_runs_offline_during_prepare(self):
        host = replace(self.host, offline=True, preparation=({"image": "fixture:v1", "command": "warm-exact-packages"},))
        with patch("fruitfly_eval.harbor.dependencies.image_identity", return_value="sha256:image"), patch(
                "fruitfly_eval.harbor.dependencies.run_container", return_value=subprocess.CompletedProcess([], 0)) as run:
            first = prepare_dependencies(host, "docker")
            second = prepare_dependencies(host, "docker")
        self.assertEqual(first, second)
        run.assert_called_once()
        command = run.call_args.args[1]
        self.assertFalse(any("UV_OFFLINE" in arg or "PIP_NO_INDEX" in arg for arg in command))
        self.assertIn("sha256:image", command)
        self.assertEqual(first["verifier_execution"], "unverified until a complete smoke trial")

    def test_timed_out_preparation_retires_its_container(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1] == "run":
                raise subprocess.TimeoutExpired(command, 1)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("fruitfly_eval.harbor.docker.subprocess.run", side_effect=run), self.assertRaises(subprocess.TimeoutExpired):
            run_container("docker", ["image", "command"], timeout=1)
        self.assertEqual(calls[1], ["docker", "rm", "-f", "-v", calls[0][3]])

    def test_preparation_and_check_are_benchmark_independent_and_detect_drift(self):
        def probe(task, runtime, docker, directory, *, host):
            return {"environment_key": environment_key(task), "images": [{"reference": "fixture:v1", "id": "sha256:first"}], "detail": "fake imports passed"}
        with patch("fruitfly_eval.harbor.preparation.probe_environment", side_effect=probe) as probes:
            prepared = prepare(self.request, self.descriptor, self.host)
        self.assertEqual(prepared["task_count"], 2)
        probes.assert_called_once()  # Same environment and runtime, distinct tasks.
        receipt = load_preparation(self.host, self.descriptor, "no_gpu")
        with patch("fruitfly_eval.harbor.preparation.image_identity", return_value="sha256:first"):
            self.assertTrue(inspect(self.request, self.descriptor, self.host)["available"])
        with patch("fruitfly_eval.harbor.preparation.image_identity", return_value="sha256:changed"):
            self.assertFalse(inspect(self.request, self.descriptor, self.host)["available"])
        (Path(receipt["tasks"][0]["path"]) / "instruction.md").write_text("drift")
        with self.assertRaisesRegex(ValueError, "prepared task changed"):
            load_preparation(self.host, self.descriptor, "no_gpu")

    def test_check_never_silently_prepares_missing_material(self):
        with patch("fruitfly_eval.harbor.preparation.prepare", side_effect=AssertionError("unexpected preparation")):
            result = inspect(self.request, self.descriptor, self.host)
        self.assertFalse(result["available"])
        self.assertIn("run eval prepare", result["checks"][0]["detail"])

    def test_check_detects_verifier_image_drift_and_rejects_incomplete_or_older_preparation(self):
        def probe(task, runtime, docker, directory, *, host):
            return {"environment_key": environment_key(task), "images": [
                {"reference": "agent:v1", "id": "sha256:agent"},
                {"reference": "verifier:v1", "id": "sha256:verifier"}]}
        with patch("fruitfly_eval.harbor.preparation.probe_environment", side_effect=probe):
            result = prepare(self.request, self.descriptor, self.host)
        path = Path(result["receipt"])
        receipt = load_preparation(self.host, self.descriptor, "no_gpu")
        with patch("fruitfly_eval.harbor.preparation.image_identity", side_effect=lambda docker, image:
                   "sha256:agent" if image == "agent:v1" else "sha256:changed"), patch(
            "fruitfly_eval.harbor.preparation.probe_environment", side_effect=AssertionError("check must not start environments")
        ):
            checked = inspect(self.request, self.descriptor, self.host)
        self.assertFalse(checked["available"])
        self.assertEqual([c["image"] for c in checked["checks"] if c["status"] == "failed"], ["verifier:v1"])
        receipt["schema_version"] = 1
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "run eval prepare again"):
            load_preparation(self.host, self.descriptor, "no_gpu")
        receipt["schema_version"] = 3
        receipt["environments"] = []
        receipt["id"] = digest({key: value for key, value in receipt.items() if key != "id"})
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "probes do not cover"):
            load_preparation(self.host, self.descriptor, "no_gpu")

    def test_separate_verifier_task_is_frozen_without_changing_official_mode(self):
        (self.tasks / "task-a/task.toml").write_text('[verifier]\nenvironment_mode = "separate"\n[environment]\ndocker_image = "fixture:v1"\n')
        tasks = prepare_tasks(self.host, self.descriptor, "smoke")["tasks"]
        self.assertEqual(tasks[0]["configuration"]["verifier"]["environment_mode"], "separate")
        self.assertEqual((Path(tasks[0]["path"]) / "task.toml").read_bytes(),
                         (self.tasks / "task-a/task.toml").read_bytes())

    def test_dockerfile_and_compose_probes_use_public_harbor_factory_and_cleanup(self):
        directory = self.root / "check"
        environment = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(),
            exec=AsyncMock(return_value=SimpleNamespace(return_code=0, stdout="imports passed", stderr="")))
        factory = SimpleNamespace(create_environment_from_config=Mock(return_value=environment))
        class Paths:
            def __init__(self, trial_dir):
                self.directory = trial_dir
            def mkdir(self):
                self.directory.mkdir(parents=True, exist_ok=True)
            def chmod_dir(self):
                pass
        definition = {"role": "agent", "step": None, "context": str(self.tasks / "task-a/environment"),
                      "configuration": {}, "user": None, "name": "task-a"}
        modules = {}
        for name, attributes in {
            "harbor.environments.factory": {"EnvironmentFactory": factory},
            "harbor.models.task.config": {"EnvironmentConfig": SimpleNamespace(model_validate=lambda value:
                SimpleNamespace(build_timeout_sec=1, resolve_baseline=lambda: "official-network-policy"))},
            "harbor.models.trial.config": {"EnvironmentConfig": SimpleNamespace(model_validate=lambda value: SimpleNamespace(**value))},
            "harbor.models.trial.paths": {"TrialPaths": Paths},
        }.items():
            module = ModuleType(name)
            module.__dict__.update(attributes)
            modules[name] = module
        _, receipt = prepared_harbor(self.root)
        task = {"id": "example/task-a", "path": str(self.tasks / "task-a"), "image": None, "configuration": {}}
        def docker(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, "owned-container\n" if command[1] == "ps" else "fixture:v1 sha256:fixture\n", "")
        with patch.dict(sys.modules, modules), patch("fruitfly_eval.harbor.environments.environment_definitions", return_value=[definition]), patch(
            "fruitfly_eval.harbor.environments.subprocess.run", side_effect=docker), patch(
            "fruitfly_eval.harbor.environments.retire_projects"
        ) as retire:
            probed = probe_environment(task, receipt["runtime"], "docker", directory, host=self.host)
            self.assertEqual(probed["images"], [{"reference": "fixture:v1", "id": "sha256:fixture"}])
            environment.start.assert_awaited_once_with(force_build=False)
            environment.stop.assert_awaited_once_with(delete=False)
            self.assertEqual(retire.call_args.args[0], [factory.create_environment_from_config.call_args.kwargs["session_id"]])
            self.assertTrue(all(m["read_only"] for m in factory.create_environment_from_config.call_args.kwargs["config"].mounts))
            environment.stop.reset_mock()
            environment.exec.side_effect = RuntimeError("probe error")
            with self.assertRaisesRegex(RuntimeError, "probe error"):
                probe_environment(task, receipt["runtime"], "docker", directory, host=self.host)
            environment.stop.assert_awaited_once_with(delete=False)
