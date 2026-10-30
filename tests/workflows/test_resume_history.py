"""Real offline recovery exposes history without changing model context."""

import contextlib
import io
import json
from dataclasses import replace
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
from tests.support.run import _write_catalog
from tests.support.terminal import ScriptedLines


class ResumeHistoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_permissions_changed_model_prompt_and_profile_continue_in_one_file(self):
        from fruitfly_agent.run.runtime.manifest import digest_manifest
        from fruitfly_agent.lab.catalog import PermissionPolicy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            _write_models(root)
            provider = FauxProvider()
            provider.respond_text("old answer")
            registry = Mock()
            registry.create.return_value = provider
            path = await self._seed(root, registry)
            records = [json.loads(line) for line in path.read_text().splitlines()]
            original = records[0]["manifest"]
            original.pop("permissions")
            original.pop("digest")
            original["digest"] = digest_manifest(original)
            path.write_text("".join(json.dumps(record) + "\n" for record in records))
            before = path.read_bytes()
            _write_catalog(root / ".fruitfly/models.yaml", {"renamed-model": "new-model"})
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry,
                permission_policy=PermissionPolicy(root, read_roots=(root, root.parent)))
            prompt = factory.artifact_store.put_text("Current prompt for continuation")
            factory.configuration.stage_profile(replace(factory.configuration.profile(), profile_id="renamed",
                                                        model_profile="renamed-model", prompt=prompt.artifact_id))
            factory.configuration.select_profile("renamed")
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start(resume=True, session_path=path)
            self.assertEqual(1, len(provider.calls))
            self.assertEqual(0, app.status.permission_grants)
            self.assertEqual("new-model", app.status.model)
            provider.respond_text("continued answer")
            await app.submit("continue")
            self.assertIn("Current prompt for continuation", provider.calls[-1]["system_prompt"])
            self.assertEqual("old question", provider.calls[-1]["messages"][0].content)
            await app.close()
            await app.start(resume=True, session_path=path)
            provider.respond_text("second continuation")
            await app.submit("continue again")
            await app.close()
            self.assertTrue(path.read_bytes().startswith(before))
            with Session(path) as saved:
                manifests = [entry for entry in saved.read_all() if entry.payload.get("kind") == "runtimeManifest"]
                self.assertEqual(2, len(manifests))
                self.assertEqual(original, manifests[0].payload["manifest"])
                self.assertEqual("renamed", manifests[1].payload["manifest"]["profile"])
                self.assertEqual(["old question", "continue", "continue again"],
                    [message.content for message in saved.canonical_messages() if message.role == "user"])
                current = None
                run_bindings = []
                for entry in saved.read_all():
                    if entry.payload.get("kind") == "runtimeManifest":
                        current = entry.payload["manifest"]["models"]["main"]["model"]
                    elif entry.payload.get("kind") == "runRecord" and entry.payload.get("event") == "start":
                        run_bindings.append(current)
                self.assertEqual(["offline-model", "new-model", "new-model"], run_bindings)

    async def test_changed_context_rebuilds_projection_and_persists_new_input_across_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            provider = FauxProvider()
            provider.respond_text("old answer")
            registry = Mock()
            registry.create.return_value = provider
            path = await self._seed(root, registry)
            with Session(path) as saved:
                from fruitfly_agent.core.data_model import UserMessage
                saved.append("compaction", {"messages": [UserMessage(content="old projected summary").to_dict()]})
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
            factory.configuration.set_mechanism("compaction", enabled=False)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start(resume=True, session_path=path)
            provider.respond_text("new answer")
            await app.submit("new question")
            self.assertEqual("old question", provider.calls[-1]["messages"][0].content)
            await app.close()
            await app.start(resume=True, session_path=path)
            self.assertEqual(1, app.status.compaction_count)
            provider.respond_text("another answer")
            await app.submit("another question")
            self.assertIn("new question", [getattr(message, "content", None) for message in provider.calls[-1]["messages"]])
            await app.close()
            with Session(path) as saved:
                self.assertEqual(1, sum("contextProjection" in entry.payload for entry in saved.read_all()))
                self.assertEqual(6, len(saved.canonical_messages()))

    async def test_failed_resource_start_retains_active_runtime_and_target_file(self):
        from fruitfly_agent.lab.catalog import MechanismDefinition, builtin_catalog
        from fruitfly_agent.core.mechanisms import MechanismDescriptor, MechanismContribution
        class BrokenResource:
            closed = False
            async def start(self):
                raise RuntimeError("resource startup failed")
            async def close(self):
                self.closed = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_models(root)
            provider = FauxProvider()
            provider.respond_text("old answer")
            registry = Mock()
            registry.create.return_value = provider
            path = await self._seed(root, registry)
            broken = BrokenResource()
            def install(state, context, parameters):
                return state.with_component("broken", context.own(broken))
            definition = MechanismDefinition(MechanismDescriptor("broken", "Broken", "fixture",
                (MechanismContribution("capability", "tools"),)), install,
                implementation_path='tests/workflows/test_resume_history.py',
                documentation_path='tests/workflows/README.md',
                optimization_exemption='Resource startup fixture; no research algorithm is installed.',
            )
            catalog = builtin_catalog().extended((definition,))
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry, catalog=catalog)
            app = AgentApplication(factory)
            await app.start()
            current = app.status.session_path
            factory.configuration.set_mechanism("broken", enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            before = path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "resource startup failed"):
                await app.resume(path)
            self.assertEqual(current, app.status.session_path)
            self.assertEqual(before, path.read_bytes())
            self.assertTrue(broken.closed)
            with Session(path):
                pass
            await app.close()

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
            ), patch("fruitfly_agent.run.runtime.assembly.default_registry", return_value=registry), patch.object(
                cli, "TerminalFrontend", side_effect=frontend
            ), contextlib.redirect_stdout(output):
                code = await cli.run_cli(_args(cwd=tmp, session=str(path), resume=True))
            self.assertEqual(code, 0)
            setup.run.assert_called_once_with(configure=False)
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
                "fruitfly_agent.run.runtime.assembly.default_registry", return_value=registry
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
