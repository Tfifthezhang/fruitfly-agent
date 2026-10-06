from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import tempfile
import asyncio
import sys
import unittest
from unittest.mock import patch
from fruitfly_agent.interactive import EvaluationLaunchRequest
from fruitfly_agent.run.evaluation import (
    FULL_EVALUATION_TIMEOUT_SECONDS,
    SMOKE_EVALUATION_TIMEOUT_SECONDS,
    RunEvaluationController,
    _default_timeout_seconds,
)


class _Configuration:
    def snapshot(self):
        return SimpleNamespace(
            mechanisms=(SimpleNamespace(mechanism_id="opro", label="OPRO"),)
        )


class _Application:
    running = False
    pending_count = 0
    runtime_manifest = {
        "digest": "sha256:test",
        "components": [
            {
                "id": "opro",
                "contributions": [{"layer": "optimization", "family": "context"}],
                "activation": "runtime",
                "parameters": {},
            }
        ],
    }


class EvalBridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_default_timeout_does_not_apply_smoke_limit_to_full_profiles(self) -> None:
        self.assertEqual(
            _default_timeout_seconds("smoke"), SMOKE_EVALUATION_TIMEOUT_SECONDS
        )
        self.assertEqual(
            _default_timeout_seconds("no_gpu"), FULL_EVALUATION_TIMEOUT_SECONDS
        )
        self.assertEqual(
            _default_timeout_seconds("gpu"), FULL_EVALUATION_TIMEOUT_SECONDS
        )

    def test_controller_environment_includes_factory_loaded_secrets(self) -> None:
        factory = SimpleNamespace(
            cwd=Path("/tmp"),
            environment={"FRUITFLY_TEST_SECRET": "loaded-from-dotenv"},
        )
        controller = RunEvaluationController(_Application(), factory)
        environment = controller._environment()
        self.assertEqual(
            environment["FRUITFLY_TEST_SECRET"], "loaded-from-dotenv"
        )

    async def test_stderr_and_non_json_stdout_are_visible_before_child_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            release = cwd / "release"
            factory = SimpleNamespace(
                cwd=cwd, environment={},
                selection=SimpleNamespace(config_path=cwd / "config.yaml", profile=SimpleNamespace(profile_id="test")),
            )
            controller = RunEvaluationController(_Application(), factory)
            updates = []
            create_process = asyncio.create_subprocess_exec
            script = (
                "import sys,time,json; from pathlib import Path; "
                "print('raw stdout',flush=True); "
                "sys.stderr.buffer.write('Ｈｉ stderr'.encode()); sys.stderr.flush(); "
                f"p=Path({str(release)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)'); "
                "print(json.dumps({'type':'finished','status':'failed','evaluation_id':'test'}),flush=True)"
            )

            async def launch(*args, **kwargs):
                return await create_process(sys.executable, "-u", "-c", script, **kwargs)

            async def observe(event):
                updates.append(event)
                if event.get("source") == "eval stderr":
                    release.touch()

            with patch("fruitfly_agent.run.evaluation.asyncio.create_subprocess_exec", new=launch):
                result = await asyncio.wait_for(controller.run(EvaluationLaunchRequest("current_setup", "terminal-bench", "smoke"), on_event=observe), timeout=5)
            self.assertEqual(result.status, "failed")
            self.assertIn("raw stdout", "".join(e.get("text", "") for e in updates))
            self.assertIn("Ｈｉ stderr", "".join(e.get("text", "") for e in updates))
            self.assertEqual(result.detail, "Ｈｉ stderr")

    async def test_catalog_and_blocked_report_work_outside_source_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            factory = SimpleNamespace(
                cwd=cwd,
                environment={},
                configuration=_Configuration(),
                selection=SimpleNamespace(
                    config_path=cwd / "config.yaml",
                    profile=SimpleNamespace(profile_id="test"),
                ),
            )
            controller = RunEvaluationController(_Application(), factory)
            environment = controller._environment()
            environment["PATH"] = ""  # Child must remain offline even when Docker is installed.
            updates = []

            async def observe(event):
                updates.append(event)

            with patch.object(controller, "_environment", return_value=environment):
                snapshot = controller.snapshot()
                result = await controller.run(
                    EvaluationLaunchRequest(
                        "current_setup", "swe-bench", "smoke"
                    ), on_event=observe,
                )

            self.assertEqual(snapshot.benchmarks[0].benchmark_id, "swe-bench")
            self.assertEqual(snapshot.mechanisms[0].mechanism_id, "opro")
            self.assertEqual(result.status, "blocked")
            self.assertTrue(Path(result.report_json).is_file())
            self.assertEqual(
                [item["type"] for item in updates],
                ["planned", "preflight", "report_written", "finished"],
            )


if __name__ == "__main__":
    unittest.main()
