"""Cli configuration behavior and failure contracts."""
from __future__ import annotations
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import InteractiveSession, RuntimeHandle
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run import cli
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog, _args
from tests.support.configuration import MockConfiguration
from fruitfly_agent.interactive.contracts.startup import ConfigurationEditResult


class CliRunTest(unittest.IsolatedAsyncioTestCase):
    async def test_cwd_selects_env_file_and_process_values_take_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".fruitfly").mkdir()
            (root / ".fruitfly/secrets.env").write_text("TEST_SETTING=file\nFILE_ONLY=present\n", encoding="utf-8")
            launch = root / "launch"
            launch.mkdir()
            (launch / ".env").write_text("TEST_SETTING=wrong-workspace\nFILE_ONLY=wrong\n", encoding="utf-8")
            setup = Mock()
            setup.run.return_value = 'exit'
            with patch.dict(os.environ, {"TEST_SETTING": "process"}, clear=True), patch.object(
                cli, "RunApplicationFactory"
            ) as factory, patch.object(cli, "TerminalStartupFrontend", return_value=setup), patch.object(
                Path, "cwd", return_value=launch
            ):
                factory.return_value.configuration.snapshot.return_value = MockConfiguration(model='offline').snapshot()
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 0)
            self.assertEqual(factory.call_args.kwargs["cwd"], root.resolve())
            environment = factory.call_args.kwargs["environment"]
            self.assertEqual(environment.get("TEST_SETTING"), "process")
            self.assertEqual(environment.get("FILE_ONLY"), "present")

    async def test_incomplete_first_run_exits_without_creating_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / ".fruitfly/models.yaml", {"a": "model-a", "b": "model-b"})
            setup = Mock()
            setup.run.return_value = 'exit'
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "TerminalStartupFrontend", return_value=setup
            ), patch.object(cli, "AgentApplication") as application_type:
                code = await cli.run_cli(_args(cwd=tmp))

        self.assertEqual(code, 0)
        application_type.assert_not_called()

    async def test_complete_interactive_run_requires_start_before_welcome_without_model_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / '.fruitfly/models.yaml', {'only': 'model-a'})
            provider = FauxProvider()
            registry = Mock()
            registry.create.return_value = provider
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch.object(cli, 'load_env', return_value={'TEST_API_KEY': 'offline-fixture'}), patch(
                    'fruitfly_agent.run.runtime.assembly.default_registry', return_value=registry), patch.object(
                    cli, 'transient_screen', wraps=cli.transient_screen) as screen, patch(
                    'sys.stdin', io.StringIO('1\n/exit\n')), contextlib.redirect_stdout(output):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 0)
            screen.assert_called_once()
            self.assertLess(output.getvalue().index('Start session'), output.getvalue().index('FruitFlyAgent interactive'))
            self.assertIn('FruitFlyAgent interactive · model-a', output.getvalue())
            self.assertIn('/config', output.getvalue())
            for obsolete in ('Start new session', 'unsaved changes', '(next)'):
                self.assertNotIn(obsolete, output.getvalue())
            self.assertTrue((root / '.fruitfly/config.yaml').is_file())
            self.assertEqual(provider.calls, [])

    async def test_configure_flag_opens_configuration_before_creating_a_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_catalog(Path(tmp) / '.fruitfly/models.yaml', {'only': 'model-a'})
            setup = Mock()
            setup.run_for_startup.return_value = ConfigurationEditResult()
            with patch.object(cli, 'load_env', return_value={}), patch.object(
                    cli, 'TerminalConfigurationFrontend', return_value=setup), patch.object(
                    cli, 'AgentApplication') as application, patch('sys.stdin', io.StringIO('q\n')):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp, configure=True)), 0)
            setup.run_for_startup.assert_called_once_with()
            application.assert_not_called()

    async def test_configure_rejects_noninteractive_inputs_before_factory_creation(self):
        for values in ({'task': 'do work'}, {'image': ['image.png']}):
            with self.subTest(values=values), patch.object(cli, 'RunApplicationFactory') as factory, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(await cli.run_cli(_args(configure=True, **values)), 2)
                factory.assert_not_called()

    async def test_missing_model_key_opens_repair_and_cancellation_creates_no_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / '.fruitfly/models.yaml', {'only': 'model-a'})
            output = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), patch.object(cli, 'load_env', return_value={}), patch(
                    'sys.stdin', io.StringIO('2\nback\n/cancel\nq\n')), patch.object(cli, 'AgentApplication') as application, contextlib.redirect_stdout(output):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 0)
            self.assertIn('Set API key', output.getvalue())
            application.assert_not_called()
            self.assertFalse((root / '.fruitfly/config.yaml').exists())
            self.assertFalse((root / '.fruitfly/secrets.env').exists())
            self.assertFalse((root / '.fruitfly/sessions').exists())

    async def test_invalid_configuration_reports_its_path_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '.fruitfly/config.yaml'
            path.parent.mkdir()
            body = 'unexpected: true\n'
            path.write_text(body)
            errors = io.StringIO()
            with patch.object(cli, 'AgentApplication') as application, patch.object(cli, 'TerminalConfigurationFrontend') as frontend, contextlib.redirect_stderr(errors):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 2)
            self.assertIn(str(path), errors.getvalue())
            self.assertEqual(path.read_text(), body)
            application.assert_not_called()
            frontend.assert_not_called()

    async def test_startup_save_failure_returns_to_panel_without_creating_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_catalog(root / '.fruitfly/models.yaml', {'only': 'model-a'})
            factory = RunApplicationFactory(cwd=root, environment={'TEST_API_KEY': 'offline-fixture'}, allow_incomplete=True)
            output = io.StringIO()
            with patch.object(cli, 'RunApplicationFactory', return_value=factory), patch.object(
                    factory.configuration, 'save', side_effect=OSError('fixture write failed')), patch.object(
                    cli, 'AgentApplication') as application, patch.object(
                    cli, 'transient_screen', wraps=cli.transient_screen), patch('sys.stdin', io.StringIO('1\nq\n')), contextlib.redirect_stdout(output):
                self.assertEqual(await cli.run_cli(_args(cwd=tmp)), 0)
            self.assertIn('fixture write failed', output.getvalue())
            self.assertTrue(factory.configuration.changed)
            application.assert_not_called()
            self.assertFalse((root / '.fruitfly/sessions').exists())

    async def test_confirmed_runtime_configuration_rebuilds_a_fresh_session(self) -> None:
        captured_paths: list[str] = []

        class FakeFrontend:
            def __init__(self, app, *, bindings) -> None:
                assert callable(bindings.clipboard_image)
                self.app = app
                captured_paths.append(app.status.session_path)

            async def run(self) -> int:
                await self.app.rebuild()
                captured_paths.append(self.app.status.session_path)
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configuration = Mock()
            configuration.snapshot.return_value = MockConfiguration(model='offline').snapshot()

            class FakeFactory:
                def __init__(self) -> None:
                    self.configuration = configuration
                    self.catalog = Mock()
                    self.tool_service_startup_approval = None
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
            startup.run.return_value = 'start'
            async def wait(task, **kwargs):
                await task
                return True
            startup.wait_for_start.side_effect = wait
            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "RunApplicationFactory", return_value=factory
            ), patch.object(
                cli, "TerminalStartupFrontend", return_value=startup
            ), patch.object(cli, "TerminalFrontend", FakeFrontend):
                code = await cli.run_cli(_args(cwd=tmp))

        self.assertEqual(code, 0)
        self.assertEqual(factory.opens, 2)
        self.assertEqual(factory.reloads, 1)
        self.assertEqual(len(captured_paths), 2)
        self.assertNotEqual(captured_paths[0], captured_paths[1])
