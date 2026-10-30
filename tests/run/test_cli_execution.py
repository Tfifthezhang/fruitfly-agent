"""Cli execution behavior and failure contracts."""
from __future__ import annotations
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import ConfigurationLaunchResult
from fruitfly_agent.run import DataArtifactStore, RunConfigurationController
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run import cli
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog, _args


class CliRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_headless_commands_require_explicit_tool_approval(self):
        for approved in (False, True):
            with self.subTest(approved=approved), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
                provider = FauxProvider()
                provider.respond_tool_call("bash", {"command": "printf verified > output.txt"})
                provider.respond_text("done")
                registry = Mock()
                registry.create.return_value = provider
                with patch("fruitfly_agent.run.runtime.assembly.default_registry", return_value=registry), \
                        contextlib.redirect_stdout(io.StringIO()):
                    result = await cli.run_cli(_args(task="write output", cwd=tmp, approve_tools=approved))
                self.assertEqual(result, 0)
                self.assertEqual((root / "output.txt").exists(), approved)
                tool = next(m for m in provider.calls[-1]["messages"] if m.role == "toolResult")
                self.assertEqual(tool.is_error, not approved)
                if approved:
                    self.assertEqual((root / "output.txt").read_text(), "verified")

    async def test_automatic_approval_keeps_protected_file_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            (root / ".env").write_text("FIXTURE_ONLY=placeholder\n")
            provider = FauxProvider()
            provider.respond_tool_call("read", {"path": ".env"})
            provider.respond_text("done")
            registry = Mock()
            registry.create.return_value = provider
            with patch("fruitfly_agent.run.runtime.assembly.default_registry", return_value=registry), \
                    contextlib.redirect_stdout(io.StringIO()):
                await cli.run_cli(_args(task="read file", cwd=tmp, approve_tools=True))
            tool = next(m for m in provider.calls[-1]["messages"] if m.role == "toolResult")
            self.assertTrue(tool.is_error)
            self.assertNotIn("placeholder", tool.text)

    async def test_resume_uses_current_bindings_instead_of_historical_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            store = DataArtifactStore(root / ".fruitfly" / "artifacts")
            ref = store.put_text("Pinned skill catalog guidance")
            session_path = root / "candidate-session.jsonl"
            registry = Mock()
            providers = []

            def create_provider(*_):
                provider = FauxProvider()
                provider.respond_text("candidate used")
                providers.append(provider)
                return provider

            registry.create.side_effect = create_provider

            initial_factory = RunApplicationFactory(
                cwd=root,
                environment={},
                provider_registry=registry,
                data_artifact_bindings={
                    "skill-catalog.guidance": ref.artifact_id,
                },
            )
            initial = await initial_factory.open(
                resume=False,
                session_path=session_path,
            )
            initial.activate_callback()
            initial_manifest = initial.manifest
            await initial.session.submit("exercise the bound guidance")
            self.assertIn(
                "Pinned skill catalog guidance",
                providers[0].calls[0]["system_prompt"],
            )
            await initial.close()

            with Session(session_path) as session:
                session.append(
                    "message",
                    {"message": UserMessage(content="continue").to_dict()},
                )

            # Current bindings govern continuation; historical guidance is not required.
            resumed_factory = RunApplicationFactory(
                cwd=root,
                environment={},
                provider_registry=registry,
            )
            resumed = await resumed_factory.open(
                resume=True,
                session_path=session_path,
            )
            try:
                self.assertNotEqual(resumed.manifest, initial_manifest)
                self.assertEqual([], resumed.manifest.get("data_artifacts", []))
                stage = next(
                    item for item in resumed.components["context-pipeline"].stages
                    if item.stage_id == "skill-catalog"
                )
                transformed = stage.mechanism.transform(
                    ContextFrame("base", (), (), "offline-model", 32)
                )
                self.assertIsNone(transformed)
            finally:
                await resumed.close()

    async def test_one_shot_persists_a_complete_turn(self) -> None:
        provider = FauxProvider()
        provider.respond_text("visible answer")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            session_path = root / "session.jsonl"
            event_path = root / "live-events.jsonl"
            output = io.StringIO()
            registry = Mock()
            registry.create.return_value = provider
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry",
                return_value=registry,
            ), patch.object(
                cli, "TerminalConfigurationFrontend"
            ) as startup, contextlib.redirect_stdout(output), patch.dict(
                os.environ, {"FRUITFLY_EVENT_STREAM_PATH": str(event_path)}
            ):
                code = await cli.run_cli(
                    _args(
                        task="offline task", cwd=tmp,
                        session=str(session_path),
                    )
                )

            with Session(session_path) as session:
                roles = [message.role for message in session.messages()]
                bindings = [
                    entry
                    for entry in session.read_all()
                    if entry.payload.get("kind") == "runtimeManifest"
                ]
            events = [json.loads(line) for line in event_path.read_text().splitlines()]

        self.assertEqual(code, 0)
        startup.assert_not_called()
        self.assertIn("🪰 visible answer", output.getvalue())
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(events[0]["type"], "run_started")
        self.assertEqual(events[-1]["type"], "run_finished")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].payload["manifest"]["schema_version"], 7)
        self.assertEqual(
            bindings[0].payload["manifest"]["models"]["main"]["model"],
            "offline-model",
        )

    async def test_resume_continues_with_a_changed_model_in_the_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            model_path = root / ".fruitfly/models.yaml"
            _write_catalog(model_path, {"offline": "model-old"})
            first = FauxProvider()
            first.respond_text("saved")
            registry = Mock()
            registry.create.return_value = first
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry",
                return_value=registry,
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    await cli.run_cli(
                        _args(task="first", cwd=tmp, session=str(path))
                    ),
                    0,
                )
            _write_catalog(model_path, {"offline": "model-new"})
            first.respond_text("continued")
            errors = io.StringIO()
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry",
                return_value=registry,
            ), contextlib.redirect_stderr(errors):
                code = await cli.run_cli(
                    _args(task="resume", cwd=tmp, session=str(path), resume=True)
                )

        self.assertEqual(code, 0)
        self.assertEqual("model-new", first.calls[-1]["model"])
        self.assertEqual("first", first.calls[-1]["messages"][0].content)

    async def test_interactive_resume_injects_next_session_controller(self) -> None:
        captured: list[tuple[int, object]] = []

        class FakeFrontend:
            def __init__(self, app) -> None:
                captured.append(
                    (app.status.message_count, app.configuration)
                )

            async def run(self) -> int:
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            _write_catalog(root / ".fruitfly/models.yaml", {"offline": "offline-model"})
            provider = FauxProvider()
            provider.respond_text("saved")
            registry = Mock()
            registry.create.return_value = provider
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry",
                return_value=registry,
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    await cli.run_cli(
                        _args(task="first", cwd=tmp, session=str(path))
                    ),
                    0,
                )
            startup = Mock()
            startup.run.return_value = ConfigurationLaunchResult(start=True)
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "TerminalConfigurationFrontend", return_value=startup
            ), patch(
                "fruitfly_agent.run.runtime.assembly.default_registry",
                return_value=registry,
            ), patch.object(cli, "TerminalFrontend", FakeFrontend):
                code = await cli.run_cli(
                    _args(cwd=tmp, session=str(path), resume=True)
                )

        self.assertEqual(code, 0)
        startup.run.assert_called_once_with(configure=False)
        self.assertEqual(captured[0][0], 2)
        self.assertIsInstance(captured[0][1], RunConfigurationController)
