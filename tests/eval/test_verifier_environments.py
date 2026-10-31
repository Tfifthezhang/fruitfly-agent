"""Independent verifier environments preserve Harbor ownership and isolation."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fruitfly_eval.benchmarks.harbor import HarborBenchmarkAdapter, harbor_descriptor
from fruitfly_eval.harbor.environments import environment_config, environment_definitions, environment_key, probe_environment
from fruitfly_eval.harbor.lifecycle import owned_projects, record_environment, retire_containers
from fruitfly_eval.harbor.material import digest
from fruitfly_eval.harbor.tasks import registry_tasks
from tests.support.harbor import load_harbor_environment, prepared_harbor


PreparedDockerEnvironment = load_harbor_environment()


def modules_with(attributes):
    modules = {}
    for name, values in attributes.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        modules[name] = module
    return modules


def environment_model(**values):
    return SimpleNamespace(model_dump=lambda **kwargs: dict(values), **values)


class VerifierEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.host, self.receipt = prepared_harbor(self.root)
        self.task = {"id": "example/task", "path": str(self.root / "task"),
                     "configuration": {"environment": {"cpus": 2}}}
        self.runtime = self.receipt["runtime"]

    def test_every_harbor_benchmark_selects_the_same_environment_extension(self):
        host = replace(self.host, offline=True, verifier_env={"VERIFIER_SETTING": "value"})
        for name in ("swe-like", "workbuddy-like"):
            with self.subTest(name=name):
                adapter = HarborBenchmarkAdapter()
                adapter.descriptor = harbor_descriptor(benchmark_id=name, label=name, description="Fixture",
                    version="1", dataset=f"example/{name}@1.0.0", smoke_task="example/task")
                command = adapter._command(executable="harbor", dataset=adapter.descriptor.dataset,
                    variant="smoke", execution={}, jobs_dir=self.root, job_name=name,
                    config_path=self.root / "config", model_catalog=self.root / "models", profile="default",
                    secret_names=("MODEL_API_KEY",), host=host, preparation=self.receipt)
                payload = json.loads(Path(command[3]).read_text())
                config = payload["environment"]
                self.assertEqual(config["import_path"], "fruitfly_eval.harbor.docker_environment:PreparedDockerEnvironment")
                self.assertEqual([m["target"] for m in config["mounts"]],
                                 ["/opt/runtime", "/installed-agent/fruitfly/source"])
                self.assertEqual([m["target"] for m in config["kwargs"]["dependency_mounts"]],
                                 ["/opt/fruitfly-eval-dependencies/assets", "/opt/fruitfly-eval-dependencies/cache"])
                self.assertEqual(payload["verifier"]["env"]["UV_OFFLINE"], "1")
                self.assertEqual(payload["verifier"]["env"]["VERIFIER_SETTING"], "value")
                self.assertNotIn("MODEL_API_KEY", json.dumps(config))

    def test_extension_adds_only_dependencies_and_records_both_exact_sessions(self):
        trial = self.root / "job/task__A1"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text(json.dumps({"trial_name": trial.name}))
        config = environment_config(self.host, self.runtime)
        resources = SimpleNamespace(cpus=4, gpus=1, gpu_types=["H100"])
        for role, session in (("agent", "task__A1__env"), ("verifier", "task__A1__verifier__grade")):
            with self.subTest(role=role):
                mounts = [{"type": "bind", "source": str(trial / "verifier"), "target": "/logs/verifier"}]
                if role == "agent":
                    mounts.extend(config["mounts"])
                environment = PreparedDockerEnvironment(
                    environment_dir=self.root / role, environment_name="task", session_id=session,
                    trial_paths=SimpleNamespace(trial_dir=trial), task_env_config=resources,
                    mounts=mounts, **config["kwargs"])
                actual = environment.constructor["mounts"]
                targets = [m["target"] for m in actual]
                self.assertIn("/logs/verifier", targets)
                self.assertEqual(actual[-2]["read_only"], True)
                self.assertFalse(actual[-1].get("read_only", False))
                self.assertIs(environment.constructor["task_env_config"], resources)
                if role == "verifier":
                    self.assertNotIn("/opt/runtime", targets)
                    self.assertNotIn("/installed-agent/fruitfly/source", targets)
        self.assertEqual(owned_projects(self.root), ["task__a1__env", "task__a1__verifier__grade"])

    def test_dependency_mount_conflict_fails_before_environment_construction(self):
        target = "/opt/fruitfly-eval-dependencies/assets"
        with self.assertRaisesRegex(ValueError, "conflicts with Harbor mount"):
            PreparedDockerEnvironment(dependency_mounts=[{"target": target}],
                                      mounts=[{"target": target}])

    def test_definition_resolution_delegates_inheritance_and_step_modes_to_harbor(self):
        agent = environment_model(cpus=4, gpus=1, gpu_types=["H100"])
        inherited = environment_model(cpus=4, gpus=1, gpu_types=["H100"])
        overridden = environment_model(cpus=2, gpus=0)
        steps = [SimpleNamespace(name=name, verifier=SimpleNamespace(user=user))
                 for name, user in (("shared", None), ("inherited", None), ("own", "grader"))]
        paths = SimpleNamespace(environment_dir=self.root / "environment", tests_dir=self.root / "tests",
                                step_tests_dir=lambda name: self.root / "steps" / name / "tests",
                                validate_input_tree=Mock())
        paths.step_tests_dir("own").mkdir(parents=True)
        config = SimpleNamespace(environment=agent, agent=SimpleNamespace(user="solver"),
                                 verifier=SimpleNamespace(user="default-grader"), steps=steps)
        model = SimpleNamespace(config=config, paths=paths, short_name="task")
        resolver = Mock(side_effect=[None, inherited, overridden])
        modules = modules_with({
            "harbor.models.task.task": {"Task": Mock(return_value=model)},
            "harbor.models.task.verifier_mode": {"resolve_effective_verifier_env_config": resolver},
        })
        with patch.dict("sys.modules", modules):
            definitions = environment_definitions(self.task)
        self.assertEqual([d["role"] for d in definitions], ["agent", "verifier", "verifier"])
        self.assertEqual([d["step"] for d in definitions], [None, "inherited", "own"])
        self.assertEqual(definitions[1]["configuration"]["gpus"], 1)
        self.assertEqual(definitions[1]["context"], str(paths.tests_dir))
        self.assertEqual(definitions[1]["user"], "default-grader")
        self.assertEqual(definitions[2]["configuration"]["gpus"], 0)
        self.assertEqual(definitions[2]["context"], str(paths.step_tests_dir("own")))
        self.assertEqual(definitions[2]["user"], "grader")
        self.assertEqual([call.args for call in resolver.call_args_list], [(config, step) for step in steps])
        config.steps = None
        resolver.side_effect = [inherited]
        with patch.dict("sys.modules", modules):
            self.assertEqual(environment_definitions(self.task)[1]["step"], None)
        self.assertEqual(resolver.call_args.args, (config, None))

    def test_verifier_files_and_configuration_change_probe_identity(self):
        tests = Path(self.task["path"]) / "tests"
        tests.mkdir(parents=True)
        (tests / "Dockerfile").write_text("FROM fixture:v1")
        first = environment_key(self.task)
        self.task["configuration"]["verifier"] = {"environment_mode": "separate"}
        second = environment_key(self.task)
        self.assertNotEqual(first, second)
        (tests / "Dockerfile").write_text("FROM fixture:v2")
        self.assertNotEqual(second, environment_key(self.task))

    def test_verifier_probe_uses_its_context_resources_and_dependencies_without_agent_imports(self):
        definition = {"role": "verifier", "step": "grade", "context": str(self.root / "step-tests"),
                      "configuration": {"cpus": 4, "gpus": 1}, "user": "grader", "name": "task"}
        environment = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(),
            exec=AsyncMock(return_value=SimpleNamespace(return_code=0, stdout="dependencies ready", stderr="")))
        factory = SimpleNamespace(create_environment_from_config=Mock(return_value=environment))
        class Paths:
            def __init__(self, trial_dir):
                self.trial_dir = trial_dir
            def mkdir(self):
                self.trial_dir.mkdir(parents=True, exist_ok=True)
            def chmod_dir(self):
                pass
        validate = Mock(side_effect=lambda value: SimpleNamespace(**value, build_timeout_sec=10,
                                                                  resolve_baseline=lambda: "task-policy"))
        modules = modules_with({
            "harbor.environments.factory": {"EnvironmentFactory": factory},
            "harbor.models.task.config": {"EnvironmentConfig": SimpleNamespace(model_validate=validate)},
            "harbor.models.trial.config": {"EnvironmentConfig": SimpleNamespace(model_validate=lambda value: SimpleNamespace(**value))},
            "harbor.models.trial.paths": {"TrialPaths": Paths},
        })
        def docker(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, "container\n" if command[1] == "ps" else "verifier:v1 sha256:verifier\n", "")
        host = replace(self.host, verifier_env={"VERIFIER_SETTING": "yes"}, offline=True)
        with patch.dict("sys.modules", modules), patch(
            "fruitfly_eval.harbor.environments.environment_definitions", return_value=[definition]
        ), patch("fruitfly_eval.harbor.environments.subprocess.run", side_effect=docker), patch(
            "fruitfly_eval.harbor.environments.retire_projects"
        ) as retire:
            receipt = probe_environment(self.task, self.runtime, "docker", self.root / "probes", host=host)
            arguments = factory.create_environment_from_config.call_args.kwargs
            self.assertEqual(arguments["mounts"], [])
            self.assertEqual(arguments["environment_dir"], self.root / "step-tests")
            self.assertEqual(arguments["task_env_config"].gpus, 1)
            self.assertEqual(arguments["network_policy"], "task-policy")
            self.assertIn("dependency_mounts", arguments["config"].kwargs)
            executed = environment.exec.call_args.kwargs
            self.assertNotIn("fruitfly_agent", executed["command"])
            self.assertNotIn("PYTHONPATH", executed["env"])
            self.assertEqual(executed["env"]["UV_OFFLINE"], "1")
            self.assertEqual(executed["env"]["VERIFIER_SETTING"], "yes")
            self.assertEqual(executed["user"], "grader")
            self.assertEqual(receipt["roles"][0]["step"], "grade")
            self.assertEqual(receipt["images"], [{"reference": "verifier:v1", "id": "sha256:verifier"}])
            environment.stop.assert_awaited_once_with(delete=False)
            retire.assert_called_once()
            environment.exec.return_value = SimpleNamespace(return_code=1, stdout="dependency error", stderr="")
            environment.stop.reset_mock()
            with self.assertRaisesRegex(ValueError, "verifier environment probe failed"):
                probe_environment(self.task, self.runtime, "docker", self.root / "probes", host=host)
            self.assertEqual((self.root / "probes/0-verifier/probe.log").read_text(), "dependency error")
            environment.stop.assert_awaited_once_with(delete=False)
            for failure in (RuntimeError("start failed"), asyncio.CancelledError()):
                with self.subTest(failure=type(failure).__name__):
                    environment.start.side_effect = failure
                    environment.stop.reset_mock()
                    retire.reset_mock()
                    with self.assertRaises(type(failure)):
                        probe_environment(self.task, self.runtime, "docker", self.root / "probes", host=host)
                    environment.stop.assert_awaited_once_with(delete=False)
                    retire.assert_called_once()

    def test_shortened_verifier_session_is_retired_by_exact_record_not_prefix(self):
        trial = self.root / "job/trial"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text('{"trial_name":"trial"}')
        session = "a-truncated-verifier-name__c6a79523"
        record_environment(trial, session)
        self.assertEqual(owned_projects(self.root), [session, "trial__env"])
        record = trial / "fruitfly-environments" / (digest(session) + ".json")
        data = json.loads(record.read_text())
        data["trial_directory"] = str(self.root / "unrelated")
        record.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "cannot establish container ownership"):
            owned_projects(self.root)

    def test_cleanup_removes_agent_and_verifier_containers_without_selecting_another_job(self):
        trial = self.root / "job/trial"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text('{"trial_name":"trial"}')
        record_environment(trial, "trial__verifier__grade")
        live = {"trial__env": ["agent-container"], "trial__verifier__grade": ["verifier-container"],
                "other-job": ["unrelated-container"]}
        queries = []
        def docker(command, **kwargs):
            output = ""
            if command[1] == "ps":
                project = command[-1].removeprefix("label=com.docker.compose.project=")
                queries.append(project)
                output = "\n".join(live[project])
            elif command[1:4] == ["rm", "-f", "-v"]:
                for containers in live.values():
                    containers[:] = [c for c in containers if c not in command[4:]]
            return subprocess.CompletedProcess(command, 0, output, "")
        with patch("fruitfly_eval.harbor.lifecycle.subprocess.run", side_effect=docker):
            removed = retire_containers(self.root, "docker", {})
        self.assertEqual(removed, ["agent-container", "verifier-container"])
        self.assertEqual(live["other-job"], ["unrelated-container"])
        self.assertEqual(set(queries), {"trial__env", "trial__verifier__grade"})

    def test_versioned_datasets_use_harbor_version_field(self):
        task_id = SimpleNamespace(get_name=lambda: "example/task")
        config = SimpleNamespace(get_task_id=lambda: task_id)
        dataset = Mock(return_value=SimpleNamespace(get_task_configs=AsyncMock(return_value=[config])))
        client = Mock(return_value=SimpleNamespace(download_tasks=AsyncMock(return_value=SimpleNamespace(
            results=[SimpleNamespace(path=self.root / "downloaded")]))))
        modules = modules_with({"harbor.models.job.config": {"DatasetConfig": dataset},
                                "harbor.tasks.client": {"TaskClient": client}})
        with patch.dict("sys.modules", modules):
            result = asyncio.run(registry_tasks("example/dataset@4.0.0", self.root, ("example/task",)))
        dataset.assert_called_once_with(name="example/dataset", version="4.0.0", task_names=["example/task"])
        self.assertEqual(result, [("example/task", self.root / "downloaded")])
