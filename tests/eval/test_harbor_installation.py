"""Harbor installation behavior and failure contracts."""
from __future__ import annotations
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
import tempfile
import zipfile
from unittest.mock import AsyncMock, patch
from eval.benchmarks.swe_bench import SWEBenchAdapter
from eval.installation import resolve_installation, validate_installation
from tests.support.evaluation import request_payload
from tests.support.harbor import load_harbor_agent, prepared_harbor, installed_agent_inputs


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_prepared_install_does_not_install_python_or_agent_dependencies(self) -> None:
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        installed_agent_inputs(agent, root)
        agent.exec_as_agent = AsyncMock()
        agent.exec_as_root = AsyncMock()
        environment = SimpleNamespace(upload_dir=AsyncMock(), upload_file=AsyncMock())
        asyncio.run(agent.install(environment))
        commands = [call.kwargs["command"] for mock in (agent.exec_as_agent, agent.exec_as_root)
                    for call in mock.await_args_list]
        self.assertTrue(any("/opt/runtime/bin/python" in command for command in commands))
        self.assertFalse(any(word in command for command in commands for word in ("pip install", "venv", "apt", "curl")))
        environment.upload_dir.assert_not_called()
        self.assertTrue(all("/source/" not in call.args[1] for call in environment.upload_file.await_args_list))

    def test_missing_preparation_fails_before_container_access(self) -> None:
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        agent.config_path = root / "config.yaml"
        agent.exec_as_agent = AsyncMock()
        with self.assertRaisesRegex(ValueError, "run eval prepare"):
            asyncio.run(agent.install(object()))
        agent.exec_as_agent.assert_not_called()

    def test_invalid_installation_material_fails_before_environment_access(self) -> None:
        from eval.contracts import EvaluationRequest
        from eval.harbor.preparation import prepare
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        host, _ = prepared_harbor(root)
        (root / "runtime").mkdir()
        with patch("eval.harbor.preparation.probe_environment") as probe:
            with self.assertRaisesRegex(ValueError, "incomplete FruitFlyAgent source"):
                prepare(EvaluationRequest.from_dict(request_payload()), SWEBenchAdapter().descriptor, host, package=root)
        probe.assert_not_called()
        with self.assertRaisesRegex(ValueError, "FRUITFLY_EVAL_PACKAGE"):
            resolve_installation(None, checkout=root)

    def test_wheel_preparation_freezes_source_without_installation(self) -> None:
        from eval.harbor.material import source_snapshot
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        wheel = root / "fruitfly_agent-0.1-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("fruitfly_agent/__init__.py", "")
            archive.writestr("eval/__init__.py", "")
            archive.writestr("fruitfly_agent-0.1.dist-info/METADATA", "Name: fruitfly-agent\nVersion: 0.1\n")
            archive.writestr("fruitfly_agent-0.1.dist-info/licenses/LICENSE", "Fixture license")
        self.assertEqual(validate_installation(wheel), wheel.resolve())
        source_snapshot(wheel, root / "snapshot")
        self.assertTrue((root / "snapshot/fruitfly_agent/__init__.py").is_file())
        self.assertTrue((root / "snapshot/eval/__init__.py").is_file())
        self.assertEqual((root / "snapshot/licenses/LICENSE").read_text(), "Fixture license")

    def test_source_preparation_stages_build_inputs_without_local_state(self) -> None:
        from eval.harbor.material import source_snapshot
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source_snapshot(Path(__file__).resolve().parents[2], root / "source")
        staged_names = [str(path.relative_to(root / "source")) for path in (root / "source").rglob("*") if path.is_file()]
        for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml",
                     "fruitfly_agent/__init__.py", "eval/__init__.py"):
            self.assertIn(name, staged_names)
        for name in ('fruitfly_agent/providers/services.yaml',
                     'fruitfly_agent/run/configuration/templates/default-config.yaml',
                     'fruitfly_agent/experiments/templates/tasks/native.yaml'):
            self.assertIn(name, staged_names)
        self.assertFalse(any("__pycache__" in name or ".env" in name for name in staged_names))

    def test_installation_rejects_wrong_project_and_corrupt_wheel(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name, content in (("broken.whl", b"not a wheel"), ("missing.whl", None)):
            with self.subTest(name=name):
                path = root / name
                if content is not None:
                    path.write_bytes(content)
                with self.assertRaises(ValueError):
                    validate_installation(path)
        path = root / "other-0.1-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("fruitfly_agent/__init__.py", "")
            archive.writestr("eval/__init__.py", "")
            archive.writestr("other-0.1.dist-info/METADATA", "Name: other\nVersion: 0.1\n")
        with self.assertRaisesRegex(ValueError, "fruitfly-agent version 0.1"):
            validate_installation(path)

    def test_installed_agent_reports_project_version(self) -> None:
        import tomllib

        project = Path(__file__).resolve().parents[2] / "pyproject.toml"
        version = tomllib.loads(project.read_text())["project"]["version"]
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        self.assertEqual("0.1", version)
        self.assertEqual(version, agent.version())
