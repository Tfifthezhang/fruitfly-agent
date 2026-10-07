from __future__ import annotations

import contextlib

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import (
    ConfigurationLaunchResult,
    InteractiveSession,
    RuntimeHandle,
)


from fruitfly_agent.run import DataArtifactStore, RunConfigurationController, create_parser, resolve_session_path
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run import cli
from fruitfly_agent.run.application import discover_resumable_sessions


from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog, _args, _seed_resumable_session


class CliSurfaceTest(unittest.TestCase):
    def test_parser_keeps_only_stable_launch_and_profile_options(self) -> None:
        args = create_parser().parse_args(["do work", "--profile", "research"])

        self.assertEqual(args.task, "do work")
        self.assertEqual(args.profile, "research")
        self.assertFalse(args.resume)
        self.assertFalse(
            any(
                hasattr(args, name)
                for name in ("provider", "model", "memory_profile", "models_file")
            )
        )

    def test_feature_specific_legacy_flag_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            create_parser().parse_args(["--memory-profile", "obsolete"])

    def test_resume_ignores_newer_manifest_only_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = _args()
            fresh = resolve_session_path(args, root)
            self.assertEqual(fresh.parent, root / ".fruitfly" / "sessions")
            self.assertRegex(fresh.name, r"^\d{8}T\d{6}Z-[0-9a-f]{8}\.jsonl$")

            sessions = root / ".fruitfly" / "sessions"
            sessions.mkdir(parents=True)
            older = sessions / "older.jsonl"
            newer = sessions / "newer.jsonl"
            _seed_resumable_session(older)
            _seed_resumable_session(newer, message=None)
            os.utime(older, ns=(1, 1))
            os.utime(newer, ns=(2, 2))
            args.resume = True
            self.assertEqual(resolve_session_path(args, root), older.resolve())

    def test_session_discovery_filters_current_locked_and_incompatible_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / ".fruitfly" / "sessions"
            current = sessions / "current.jsonl"
            compatible = sessions / "compatible.jsonl"
            incompatible = sessions / "incompatible.jsonl"
            locked = sessions / "locked.jsonl"
            _seed_resumable_session(current)
            _seed_resumable_session(compatible)
            _seed_resumable_session(incompatible, digest="sha256:other")
            _seed_resumable_session(locked)
            os.utime(compatible, ns=(4, 4))

            with Session(locked):
                found = discover_resumable_sessions(
                    root,
                    current_path=current,
                    manifest_digest="sha256:test",
                )

        self.assertEqual([Path(item.path).name for item in found], ["compatible.jsonl"])
        self.assertEqual(found[0].message_count, 1)
        self.assertEqual(found[0].profile, "default")
        self.assertEqual(found[0].model, "offline-model")

class CliRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_cwd_selects_env_file_and_process_values_take_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("TEST_SETTING=file\nFILE_ONLY=present\n", encoding="utf-8")
            launch = root / "launch"
            launch.mkdir()
            (launch / ".env").write_text("TEST_SETTING=wrong-workspace\nFILE_ONLY=wrong\n", encoding="utf-8")
            setup = Mock()
            setup.run.return_value = ConfigurationLaunchResult(start=False)
            with patch.dict(os.environ, {"TEST_SETTING": "process"}, clear=True), patch.object(
                cli, "RunApplicationFactory"
            ) as factory, patch.object(cli, "TerminalConfigurationFrontend", return_value=setup), patch.object(
                Path, "cwd", return_value=launch
            ):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 0)
            self.assertEqual(factory.call_args.kwargs["cwd"], root.resolve())
            environment = factory.call_args.kwargs["environment"]
            self.assertEqual(environment.get("TEST_SETTING"), "process")
            self.assertEqual(environment.get("FILE_ONLY"), "present")

    async def test_resume_reloads_the_exact_bound_data_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"offline": "offline-model"})
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

            # The resumed runtime resolves the artifact recorded in the Session,
            # even if the caller no longer supplies the original binding.
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
                self.assertEqual(resumed.manifest, initial_manifest)
                stage = next(
                    item for item in resumed.components["context-pipeline"].stages
                    if item.stage_id == "skill-catalog"
                )
                transformed = stage.mechanism.transform(
                    ContextFrame("base", (), (), "offline-model", 32)
                )
                self.assertIn(
                    "Pinned skill catalog guidance",
                    transformed.frame.system_prompt,
                )
            finally:
                await resumed.close()

    async def test_incomplete_first_run_exits_without_creating_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"a": "model-a", "b": "model-b"})
            setup = Mock()
            setup.run.return_value = ConfigurationLaunchResult(start=False)
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "TerminalConfigurationFrontend", return_value=setup
            ), patch.object(cli, "AgentApplication") as application_type:
                code = await cli.run_cli(_args(cwd=tmp))

        self.assertEqual(code, 0)
        application_type.assert_not_called()

    async def test_complete_interactive_run_still_uses_startup_before_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"only": "model-a"})
            setup = Mock()
            setup.run.return_value = ConfigurationLaunchResult(start=False)
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "TerminalConfigurationFrontend", return_value=setup
            ), patch.object(cli, "AgentApplication") as application_type:
                code = await cli.run_cli(_args(cwd=tmp))

        self.assertEqual(code, 0)
        setup.run.assert_called_once_with(editable=True)
        application_type.assert_not_called()

    async def test_one_shot_persists_a_complete_turn(self) -> None:
        provider = FauxProvider()
        provider.respond_text("visible answer")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / "models.yaml", {"offline": "offline-model"})
            session_path = root / "session.jsonl"
            event_path = root / "live-events.jsonl"
            output = io.StringIO()
            registry = Mock()
            registry.create.return_value = provider
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.assembly.default_registry",
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
        self.assertEqual(bindings[0].payload["manifest"]["schema_version"], 5)
        self.assertEqual(
            bindings[0].payload["manifest"]["models"]["main"]["model"],
            "offline-model",
        )

    async def test_resume_rejects_a_changed_profile_before_runtime_assembly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            model_path = root / "models.yaml"
            _write_catalog(model_path, {"offline": "model-old"})
            first = FauxProvider()
            first.respond_text("saved")
            registry = Mock()
            registry.create.return_value = first
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.assembly.default_registry",
                return_value=registry,
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    await cli.run_cli(
                        _args(task="first", cwd=tmp, session=str(path))
                    ),
                    0,
                )
            _write_catalog(model_path, {"offline": "model-new"})
            errors = io.StringIO()
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.assembly.default_registry",
                return_value=registry,
            ), contextlib.redirect_stderr(errors):
                code = await cli.run_cli(
                    _args(task="resume", cwd=tmp, session=str(path), resume=True)
                )

        self.assertEqual(code, 2)
        self.assertIn("start a new session", errors.getvalue())

    async def test_interactive_resume_injects_next_session_controller(self) -> None:
        captured: list[tuple[int, object, object]] = []

        class FakeFrontend:
            def __init__(self, app, *, evaluation=None) -> None:
                captured.append(
                    (app.status.message_count, app.configuration, evaluation)
                )

            async def run(self) -> int:
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            _write_catalog(root / "models.yaml", {"offline": "offline-model"})
            provider = FauxProvider()
            provider.respond_text("saved")
            registry = Mock()
            registry.create.return_value = provider
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.assembly.default_registry",
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
                "fruitfly_agent.run.assembly.default_registry",
                return_value=registry,
            ), patch.object(cli, "TerminalFrontend", FakeFrontend):
                code = await cli.run_cli(
                    _args(cwd=tmp, session=str(path), resume=True)
                )

        self.assertEqual(code, 0)
        startup.run.assert_called_once_with(editable=False)
        self.assertEqual(captured[0][0], 2)
        self.assertIsInstance(captured[0][1], RunConfigurationController)
        self.assertIsNotNone(captured[0][2])

    async def test_confirmed_runtime_configuration_rebuilds_a_fresh_session(self) -> None:
        captured_paths: list[str] = []

        class FakeFrontend:
            def __init__(self, app, *, evaluation=None) -> None:
                self.app = app
                self.evaluation = evaluation
                captured_paths.append(app.status.session_path)

            async def run(self) -> int:
                await self.app.rebuild()
                captured_paths.append(self.app.status.session_path)
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configuration = Mock()

            class FakeFactory:
                def __init__(self) -> None:
                    self.configuration = configuration
                    self.opens = 0
                    self.reloads = 0

                async def open(self, *, resume, session_path):
                    self.opens += 1
                    path = session_path or self.new_session_path()
                    session = InteractiveSession(
                        AgentLoopConfig(provider=FauxProvider(), model="offline"),
                        session_path=path,
                    )
                    return RuntimeHandle(session, {"digest": str(self.opens)})

                def reload_configuration(self):
                    self.reloads += 1

                def new_session_path(self):
                    return root / f"session-{self.opens + 1}.jsonl"

            factory = FakeFactory()

            startup = Mock()
            startup.run.return_value = ConfigurationLaunchResult(start=True)
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "RunApplicationFactory", return_value=factory
            ), patch.object(
                cli, "TerminalConfigurationFrontend", return_value=startup
            ), patch.object(cli, "TerminalFrontend", FakeFrontend):
                code = await cli.run_cli(_args(cwd=tmp))

        self.assertEqual(code, 0)
        self.assertEqual(factory.opens, 2)
        self.assertEqual(factory.reloads, 1)
        self.assertEqual(len(captured_paths), 2)
        self.assertNotEqual(captured_paths[0], captured_paths[1])
