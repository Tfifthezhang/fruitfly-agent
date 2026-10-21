"""Host strategies change actual tool behavior without benchmark-aware tools."""
import asyncio
import contextlib
import io
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.env import ExecOptions
from fruitfly_agent.core.tool_runtime.authorization import AuthorizationRequest
from fruitfly_agent.lab.catalog import PermissionPolicy, apply_permission_policy
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.run import cli
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.run import _args


def workspace_files(root):
    (root / "models.yaml").write_text(yaml.safe_dump({"models": {"fixture": {
        "provider": "openai", "model": "fixture", "api_key_env": "FIXTURE_MODEL_KEY",
        "context_window": 32768, "max_output_tokens": 1024}}}))
    (root / "config.yaml").write_text(yaml.safe_dump({"schema_version": 1, "default_profile": "fixture",
        "profiles": {"fixture": {"model": {"catalog": "models.yaml", "profile": "fixture"},
            "mechanisms": [{"id": n} for n in ("local-env", "read-tool", "write-tool", "bash-tool")]}}}))


class ExecutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_file_and_shell_tools_are_guarded_or_unrestricted_by_injection(self):
        for unrestricted in (False, True):
            with self.subTest(unrestricted=unrestricted), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "workspace"
                root.mkdir()
                workspace_files(root)
                (root / ".env").write_text("fixture protected file")
                outside = base / "outside.txt"
                outside.write_text("fixture external file")
                binary = base / "bin"
                binary.mkdir()
                executable = binary / "fruitfly-fixture-command"
                executable.write_text("#!/bin/sh\nprintf task-environment\n")
                executable.chmod(0o755)
                provider = FauxProvider()
                provider.respond_tool_call("read", {"path": str(outside)})
                provider.respond_tool_call("read", {"path": ".env"})
                provider.respond_tool_call("write", {"path": ".env", "content": "fixture replacement"})
                provider.respond_tool_call("bash", {"command": "fruitfly-fixture-command > command.txt"})
                provider.respond_text("done")
                registry = Mock(create=Mock(return_value=provider))
                environment = {"FIXTURE_MODEL_KEY": "offline-fixture", "PATH": str(binary) + ":/usr/bin:/bin"}
                policy = PermissionPolicy.unrestricted(root) if unrestricted else None
                with patch.dict(os.environ, {"PATH": environment["PATH"]}):
                    factory = RunApplicationFactory(cwd=root, environment=environment, config_path="config.yaml",
                        provider_registry=registry, permission_policy=policy)
                    handle = await factory.open(resume=False, session_path=None)
                    try:
                        handle.activate_callback()
                        result = await handle.session.submit("exercise the configured tools")
                        tools = [m for m in result.messages if m.role == "toolResult"]
                        self.assertEqual(len(tools), 4)
                        self.assertEqual([m.is_error for m in tools], [not unrestricted] * 4)
                        self.assertEqual((root / "command.txt").exists(), unrestricted)
                        if unrestricted:
                            self.assertEqual((root / "command.txt").read_text(), "task-environment")
                            self.assertEqual((root / ".env").read_text(), "fixture replacement")
                            self.assertEqual(handle.manifest["permissions"]["mode"], "unrestricted")
                            self.assertEqual(handle.manifest["permissions"]["environment"], "inherited")
                        else:
                            self.assertEqual((root / ".env").read_text(), "fixture protected file")
                        self.assertIsNone(handle.authorization.pending)
                        self.assertEqual(handle.authorization.status()["grants"], 0)
                    finally:
                        await handle.close()

    async def test_unrestricted_binding_retains_backend_and_allows_undeclared_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = LocalEnv(directory)
            backend.with_permissions = Mock(side_effect=AssertionError("guard adapter must not run"))
            policy = PermissionPolicy.unrestricted(root)
            config = AgentLoopConfig(provider=FauxProvider(), model="fixture", env=backend)
            confirm = Mock(side_effect=AssertionError("approval must not run"))
            audit = []
            configured = apply_permission_policy(config, policy, confirm=confirm, audit=audit.append)
            self.assertIs(configured.env, backend)
            request = AuthorizationRequest("one", "custom", {"fixture": "not part of audit"}, None)
            async with configured.tool_authorizer.authorize(request) as decision:
                self.assertTrue(decision.allowed)
            self.assertEqual(audit[0]["allowed"], True)
            self.assertNotIn("not part of audit", str(audit))
            signal = asyncio.Event()
            signal.set()
            with self.assertRaises(asyncio.CancelledError):
                async with configured.tool_authorizer.authorize(request, signal=signal):
                    self.fail("cancelled call must not start")
            result = await configured.env.exec("sleep 10", ExecOptions(timeout_seconds=0.03))
            self.assertTrue(result.unwrap().cancelled)
            confirm.assert_not_called()
            backend.with_permissions.assert_not_called()

    async def test_cli_selects_unrestricted_once_and_rejects_nonfresh_launches(self):
        for args in (_args(unrestricted=True), _args(task="fixture", unrestricted=True, resume=True),
                     _args(task="fixture", unrestricted=True, approve_tools=True)):
            with self.subTest(args=args), patch.object(cli, "RunApplicationFactory") as factory, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(await cli.run_cli(args), 2)
                factory.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace_files(root)
            (root / ".env").write_text("fixture content")
            provider = FauxProvider()
            provider.respond_tool_call("read", {"path": ".env"})
            provider.respond_text("done")
            registry = Mock(create=Mock(return_value=provider))
            with patch.object(cli, "load_env", return_value={"FIXTURE_MODEL_KEY": "fixture"}), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry", return_value=registry
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(await cli.run_cli(_args(cwd=directory, config="config.yaml", task="fixture", unrestricted=True)), 0)
            tool = next(m for m in provider.calls[-1]["messages"] if m.role == "toolResult")
            self.assertFalse(tool.is_error)
            self.assertIn("fixture content", tool.text)

    def test_strategy_environment_preparation_preserves_task_path_without_filtering(self):
        environment = {"PATH": "/task/bin", "HOME": "/task/home", "FIXTURE_SETTING": "present"}
        unrestricted = PermissionPolicy.unrestricted(Path.cwd())
        self.assertEqual(unrestricted.prepare_environment(environment), environment)
        self.assertNotIn("HOME", PermissionPolicy.prepare_environment(environment))
        self.assertNotIn("FIXTURE_SETTING", PermissionPolicy.prepare_environment(environment))
        self.assertEqual(environment["PATH"], "/task/bin")

    def test_cli_has_no_configuration_source_or_permission_preference_flags(self):
        parser = cli.create_parser()
        for args in (["--permissions", "settings.yaml"], ["--approval-mode", "auto"], ["--default-config"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser.parse_args(args)
