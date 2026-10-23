"""Default harness restoration is a reversible daily-configuration draft edit."""
import io
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import yaml

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration.profile import load_harness_config
from tests.support.terminal import MenuScriptedLines


def write_workspace(root):
    state = root / ".fruitfly"
    state.mkdir()
    model = {"provider": "openai", "model": "fixture", "context_window": 32768,
             "max_output_tokens": 1024, "api_key_env": "SHARED_MODEL_KEY"}
    for prefix, name in (("", "daily"), ("default-", "baseline")):
        (state / (prefix + "models.yaml")).write_text(yaml.safe_dump({"models": {"fake": model}}))
        ids = ("local-env", "read-tool") if prefix else ("local-env", "read-tool", "bash-tool", "write-tool", "skill-catalog")
        profile = {"model": {"catalog": prefix + "models.yaml", "profile": "fake"},
                   "mechanisms": [{"id": n} for n in ids]}
        (state / (prefix + "config.yaml")).write_text(yaml.safe_dump({"schema_version": 1,
            "default_profile": name, "profiles": {name: profile}}))


class DefaultConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        write_workspace(self.root)
        self.environment = {"SHARED_MODEL_KEY": "offline-fixture"}

    def factory(self, **kwargs):
        return RunApplicationFactory(cwd=self.root, environment=self.environment, **kwargs)

    def frontend(self, controller, *lines):
        output = io.StringIO()
        return TerminalConfigurationFrontend(controller, output_stream=output,
            line_editor=MenuScriptedLines(output, *lines)), output

    def test_home_is_clean_and_restore_is_last_config_action_before_back(self):
        factory = self.factory()
        frontend, _ = self.frontend(factory.configuration, "@Configure", "@Restore default configuration", "@Back", "@Start new session")
        frames = []
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        home = next(f for f in frames if f["title"] == "FruitFlyAgent")
        self.assertEqual([r.label for r in home["rows"]], ["Start new session", "Configure", "Exit"])
        for frame in (f for f in frames if f["title"] == "Configuration"):
            self.assertEqual([r.label for r in frame["rows"]][-2:], ["Restore default configuration", "Back"])
            self.assertFalse(any(r.label == "Permissions" for r in frame["rows"]))
        saved = load_harness_config(self.root / ".fruitfly/config.yaml").select()
        baseline = load_harness_config(self.root / ".fruitfly/default-config.yaml").select()
        self.assertEqual(saved.mechanisms, baseline.mechanisms)
        self.assertEqual(saved.model_catalog, "models.yaml")

    def test_restoration_preserves_model_credentials_other_profiles_and_default_files(self):
        factory = self.factory()
        controller = factory.configuration
        artifact = factory.artifact_store.put_text("Fixture experiment instructions")
        original_profile = replace(controller.profile(), prompt=artifact.artifact_id,
            artifact_bindings={"skill-catalog.guidance": artifact.artifact_id})
        controller.stage_profile(original_profile)
        controller.save()
        controller.model_setup.credentials.values["PENDING_FIXTURE_KEY"] = "offline-pending"
        before = {p: p.read_bytes() for p in (self.root / ".fruitfly").glob("*.yaml")}
        result = controller.restore_defaults()
        self.assertTrue(result.changed)
        self.assertTrue(controller.changed)
        self.assertEqual(controller.profile().model_catalog, original_profile.model_catalog)
        self.assertEqual(controller.profile().model_profile, original_profile.model_profile)
        self.assertEqual(controller.profile().artifact_bindings, {})
        self.assertEqual(controller.profile().prompt, "assistant-default")
        self.assertEqual(controller.model_setup.credentials.values, {"PENDING_FIXTURE_KEY": "offline-pending"})
        self.assertEqual(factory.environment["SHARED_MODEL_KEY"], "offline-fixture")
        for path, body in before.items():
            self.assertEqual(path.read_bytes(), body)
        controller.reset()
        self.assertEqual(controller.profile(), original_profile)
        self.assertFalse(controller.changed)
        self.assertEqual(controller.model_setup.credentials.values, {})

    def test_active_restore_uses_discard_and_save_apply_flow(self):
        for decision, saved in (("@Discard changes", False), ("@Save and apply to this conversation", True)):
            with self.subTest(decision=decision):
                factory = self.factory()
                original = factory.configuration.profile()
                before_default = (self.root / ".fruitfly/default-config.yaml").read_bytes()
                frontend, _ = self.frontend(factory.configuration, "@Restore default configuration", "@Back", decision)
                result = frontend.run_for_active_session()
                self.assertEqual(result.start, saved)
                self.assertEqual(result.saved, saved)
                actual = load_harness_config(self.root / ".fruitfly/config.yaml").select()
                if saved:
                    self.assertEqual(actual.mechanisms, load_harness_config(self.root / ".fruitfly/default-config.yaml").select().mechanisms)
                else:
                    self.assertEqual(actual, original)
                self.assertEqual((self.root / ".fruitfly/default-config.yaml").read_bytes(), before_default)

    def test_missing_or_invalid_defaults_leave_the_daily_draft_unchanged(self):
        controller = self.factory().configuration
        original = controller.profile()
        path = self.root / ".fruitfly/default-config.yaml"
        for contents in (None, "broken: ["):
            with self.subTest(contents=contents):
                path.unlink(missing_ok=True)
                if contents is not None:
                    path.write_text(contents)
                with self.assertRaises(ValueError):
                    controller.restore_defaults()
                self.assertEqual(controller.profile(), original)
                self.assertFalse(controller.changed)

    def test_manually_changed_defaults_are_reloaded_by_each_restore(self):
        controller = self.factory().configuration
        controller.restore_defaults()
        controller.reset()
        path = self.root / ".fruitfly/default-config.yaml"
        config = yaml.safe_load(path.read_text())
        config["profiles"]["baseline"]["mechanisms"] = [{"id": "local-env"}, {"id": "write-tool"}]
        path.write_text(yaml.safe_dump(config))
        controller.restore_defaults()
        self.assertEqual({m.mechanism_id for m in controller.profile().mechanisms}, {"local-env", "write-tool"})

    def test_default_file_stays_read_only_and_has_no_model_wizard(self):
        controller = self.factory(config_path=".fruitfly/default-config.yaml").configuration
        self.assertTrue(controller.read_only)
        self.assertIsNone(controller.model_setup)
        self.assertIsNone(controller.mechanism_setup)
        for action in (controller.save, controller.restore_defaults, lambda: controller.select_model("fake")):
            with self.assertRaisesRegex(ValueError, "read-only"):
                action()
        frontend, output = self.frontend(controller, "back")
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertNotIn("Restore default configuration", output.getvalue())
        self.assertNotIn("Permissions", output.getvalue())

    def test_default_auxiliary_model_missing_from_daily_catalog_rejects_restoration(self):
        controller = self.factory().configuration
        original = controller.profile()
        path = self.root / ".fruitfly/default-config.yaml"
        config = yaml.safe_load(path.read_text())
        config["profiles"]["baseline"]["mechanisms"].append({"id": "component-improvement",
            "parameters": {"editor_profile": "editor"}})
        path.write_text(yaml.safe_dump(config))
        with self.assertRaisesRegex(ValueError, "editor"):
            controller.restore_defaults()
        self.assertEqual(controller.profile(), original)
