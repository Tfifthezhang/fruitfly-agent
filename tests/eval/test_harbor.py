from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import AsyncMock, patch

import yaml

from eval.benchmarks.harbor import (
    _condition_runtime_files,
    _harbor_executable,
    _load_harbor_job_result,
    _forward_agent_events,
    _forward_logs,
    _forward_trial_results,
    _run_harbor_job,
    parse_harbor_job_result,
)
from eval.benchmarks.swe_bench import SWEBenchAdapter
from tests.support.harbor import InstalledAgentDouble, load_harbor_agent

FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_harbor_job_streams_then_archives_display_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            stream = agent / "live-events.jsonl"
            script = (
                "from pathlib import Path; import time; "
                f"Path({str(stream)!r}).write_text(" 
                "'{\"type\":\"run_started\",\"run_id\":\"one\"}\\n'); "
                "time.sleep(0.5)"
            )
            updates = []
            code, detail = _run_harbor_job(
                [sys.executable, "-c", script], environment={}, timeout=5,
                condition_root=root, progress=updates.append,
                condition_id="current",
            )
            self.assertEqual((code, detail), (0, ""))
            self.assertEqual(next(item for item in updates if item["type"] == "agent_event")["event"]["type"], "run_started")
            self.assertFalse(stream.exists())
            self.assertIn('"type":"run_started"', stream.with_name("events.jsonl").read_text())

    def test_quiet_harbor_job_emits_progress_before_it_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            released = root / "released"
            script = (
                "from pathlib import Path; import time; "
                f"p=Path({str(released)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)')"
            )
            updates = []

            def observe(event):
                updates.append(event)
                released.touch()  # The child cannot finish until progress arrives.

            code, detail = _run_harbor_job(
                [sys.executable, "-c", script], environment={}, timeout=5,
                condition_root=root, progress=observe, condition_id="current",
            )
            self.assertEqual((code, detail), (0, ""))
            event = updates[0]
            self.assertEqual(event["type"], "job_progress")
            self.assertEqual(event["agent_runs_started"], 0)
            self.assertEqual(event["completed"], 0)
            self.assertGreaterEqual(event["elapsed_seconds"], 0)

    def test_runner_output_is_streamed_in_full_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            released = root / "released"
            script = (
                "from pathlib import Path; import sys,time; "
                "print('early output',flush=True); "
                f"p=Path({str(released)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)'); "
                "sys.stderr.write('E'*10000+'tail without newline')"
            )
            updates = []

            def observe(event):
                updates.append(event)
                if event["type"] == "log" and "early output" in event["text"]:
                    released.touch()

            code, _ = _run_harbor_job(
                [sys.executable, "-u", "-c", script], environment={}, timeout=5,
                condition_root=root, progress=observe, condition_id="current",
            )
            self.assertEqual(code, 0)
            expected = "early output\n" + "E"*10000 + "tail without newline"
            self.assertEqual((root / "harbor.log").read_text(), expected)
            self.assertEqual("".join(e["text"] for e in updates if e["type"] == "log"), expected)

    def test_setup_and_exception_logs_forward_partial_lines_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            setup = agent / "setup.log"
            setup.write_bytes("ＯＫ\n".encode() + b"partial")
            offsets, fragments, updates = {}, {}, []
            _forward_logs(root, "current", offsets, fragments, updates.append)
            self.assertEqual(updates[0]["text"], "ＯＫ\n")
            with setup.open("ab") as handle:
                handle.write(b" completed\n")
            (agent.parent / "exception.txt").write_text("timeout traceback")
            _forward_logs(root, "current", offsets, fragments, updates.append, final=True)
            _forward_logs(root, "current", offsets, fragments, updates.append, final=True)
            self.assertEqual([e["text"] for e in updates], ["ＯＫ\n", "partial completed\n", "timeout traceback"])

    def test_existing_python_install_skips_apt_and_uv(self) -> None:
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        agent.source_root = Path("/source")
        agent.config_path = Path("/config.yaml")
        agent.model_catalog_path = Path("/models.yaml")
        agent.ensure_system_dependencies = AsyncMock()
        agent.exec_as_root = AsyncMock()
        environment = SimpleNamespace(
            exec=AsyncMock(return_value=SimpleNamespace(return_code=0)),
            upload_dir=AsyncMock(), upload_file=AsyncMock(),
        )
        asyncio.run(agent.install(environment))
        agent.ensure_system_dependencies.assert_not_called()
        command = agent.exec_as_root.call_args.kwargs["command"]
        self.assertIn("python3 -m venv", command)
        self.assertIn("-m pip install", command)
        self.assertNotIn("uv", command)
        self.assertNotIn("apt", command)
        environment.upload_dir.assert_awaited_once()

    def test_installed_agent_reports_project_version(self) -> None:
        import tomllib

        project = Path(__file__).resolve().parents[2] / "pyproject.toml"
        version = tomllib.loads(project.read_text())["project"]["version"]
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        self.assertEqual("0.1", version)
        self.assertEqual(version, agent.version())

    def test_setup_logging_keeps_output_and_nonzero_exit(self) -> None:
        import subprocess
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        agent.options = None
        with tempfile.TemporaryDirectory() as directory:
            async def execute(instance, environment, command, **kwargs):
                # Exercise the exact shell wrapper without requiring root.
                command = command.replace("/logs/agent", directory)
                return subprocess.run(["bash", "-o", "pipefail", "-c", command], capture_output=True, text=True)

            with patch.object(InstalledAgentDouble, "_exec", new=execute):
                result = asyncio.run(agent._exec(None, "printf 'visible error\\n'; exit 7", user="root"))
            self.assertEqual(result.returncode, 7)
            self.assertIn("visible error", (Path(directory) / "setup.log").read_text())

    def test_transient_registry_failure_retries_before_job_and_keeps_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            count = root / "count"
            script = (
                "from pathlib import Path; import sys; "
                f"p=Path({str(count)!r}); "
                "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
                "print('ConnectError: Error getting dataset terminal-bench@2.0' if n==1 else 'registry ready',flush=True); "
                "sys.exit(1 if n==1 else 0)"
            )
            updates = []
            code, _ = _run_harbor_job([sys.executable, "-u", "-c", script], environment={}, timeout=5, condition_root=root, progress=updates.append, condition_id="current")
            self.assertEqual(code, 0)
            self.assertEqual(count.read_text(), "2")
            self.assertIn("ConnectError", (root / "harbor-attempt-1.log").read_text())
            self.assertEqual((root / "harbor.log").read_text(), "registry ready\n")
            text = "".join(e["text"] for e in updates if e["type"] == "log")
            self.assertEqual(text.count("ConnectError:"), 1)
            self.assertIn("retry 2/3", text)

    def test_registry_failure_after_job_creation_is_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "job").mkdir()
            script = "print('ConnectError: Error getting dataset terminal-bench@2.0'); raise SystemExit(1)"
            code, _ = _run_harbor_job([sys.executable, "-c", script], environment={}, timeout=5, condition_root=root, progress=None, condition_id="current")
            self.assertEqual(code, 1)
            self.assertFalse((root / "harbor-attempt-1.log").exists())

    def test_live_transport_forwards_complete_events_and_trial_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            stream = agent / "live-events.jsonl"
            updates = []
            offsets = {}
            fragments = {}
            stream.write_bytes(b'{"type":"run_started","run_id":"one"}\n{"type":')
            _forward_agent_events(root, "current", offsets, fragments, updates.append)
            self.assertEqual(len(updates), 1)
            self.assertEqual(next(item for item in updates if item["type"] == "agent_event")["event"]["type"], "run_started")
            with stream.open("ab") as handle:
                handle.write(b'"run_finished","run_id":"one"}\n')
            _forward_agent_events(root, "current", offsets, fragments, updates.append)
            self.assertEqual(updates[-1]["event"]["type"], "run_finished")
            trial_result = agent.parent / "result.json"
            trial_result.write_text('{"status":"completed"}', encoding="utf-8")
            seen = set()
            _forward_trial_results(root, "current", seen, updates.append)
            _forward_trial_results(root, "current", seen, updates.append)
            self.assertEqual([item["type"] for item in updates].count("trial_finished"), 1)

    def test_preflight_distinguishes_three_resource_profiles(self) -> None:
        adapter = SWEBenchAdapter(
            harbor_command="/bin/harbor",
            docker_command="/bin/docker",
        )
        with patch(
            "eval.benchmarks.harbor._docker_check",
            return_value={"ok": True, "detail": "ready"},
        ):
            self.assertTrue(adapter.preflight("smoke").available)
            self.assertTrue(adapter.preflight("no_gpu").available)
            self.assertFalse(adapter.preflight("gpu").available)
            self.assertIn("GPU", adapter.preflight("gpu").checks[-1]["detail"])

    def test_harbor_is_found_next_to_active_python_without_venv_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "harbor"
            executable.write_text("", encoding="utf-8")
            executable.chmod(0o755)
            with patch("eval.benchmarks.harbor.sys.executable", str(executable.with_name("python"))):
                with patch("eval.benchmarks.harbor.shutil.which", return_value=None):
                    self.assertEqual(_harbor_executable(), str(executable))

    def test_preflight_explains_docker_engine_failure(self) -> None:
        adapter = SWEBenchAdapter(
            harbor_command="/bin/harbor",
            docker_command="/bin/docker",
        )
        with patch(
            "eval.benchmarks.harbor._docker_check",
            side_effect=(
                {"ok": False, "detail": "Docker engine is unavailable"},
                {"ok": True, "detail": "2.0"},
            ),
        ):
            result = adapter.preflight("smoke")
        self.assertFalse(result.available)
        self.assertEqual(result.checks[2]["id"], "docker_daemon")
        self.assertIn("unavailable", result.checks[2]["detail"])

    def test_preflight_explains_missing_compose_v2(self) -> None:
        adapter = SWEBenchAdapter(
            harbor_command="/bin/harbor",
            docker_command="/bin/docker",
        )
        with patch(
            "eval.benchmarks.harbor._docker_check",
            side_effect=(
                {"ok": True, "detail": "28.0"},
                {"ok": False, "detail": "Docker Compose v2 is unavailable"},
            ),
        ):
            result = adapter.preflight("smoke")
        self.assertFalse(result.available)
        self.assertEqual(result.checks[3]["id"], "docker_compose")
        self.assertIn("Compose v2", result.checks[3]["detail"])

    def test_smoke_command_limits_tasks_without_replacing_the_agent(self) -> None:
        adapter = SWEBenchAdapter()
        command = adapter._command(
            executable="harbor",
            dataset=adapter.descriptor.dataset,
            variant="smoke",
            execution={"attempts": 2, "concurrency": 1},
            jobs_dir=Path("/tmp/jobs"),
            job_name="job",
            source_root=Path("/tmp/source"),
            config_path=Path("/tmp/config.yaml"),
            model_catalog=Path("/tmp/models.yaml"),
            profile="default",
            secret_names=("TEST_API_KEY",),
        )
        self.assertIn("eval.harbor_agent:FruitFlyHarborAgent", command)
        self.assertEqual(
            command[command.index("--include-task-name") + 1],
            "swe-bench/psf__requests-1142",
        )
        self.assertEqual(command[command.index("--n-tasks") + 1], "1")
        self.assertNotIn("TEST_API_KEY=secret", command)

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
            condition_id="current",
        )
        self.assertEqual([item["status"] for item in trials], ["passed", "failed"])
        values = {item["name"]: item["value"] for item in metrics}
        self.assertEqual(values["success_rate"], 0.5)
        self.assertEqual(values["official_reward"], 0.5)
        self.assertEqual(values["input_tokens"], 18)
        self.assertEqual(values["latency_ms"], 2000)

    def test_empty_harbor_job_is_not_reported_as_a_completed_benchmark(self) -> None:
        with self.assertRaisesRegex(ValueError, "no trials"):
            parse_harbor_job_result({"trial_results": []}, condition_id="current")

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
                _load_harbor_job_result(job / "result.json"),
                condition_id="current",
                expected_manifest_digest="sha256:frozen",
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
                _load_harbor_job_result(path)

    def test_frozen_runtime_digest_mismatch_is_an_infrastructure_error(self) -> None:
        trials, metrics = parse_harbor_job_result(
            {
                "trial_results": [
                    {
                        "id": "trial-1",
                        "task_name": "task-a",
                        "verifier_result": {"rewards": {"reward": 1}},
                        "agent_result": {
                            "metadata": {"runtime_manifest_digest": "sha256:other"}
                        },
                    }
                ]
            },
            condition_id="current",
            expected_manifest_digest="sha256:frozen",
        )
        self.assertEqual(trials[0]["status"], "error")
        self.assertEqual(trials[0]["error"]["type"], "RuntimeManifestMismatch")
        values = {item["name"]: item["value"] for item in metrics}
        self.assertEqual(values["success_rate"], 0)
        self.assertEqual(values["error_rate"], 1)

    def test_harbor_setup_error_is_not_hidden_by_missing_manifest(self) -> None:
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
            condition_id="current",
            expected_manifest_digest="sha256:frozen",
        )
        self.assertEqual(trials[0]["error"]["type"], "RuntimeError")
        self.assertIn("Docker Hub", trials[0]["error"]["message"])
        self.assertEqual(
            next(item["value"] for item in metrics if item["name"] == "error_rate"),
            1.0,
        )

    def test_condition_config_relocates_catalog_and_applies_only_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yaml"
            models_path = root / "models.yaml"
            config_path.write_text(
                """schema_version: 1
default_profile: default
profiles:
  default:
    model:
      catalog: models.yaml
      profile: test
    mechanisms:
      - id: compaction
        enabled: true
        parameters: {}
""",
                encoding="utf-8",
            )
            models_path.write_text(
                """models:
  test:
    provider:
      type: openai
      api_key_env: TEST_API_KEY
    model: test-model
    context_window: 8192
    max_output_tokens: 1024
""",
                encoding="utf-8",
            )
            output = root / "condition"
            output.mkdir()
            generated, copied_models, secret_names = _condition_runtime_files(
                runtime={"config_path": str(config_path), "profile": "default"},
                condition={
                    "mechanism_overrides": {"compaction": {"enabled": False}}
                },
                output_dir=output,
            )
            payload = yaml.safe_load(generated.read_text(encoding="utf-8"))
            profile = payload["profiles"]["default"]
            enabled = {item["id"]: item["enabled"] for item in profile["mechanisms"]}
            self.assertEqual(
                profile["model"]["catalog"],
                "/installed-agent/fruitfly/runtime/models.yaml",
            )
            self.assertEqual(enabled, {"compaction": False})
            self.assertEqual(copied_models.read_text(), models_path.read_text())
            self.assertEqual(secret_names, ("TEST_API_KEY",))

    def test_installed_agent_exports_native_manifest_and_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logs_dir = Path(directory)
            entries = (
                {
                    "id": 1,
                    "parentId": None,
                    "type": "meta",
                    "kind": "runtimeManifest",
                    "manifest": {"digest": "sha256:native"},
                },
                {
                    "id": 2,
                    "parentId": None,
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "usage": {"inputTokens": 13, "outputTokens": 5},
                    },
                },
            )
            (logs_dir / "session.jsonl").write_text(
                "".join(json.dumps(entry) + "\n" for entry in entries),
                encoding="utf-8",
            )
            agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
            agent.logs_dir = logs_dir
            context = SimpleNamespace(
                metadata=None,
                n_input_tokens=None,
                n_output_tokens=None,
            )

            agent.populate_context_post_run(context)

            self.assertEqual(
                context.metadata["runtime_manifest_digest"], "sha256:native"
            )
            self.assertEqual(context.metadata["harness"], "fruitfly-agent")
            self.assertTrue(context.metadata["native_tools_preserved"])
            self.assertEqual(context.n_input_tokens, 13)
            self.assertEqual(context.n_output_tokens, 5)

    def test_installed_agent_leaves_context_empty_until_logs_are_downloaded(self) -> None:
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        agent.profile = "default"
        agent.render_instruction = lambda instruction: instruction
        agent.exec_as_agent = AsyncMock()
        context = SimpleNamespace(metadata=None)

        asyncio.run(agent.run("task", object(), context))

        self.assertIsNone(context.metadata)
        agent.exec_as_agent.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
