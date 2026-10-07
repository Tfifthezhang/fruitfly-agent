"""Model wizard persistence, cancellation, and immediate offline assembly."""

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.input import ReadlineLineEditor
from fruitfly_agent.interactive.terminal.menu import RawTerminalMenuInput
from fruitfly_agent.interactive.terminal.model_setup import _capabilities
from fruitfly_agent.providers import ProviderRegistry
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.run import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.run import _write_catalog
from tests.support.terminal import ScriptedLines


class ModelSetupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True)
        self.controller = self.factory.configuration
        self.setup = self.controller.model_setup
        (self.root / ".fruitfly").mkdir(exist_ok=True)
        self.values = dict(profile="local", model="offline-model", base_url="",
                           context_window="8192", max_output_tokens="1024", api_key_env="")

    def stage(self, **changes):
        return self.setup.stage("openai", {**self.values, **changes}, "offline-placeholder")

    def frontend(self, *lines, secret="offline-placeholder"):
        self.output = io.StringIO()
        return TerminalConfigurationFrontend(self.controller, input_stream=io.StringIO(secret + "\n"),
            output_stream=self.output, line_editor=ScriptedLines(*lines))

    async def test_first_run_wizard_saves_then_assembles_without_restarting_process(self):
        frontend = self.frontend("1", "local", "offline-model", "", "8192", "1024", "", "", "2", "1")
        result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        self.assertNotIn("offline-placeholder", self.output.getvalue())
        self.assertIn("Add model · Step 1 of 8", self.output.getvalue())
        self.assertIn("Service: OpenAI official · Responses API", self.output.getvalue())
        self.assertIn("Press Enter to use: my-model", self.output.getvalue())
        self.assertIn("This is not the model ID", self.output.getvalue())
        self.assertNotIn("offline-placeholder", (self.root / ".fruitfly/models.yaml").read_text())
        self.assertNotIn("offline-placeholder", (self.root / ".fruitfly/config.yaml").read_text())
        self.assertEqual((self.root / ".fruitfly/secrets.env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_env(self.root / ".fruitfly/secrets.env")["FRUITFLY_MODEL_LOCAL_API_KEY"], "offline-placeholder")
        self.factory.reload_configuration()
        provider = FauxProvider()
        provider.respond_text("configured")
        registry = ProviderRegistry()
        registry.register("openai", lambda spec, key: provider)
        self.factory.provider_registry = registry
        handle = await self.factory.open(resume=False, session_path=self.root / "session.jsonl")
        try:
            response = await handle.session.submit("offline check")
            self.assertFalse(response.is_error)
            self.assertEqual(response.messages[-1].text, "configured")
        finally:
            await handle.close()

    def test_field_screen_replaces_service_menu_and_labels_the_input_frame(self):
        output = io.StringIO()
        screens = []
        lines = iter(("1", "/cancel", "3"))
        def reader(_prompt):
            screens.append(output.getvalue().rsplit("\x1b[2J\x1b[H", 1)[-1])
            return next(lines)
        frontend = TerminalConfigurationFrontend(self.controller, input_stream=io.StringIO(),
            output_stream=output, line_editor=ReadlineLineEditor(output, reader=reader))
        frontend.renderer.ansi = True
        self.assertFalse(frontend.run().start)
        field_screen = screens[1]
        self.assertIn("Step 1 of 8", field_screen)
        self.assertIn("Service: OpenAI official", field_screen)
        self.assertIn("╭─ models.<name> ", field_screen)
        self.assertNotIn("╭─ prompt ", field_screen)
        self.assertNotIn("1. OpenAI", field_screen)
        self.assertNotIn("↑↓", field_screen)
        self.assertFalse(self.setup.changed)

    def test_capabilities_checkboxes_persist_booleans_and_yaml_field_names(self):
        frontend = self.frontend("1", "local", "offline-model", "", "8192", "1024", "",
                                 "1", "5", "2", "3", "4", "2", "6", "2", "1")
        self.assertTrue(frontend.run().saved)
        spec = load_model_specs(self.root / ".fruitfly/models.yaml")["local"]
        self.assertTrue(spec.capabilities.tools)
        self.assertTrue(spec.capabilities.streaming)
        self.assertFalse(spec.capabilities.parallel_tool_calls)
        self.assertTrue(spec.capabilities.vision)
        self.assertTrue(spec.capabilities.reasoning)
        rendered = self.output.getvalue()
        for field in ("model", "base_url", "context_window", "max_output_tokens", "api_key_env"):
            self.assertIn(field + ":", rendered)
        self.assertIn("provider: openai", rendered)
        self.assertIn("capabilities.parallel_tool_calls: false", rendered)
        self.assertIn("capabilities.vision: true", rendered)
        self.assertIn("streaming is required", rendered)
        self.assertNotIn("offline-placeholder", rendered)

    def test_capability_arrows_and_space_toggle_and_cancellation_write_nothing(self):
        frontend = self.frontend()
        events = iter((b"\x1b[A", b" ", b"\x1b[A", b" ", b"\x1b[B", b"\x1b[B", b"\r"))
        frontend.menu_input = SimpleNamespace(read_event=lambda: RawTerminalMenuInput.decode(next(events)))
        fields = tuple(field for field in self.setup.options()[0].fields if field.kind == "bool")
        values = _capabilities(frontend, "offline service", fields, 7, 8)
        self.assertEqual(values["capabilities.streaming"], "true")
        self.assertEqual(values["capabilities.reasoning"], "true")
        self.assertFalse(self.setup.changed)
        frontend = self.frontend("1", "local", "offline-model", "", "8192", "1024", "", "3", "back", "3")
        self.assertFalse(frontend.run().start)
        self.assertFalse(self.setup.changed)
        self.assertFalse((self.root / ".fruitfly/models.yaml").exists())

    def test_required_or_invalid_capabilities_are_rejected_before_staging(self):
        for field, value in (("tools", "false"), ("streaming", "false"), ("vision", "yes")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.stage(**{f"capabilities.{field}": value})
            self.assertFalse(self.setup.changed)

    def test_cancel_and_exit_write_nothing(self):
        for lines in (("back", "3"), ("1", "/cancel", "3"),
                      ("1", "local", "offline-model", "", "8192", "1024", "", "", "1", "3"),
                      ("1", "local", "offline-model", "", "8192", "1024", "", "", "2", "3")):
            with self.subTest(lines=lines):
                self.assertFalse(self.frontend(*lines).run().start)
                self.assertFalse(self.setup.changed)
                for name in (".fruitfly/models.yaml", ".fruitfly/secrets.env", ".fruitfly/config.yaml"):
                    self.assertFalse((self.root / name).exists())

    def test_catalog_and_environment_content_are_preserved(self):
        catalog = self.root / ".fruitfly/models.yaml"
        _write_catalog(catalog, {"existing": "old-model"})
        original = "# Keep this comment\n" + catalog.read_text() + "# Tail comment\nother: preserved\n"
        catalog.write_text(original)
        (self.root / ".fruitfly/secrets.env").write_text("# Keep credentials\nUNRELATED=value\nEMPTY=\n")
        self.stage()
        self.assertFalse((self.root / ".fruitfly/secrets.env").read_text().endswith("offline-placeholder\n"))
        self.controller.save()
        text = catalog.read_text()
        self.assertIn("# Keep this comment", text)
        self.assertIn("# Tail comment\n", text)
        self.assertIn("other: preserved\n", text)
        self.assertEqual(load_model_specs(catalog)["existing"].model, "old-model")
        self.assertTrue((self.root / ".fruitfly/secrets.env").read_text().startswith("# Keep credentials\nUNRELATED=value\nEMPTY=\n"))

    def test_invalid_fields_never_stage_or_echo_secret(self):
        cases = ({"profile": "bad label"}, {"model": ""}, {"context_window": "no"},
                 {"max_output_tokens": "8192"}, {"base_url": "https://user:password@example.invalid"},
                 {"api_key_env": "INVALID-NAME"})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError) as failure:
                self.stage(**changes)
            self.assertNotIn("offline-placeholder", str(failure.exception))
            self.assertFalse(self.setup.changed)
        with self.assertRaisesRegex(ValueError, "API base URL"):
            self.setup.stage("custom-responses", self.values, "offline-placeholder")

    def test_existing_environment_key_is_reused_without_writing_env(self):
        self.factory.environment["EXISTING_KEY"] = "offline-placeholder"
        self.setup.stage("anthropic", {**self.values, "api_key_env": "EXISTING_KEY"}, "")
        self.controller.save()
        self.assertFalse((self.root / ".fruitfly/secrets.env").exists())
        self.assertEqual(load_model_specs(self.root / ".fruitfly/models.yaml")["local"].provider.type, "anthropic")

    def test_missing_key_and_existing_key_conflict_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            self.setup.stage("openai", self.values, "")
        self.factory.environment["EXISTING_KEY"] = "first-placeholder"
        with self.assertRaisesRegex(ValueError, "already set"):
            self.stage(api_key_env="EXISTING_KEY")
        self.assertFalse(self.setup.changed)

    def test_save_failure_restores_files_and_retains_draft_for_retry(self):
        (self.root / ".fruitfly/secrets.env").write_text("# original\nOTHER=value\n")
        self.stage()
        with patch("fruitfly_agent.run.profiles.save_harness_config", side_effect=OSError("offline write failure")):
            with self.assertRaises(OSError):
                self.controller.save()
        self.assertFalse((self.root / ".fruitfly/models.yaml").exists())
        self.assertEqual((self.root / ".fruitfly/secrets.env").read_text(), "# original\nOTHER=value\n")
        self.assertNotIn("FRUITFLY_MODEL_LOCAL_API_KEY", self.factory.environment)
        self.assertTrue(self.controller.snapshot().changed)
        self.controller.save()
        self.assertFalse(self.controller.snapshot().changed)

    def test_concurrent_duplicate_and_secret_symlink_are_rejected(self):
        self.stage()
        _write_catalog(self.root / ".fruitfly/models.yaml", {"local": "other-model"})
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.controller.save()
        self.assertEqual(load_model_specs(self.root / ".fruitfly/models.yaml")["local"].model, "other-model")
        (self.root / ".fruitfly/models.yaml").unlink()
        target = self.root / "external-env"
        target.write_text("OTHER=value\n")
        (self.root / ".fruitfly/secrets.env").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.controller.save()
        self.assertEqual(target.read_text(), "OTHER=value\n")

    def test_credential_repair_is_staged_and_discardable(self):
        self.stage()
        self.controller.save()
        self.factory.environment.clear()
        (self.root / ".fruitfly/secrets.env").unlink()
        self.assertEqual(self.setup.credential_status("local"), "API key missing")
        self.setup.stage_credential("local", "second-placeholder")
        self.assertTrue(self.controller.snapshot().changed)
        self.controller.reset()
        self.assertEqual(self.setup.credential_status("local"), "API key missing")
        self.assertFalse((self.root / ".fruitfly/secrets.env").exists())

    def test_model_menu_addition_can_be_discarded_from_active_configuration(self):
        self.stage()
        self.controller.save()
        catalog = (self.root / ".fruitfly/models.yaml").read_bytes()
        environment = (self.root / ".fruitfly/secrets.env").read_bytes()
        frontend = self.frontend("1", "2", "1", "second", "another-model", "", "8192", "1024", "", "", "2", "back", "3")
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertEqual(self.controller.snapshot().model_profile, "local")
        self.assertFalse(self.controller.snapshot().changed)
        self.assertEqual((self.root / ".fruitfly/models.yaml").read_bytes(), catalog)
        self.assertEqual((self.root / ".fruitfly/secrets.env").read_bytes(), environment)

    def test_model_menu_supplies_missing_key_without_changing_model(self):
        self.stage()
        self.controller.save()
        catalog = (self.root / ".fruitfly/models.yaml").read_bytes()
        self.factory.environment.clear()
        (self.root / ".fruitfly/secrets.env").unlink()
        frontend = self.frontend("1", "3", "2", "back", "1", secret="second-placeholder")
        result = frontend.run_for_active_session()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        self.assertEqual((self.root / ".fruitfly/models.yaml").read_bytes(), catalog)
        self.assertEqual(self.setup.credential_status("local"), "API key set")
        self.assertNotIn("second-placeholder", self.output.getvalue())

    def test_changed_credential_file_is_preserved_on_save(self):
        self.stage()
        (self.root / ".fruitfly/secrets.env").write_text("FRUITFLY_MODEL_LOCAL_API_KEY=other-placeholder\n")
        with self.assertRaisesRegex(ValueError, "different value"):
            self.controller.save()
        self.assertFalse((self.root / ".fruitfly/models.yaml").exists())
        self.assertEqual((self.root / ".fruitfly/secrets.env").read_text(), "FRUITFLY_MODEL_LOCAL_API_KEY=other-placeholder\n")

    def test_interactive_first_run_uses_workspace_catalog_instead_of_checkout(self):
        fallback = self.root / "shared-models.yaml"
        _write_catalog(fallback, {"shared": "shared-model"})
        with patch("fruitfly_agent.run.model_selection.default_model_catalog_path", return_value=fallback):
            factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True)
            self.assertEqual(factory.configuration.snapshot().model_profiles, ())
            self.assertEqual(factory.configuration.snapshot().model_catalog, "models.yaml")
            one_shot = RunApplicationFactory(cwd=self.root, environment={})
            self.assertEqual(one_shot.selection.profile.model_profile, "shared")
