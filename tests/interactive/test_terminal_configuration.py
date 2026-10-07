"""Configuration menu choices, drafts, and startup confirmation."""

from dataclasses import replace
import io
import unittest

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.configuration import (
    ConfigurationLaunchResult,
)
from tests.support.terminal import ScriptedLines


from tests.support.configuration import MockConfiguration, AlgorithmConfiguration


class TerminalConfigurationFrontendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.output = io.StringIO()

    def frontend(self, controller, *lines):
        return TerminalConfigurationFrontend(
            controller, output_stream=self.output, line_editor=ScriptedLines(*lines),
        )

    def test_startup_returns_only_after_save_when_configuration_changes(self) -> None:
        controller = MockConfiguration()
        output = self.output
        frontend = self.frontend(controller, '2', '', '1', 'back', '1')

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.model, "offline")
        self.assertTrue(controller.saved)
        self.assertIn("Ready to start", output.getvalue())
        self.assertIn("> 1. Start new session", output.getvalue())
        self.assertIn("1. model", output.getvalue())
        self.assertNotIn("Advanced settings", output.getvalue())

    def test_ready_configuration_starts_from_option_without_saving(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '1')

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True))
        self.assertFalse(controller.saved)

    def test_resume_view_is_read_only_and_generic(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '1')

        result = frontend.run(editable=False)

        self.assertTrue(result.start)
        self.assertIn("FruitFlyAgent · resume", output.getvalue())
        self.assertIn("> 1. Resume session", output.getvalue())
        self.assertFalse(controller.changed)

    def test_configuration_groups_mechanisms_and_hides_parameters(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '2', '3', 'space', 'back', 'back', '1')

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertTrue(controller.enabled)
        self.assertIn("Injected mechanism", output.getvalue())
        self.assertNotIn("Provided entirely by the configuration snapshot.", output.getvalue())
        self.assertIn("✓ custom", output.getvalue())
        self.assertNotIn("Toggle the injected feature", output.getvalue())
        self.assertNotIn("feature=True", output.getvalue())

    def test_configuration_omits_advanced_settings_and_detailed_parameters(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, 'back')

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        rendered = output.getvalue()
        self.assertNotIn("Advanced settings", rendered)
        self.assertNotIn("Profile", rendered)
        self.assertNotIn("Model catalog", rendered)
        self.assertNotIn("Feature", rendered)
        self.assertNotIn("Toggle the injected feature", rendered)

    def test_module_checkbox_and_inline_algorithm_dropdown_hide_parameters(self) -> None:
        controller = AlgorithmConfiguration()
        output = self.output
        frontend = self.frontend(controller, '3', '2', '5', 'back', 'back', '1')
        result = frontend.run_for_active_session()
        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.algorithm, "variant-c")
        rendered = output.getvalue()
        self.assertIn("✓ reduction", rendered)
        self.assertIn("id: variant-b ▾", rendered)
        self.assertIn("id: variant-c ▾", rendered)
        self.assertIn("variant-a", rendered)
        self.assertNotIn("Settings", rendered)
        self.assertNotIn("Maximum tokens", rendered)
        self.assertNotIn("Detailed algorithm tuning", rendered)

    def test_single_algorithm_still_has_inline_dropdown(self) -> None:
        controller = AlgorithmConfiguration()
        original_snapshot = controller.snapshot
        def snapshot():
            value = original_snapshot()
            only = next(item for item in value.mechanisms if item.mechanism_id == "variant-b")
            return replace(value, mechanisms=(only,), selection_groups=(
                replace(value.selection_groups[0], option_ids=("variant-b",)),
            ))
        controller.snapshot = snapshot
        output = self.output
        frontend = self.frontend(controller, '3', '2', '3', 'back', 'back', '1')
        self.assertTrue(frontend.run_for_active_session().saved)
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertIn("id: variant-b ▴", output.getvalue())
        self.assertIn("✓     variant-b", output.getvalue())
        self.assertNotIn("Settings", output.getvalue())

    def test_dropdown_cancel_keeps_algorithm_and_toggle_remembers_choice(self) -> None:
        controller = AlgorithmConfiguration()
        output = self.output
        frontend = self.frontend(controller, '3', '2', 'back', '1', '1', 'back', 'back', '1')
        self.assertTrue(frontend.run_for_active_session().saved)
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertTrue(controller.enabled)
        self.assertNotIn("Settings", output.getvalue())

    def test_active_session_configuration_requires_confirmation(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '3', 'space', 'back', 'back', '1')

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertTrue(controller.saved)
        self.assertIn("New session required", output.getvalue())

    def test_active_session_configuration_returns_without_changes(self) -> None:
        controller = MockConfiguration(model="offline")
        frontend = self.frontend(controller, 'back')

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        self.assertFalse(controller.saved)

    def test_current_model_uses_a_checkmark(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '1', 'back', 'back')

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=False))
        self.assertIn("✓ offline", output.getvalue())
