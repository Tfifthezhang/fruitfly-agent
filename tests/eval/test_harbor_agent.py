"""Harbor agent behavior and failure contracts."""
from __future__ import annotations
import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
import tempfile
from unittest.mock import AsyncMock, patch
from tests.support.harbor import InstalledAgentDouble, load_harbor_agent, installed_agent_inputs


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_subscription_access_is_removed_before_trial_returns(self) -> None:
        from contextlib import asynccontextmanager
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        installed_agent_inputs(agent, root)
        agent.model_relay_directory = str(root / 'relay')
        agent.model_relay_settings = {}
        agent.model_catalog_path = root / 'models.yaml'
        agent.profile = 'default'
        agent.render_instruction = lambda instruction: instruction
        operations = []
        async def execute(_environment, *, command, env, **kwargs):
            operations.append((command, dict(env)))
            return SimpleNamespace(stdout='[1000, 1000]')
        agent.exec_as_agent = AsyncMock(side_effect=execute)
        agent.exec_as_root = AsyncMock(side_effect=execute)
        environment = SimpleNamespace(upload_file=AsyncMock())
        retired = []
        @asynccontextmanager
        async def access(*args):
            try:
                yield {'models': {'fixture': {'grant': 'private-fixture-grant',
                    'socket': '/opt/fruitfly-model-relay/trial-fixture/model.sock'}}}
            finally:
                retired.append(True)
                self.assertNotIn(" remove ", operations[-1][0])
        with patch('fruitfly_eval.harbor.model_access.task_access', access):
            asyncio.run(agent.run('task', environment, SimpleNamespace(metadata=None)))
        self.assertEqual(retired, [True])
        self.assertIn('access_files remove ', operations[-1][0])
        run_env = next(env for command, env in operations if 'harbor.supervisor' in command)
        self.assertRegex(run_env['FRUITFLY_MODEL_ACCESS_FILE'],
                         r'/model-access/[0-9a-f]{32}/model-access.json$')
        self.assertNotIn('private-fixture-grant', str(operations))
        self.assertNotIn('FRUITFLY_MODEL_ACCESS_FILE', agent.runtime_environment)

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
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        installed_agent_inputs(agent, root)
        agent.profile = "default"
        agent.render_instruction = lambda instruction: instruction
        agent.exec_as_agent = AsyncMock()
        context = SimpleNamespace(metadata=None)

        asyncio.run(agent.run("task", object(), context))

        self.assertIsNone(context.metadata)
        agent.exec_as_agent.assert_awaited_once()
        command = agent.exec_as_agent.call_args.kwargs["command"]
        self.assertIn("--unrestricted", command)
        self.assertNotIn("--approve-tools", command)
        self.assertNotIn("--permissions", command)
        self.assertIn("/logs/agent/session.jsonl -- task", command)
        self.assertTrue(agent.capabilities.atif)
