"""Harbor preflight behavior and failure contracts."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from fruitfly_eval.benchmarks.harbor import _harbor_executable
from fruitfly_eval.benchmarks.swe_bench import SWEBenchAdapter
from tests.support.harbor import load_harbor_agent, prepared_harbor


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_preflight_distinguishes_three_resource_profiles(self) -> None:
        adapter = SWEBenchAdapter(
            harbor_command="/bin/harbor",
            docker_command="/bin/docker",
        )
        with patch(
            "fruitfly_eval.benchmarks.harbor._docker_check",
            return_value={"ok": True, "detail": "ready"},
        ):
            self.assertTrue(adapter.preflight("smoke").available)
            self.assertTrue(adapter.preflight("no_gpu").available)
            self.assertTrue(adapter.preflight("full").available)
            self.assertFalse(adapter.preflight("gpu").available)
            self.assertIn("unknown execution profile", adapter.preflight("gpu").checks[0]["detail"])

    def test_harbor_is_found_next_to_active_python_without_venv_activation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "harbor"
            executable.write_text("", encoding="utf-8")
            executable.chmod(0o755)
            with patch("fruitfly_eval.benchmarks.harbor.sys.executable", str(executable.with_name("python"))):
                with patch("fruitfly_eval.benchmarks.harbor.shutil.which", return_value=None):
                    self.assertEqual(_harbor_executable(), str(executable))

    def test_preflight_explains_docker_engine_failure(self) -> None:
        adapter = SWEBenchAdapter(
            harbor_command="/bin/harbor",
            docker_command="/bin/docker",
        )
        with patch(
            "fruitfly_eval.benchmarks.harbor._docker_check",
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
            "fruitfly_eval.benchmarks.harbor._docker_check",
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
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        host, preparation = prepared_harbor(root, ("swe-bench/psf__requests-1142",))
        command = adapter._command(
            executable="harbor",
            dataset=adapter.descriptor.dataset,
            variant="smoke",
            execution={"attempts": 2, "concurrency": 1},
            jobs_dir=root,
            job_name="job",
            config_path=Path("/tmp/config.yaml"),
            model_catalog=Path("/tmp/models.yaml"),
            profile="default",
            secret_names=("TEST_API_KEY",), host=host, preparation=preparation,
        )
        job = json.loads((root / "harbor-job.json").read_text())
        self.assertEqual(job["agents"][0]["import_path"], "fruitfly_eval.harbor_agent:FruitFlyHarborAgent")
        self.assertEqual(job["tasks"], [{"path": preparation["tasks"][0]["path"], "source": adapter.descriptor.dataset}])
        self.assertEqual(job["n_attempts"], 2)
        self.assertEqual(job["retry"]["max_retries"], 0)
        self.assertNotIn("TEST_API_KEY=secret", command)
