"""Real offline recovery exposes history without changing model context."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fruitfly_agent.core.session import Session
from fruitfly_agent.interactive import AgentApplication, ConfigurationLaunchResult, TerminalFrontend
from fruitfly_agent.run import cli
from fruitfly_agent.run.application import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.materials import _write_models
from tests.support.run import _args
from tests.support.terminal import ScriptedLines


class ResumeHistoryTest(unittest.IsolatedAsyncioTestCase):
    async def _seed(self, root, registry):
        app = AgentApplication(RunApplicationFactory(cwd=root, environment={}, provider_registry=registry))
        await app.start()
        path = Path(app.status.session_path)
        await app.submit("old question")
        await app.close()
        return path

    async def test_slash_picker_and_explicit_path_display_history_once_without_requests(self):
        for picker in (True, False):
            with self.subTest(picker=picker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_models(root)
                provider = FauxProvider()
                provider.respond_text("old answer")
                registry = Mock()
                registry.create.return_value = provider
                path = await self._seed(root, registry)
                before = path.read_bytes()
                app = AgentApplication(RunApplicationFactory(cwd=root, environment={}, provider_registry=registry))
                await app.start()
                output = io.StringIO()
                lines = ScriptedLines("/resume", "1", "/status", "/exit") if picker else ScriptedLines(f"/resume {path}", "/status", "/exit")
                try:
                    code = await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=lines).run()
                    self.assertEqual(code, 0)
                    self.assertEqual(Path(app.status.session_path), path)
                    self.assertEqual(len(provider.calls), 1)
                    text = output.getvalue()
                    self.assertEqual(text.count("old question"), 1)
                    self.assertEqual(text.count("old answer"), 1)
                    self.assertLess(text.index("old question"), text.index("old answer"))
                    self.assertEqual(path.read_bytes(), before)
                finally:
                    await app.close()

    async def test_cli_startup_resume_displays_history_and_continues_original_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            provider = FauxProvider()
            provider.respond_text("old answer")
            registry = Mock()
            registry.create.return_value = provider
            path = await self._seed(root, registry)
            provider.respond_text("new answer")
            setup = Mock()
            setup.run.return_value = ConfigurationLaunchResult(start=True)
            output = io.StringIO()
            frontend_type = TerminalFrontend

            def frontend(app, **kwargs):
                return frontend_type(app, input_stream=io.StringIO(), output_stream=output,
                                     line_editor=ScriptedLines("new question", "/exit"), **kwargs)

            with patch.object(cli, "load_env", return_value={}), patch.object(
                cli, "TerminalConfigurationFrontend", return_value=setup
            ), patch("fruitfly_agent.run.assembly.default_registry", return_value=registry), patch.object(
                cli, "TerminalFrontend", side_effect=frontend
            ), contextlib.redirect_stdout(output):
                code = await cli.run_cli(_args(cwd=tmp, session=str(path), resume=True))
            self.assertEqual(code, 0)
            setup.run.assert_called_once_with(editable=False)
            self.assertEqual(len(provider.calls), 2)
            context = provider.calls[1]["messages"]
            self.assertEqual([m.role for m in context], ["user", "assistant", "user"])
            self.assertEqual(context[0].content, "old question")
            self.assertEqual(context[1].text, "old answer")
            self.assertEqual(context[2].content, "new question")
            text = output.getvalue()
            self.assertEqual(text.count("old question"), 1)
            self.assertEqual(text.count("old answer"), 1)
            self.assertLess(text.index("old answer"), text.index("new answer"))
            with Session(path) as saved:
                self.assertEqual([m.role for m in saved.canonical_messages()], ["user", "assistant", "user", "assistant"])

    async def test_cancel_and_failed_resume_keep_current_history(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _write_models(root)
                provider = FauxProvider()
                provider.respond_text("old answer")
                registry = Mock()
                registry.create.return_value = provider
                path = await self._seed(root, registry)
                factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
                app = AgentApplication(factory)
                await app.start()
                current = app.status.session_path
                output = io.StringIO()
                lines = ScriptedLines("/resume", "q", "/exit") if cancel else ScriptedLines(f"/resume {path}", "/exit")
                try:
                    if cancel:
                        await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=lines).run()
                    else:
                        with patch.object(factory, "open", side_effect=ValueError("incompatible session")):
                            await TerminalFrontend(app, input_stream=io.StringIO(), output_stream=output, line_editor=lines).run()
                        self.assertIn("could not resume session", output.getvalue())
                    self.assertEqual(app.status.session_path, current)
                    self.assertNotIn("old question", output.getvalue())
                    self.assertNotIn("old answer", output.getvalue())
                    self.assertEqual(len(provider.calls), 1)
                finally:
                    await app.close()

    async def test_one_shot_resume_continues_context_without_printing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            provider = FauxProvider()
            provider.respond_text("old answer")
            registry = Mock()
            registry.create.return_value = provider
            path = await self._seed(root, registry)
            provider.respond_text("new answer")
            output = io.StringIO()
            with patch.object(cli, "load_env", return_value={}), patch(
                "fruitfly_agent.run.assembly.default_registry", return_value=registry
            ), patch.object(cli, "TerminalConfigurationFrontend") as startup, contextlib.redirect_stdout(output):
                code = await cli.run_cli(_args(task="new question", cwd=tmp, session=str(path), resume=True))
            self.assertEqual(code, 0)
            startup.assert_not_called()
            self.assertEqual(len(provider.calls), 2)
            context = provider.calls[1]["messages"]
            self.assertEqual([m.role for m in context], ["user", "assistant", "user"])
            self.assertEqual(context[0].content, "old question")
            self.assertEqual(context[1].text, "old answer")
            self.assertEqual(context[2].content, "new question")
            self.assertIn("new answer", output.getvalue())
            self.assertNotIn("old question", output.getvalue())
            self.assertNotIn("old answer", output.getvalue())
