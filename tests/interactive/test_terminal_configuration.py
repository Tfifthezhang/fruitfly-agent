"""Configuration menu choices, drafts, and startup confirmation."""

from dataclasses import replace
import io
import unittest

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.contracts.configuration import ConfigurationLaunchResult, ConfigurationMechanism
from tests.support.terminal import MenuScriptedLines


from tests.support.configuration import MockConfiguration, AlgorithmConfiguration


class TerminalConfigurationFrontendTest(unittest.TestCase):
    def test_browsing_algorithm_help_does_not_stage_configuration(self):
        controller = AlgorithmConfiguration()
        frontend = self.frontend(controller, '@Compaction', '@Reduction', 'down', 'down',
            'back', 'back', 'back')
        frames = []
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        self.assertFalse(frontend.run_for_active_session().start)
        category = [f for f in frames if f['title'] == 'Compaction']
        focused = [f['rows'][f['selected']] for f in category]
        self.assertTrue(any(r.help.title == 'Variant A' for r in focused))
        self.assertTrue(any(r.help.title == 'Variant B' for r in focused))
        self.assertTrue(all(not r.references and not r.detail for f in category for r in f['rows']))
        self.assertNotIn('Details ·', self.output.getvalue())
        self.assertNotIn('/workspace/fruitfly.yaml', self.output.getvalue())
        self.assertEqual(controller.algorithm, 'variant-b')
        self.assertFalse(controller.changed)

    def test_real_lab_configuration_hides_tuning_but_keeps_resource_inputs_and_values(self):
        from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection
        from fruitfly_agent.run.configuration.profile import HarnessProfile
        from fruitfly_agent.run.configuration.views import mechanism_views
        from fruitfly_agent.interactive.terminal.features.configuration.presentation import category_rows, settings_rows
        catalog = builtin_catalog()
        profile = HarnessProfile('daily', mechanisms=(
            MechanismSelection('working-memory-reduction', parameters={'memory_tokens':12345}),
            MechanismSelection('live-http', parameters={'endpoint':'https://example.test/?q={query}'}),
            MechanismSelection('skill-document', parameters={'source_path':'.skills/check/SKILL.md'})))
        mechanisms, groups = mechanism_views(profile, catalog, [])
        snapshot = replace(MockConfiguration(model='offline').snapshot(), mechanisms=mechanisms, selection_groups=groups)
        rows, actions = category_rows(snapshot, 'context-manager', 'reduction')
        self.assertFalse(any(a.kind == 'parameter' for a in actions))
        self.assertTrue(all(not r.references and not r.detail for r in rows))
        self.assertTrue(all('Enabled' not in r.label and 'Disabled' not in r.label for r in rows))
        compaction = next(m for m in mechanisms if m.mechanism_id == 'working-memory-reduction')
        self.assertEqual(next(p.value for p in compaction.parameters if p.name == 'memory_tokens'), 12345)
        for identity, names in [('live-http', ['endpoint']), ('skill-document', ['initial_text', 'source_path'])]:
            item = next(m for m in mechanisms if m.mechanism_id == identity)
            _, actions = settings_rows(item, original=snapshot)
            self.assertEqual([a.parameter.name for a in actions if a.kind == 'parameter'], names)

    def setUp(self) -> None:
        self.output = io.StringIO()

    def frontend(self, controller, *lines):
        return TerminalConfigurationFrontend(
            controller, output_stream=self.output, line_editor=MenuScriptedLines(self.output, *lines),
        )

    def test_startup_returns_only_after_save_when_configuration_changes(self) -> None:
        controller = MockConfiguration()
        output = self.output
        frontend = self.frontend(controller, '@model', '1', 'back', '@Save and start')

        result = frontend.run(configure=True)

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.model, "offline")
        self.assertTrue(controller.saved)
        self.assertNotIn("Start new session", output.getvalue())
        self.assertIn("Save and start", output.getvalue())
        self.assertIn("1. model", output.getvalue())
        self.assertNotIn("Advanced settings", output.getvalue())

    def test_ready_configuration_starts_without_reading_input_or_rendering_a_menu(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller)

        result = frontend.run()

        self.assertEqual(result, ConfigurationLaunchResult(start=True))
        self.assertFalse(controller.saved)

    def test_resume_view_is_read_only_and_generic(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller)

        controller.read_only = True
        result = frontend.run()

        self.assertTrue(result.start)
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(controller.changed)

    def test_configuration_groups_mechanisms_and_hides_parameters(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '@Custom', 'space', 'back', 'back', '@Save and start')

        result = frontend.run(configure=True)

        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertTrue(controller.enabled)
        self.assertIn("Injected mechanism", output.getvalue())
        self.assertIn("Provided entirely by the configuration snapshot.", output.getvalue())
        self.assertIn("[✓] Injected mechanism", output.getvalue())
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

    def test_module_selection_keeps_focus_and_shows_no_technical_references(self):
        controller = AlgorithmConfiguration()
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Variant C',
            'back', 'back', 'back', '1')
        frames = []
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        self.assertEqual(frontend.run_for_active_session(), ConfigurationLaunchResult(start=True))
        self.assertFalse(controller.saved)
        self.assertEqual(controller.algorithm, 'variant-c')
        rendered = self.output.getvalue()
        self.assertIn('[✓] Reduction · Variant B', rendered)
        self.assertIn('[✓] Reduction · Variant C', rendered)
        self.assertIn('○ Variant A', rendered)
        self.assertIn('● Variant C', rendered)
        self.assertNotIn('Maximum tokens', rendered)
        self.assertIn('Detailed algorithm tuning', rendered)
        for technical in ('Implementation:', 'Guide:', 'Configuration:', 'profiles.default.mechanisms'):
            self.assertNotIn(technical, rendered)
        changed = next(f for f in frames if any(r.marker == '●' and r.label == 'Variant C' for r in f['rows']))
        self.assertEqual(changed['rows'][changed['selected']].label, 'Variant C')
        self.assertIn('Modified', rendered)

    def test_single_implementation_has_help_and_no_empty_settings_or_selector(self):
        controller = AlgorithmConfiguration()
        original = controller.snapshot
        def snapshot():
            value = original()
            only = next(item for item in value.mechanisms if item.mechanism_id == 'variant-b')
            return replace(value, mechanisms=(only,), selection_groups=(
                replace(value.selection_groups[0], option_ids=('variant-b',)),))
        controller.snapshot = snapshot
        frontend = self.frontend(controller, '@Compaction', '@Reduction', 'back', 'back')
        self.assertFalse(frontend.run_for_active_session().start)
        text = self.output.getvalue()
        self.assertIn('[✓] Reduction', text)
        self.assertIn('Detailed algorithm tuning', text)
        for redundant in ('Details ·', '● Variant B', 'Maximum tokens', 'Implementation:', 'Reduction ›', 'Reduction ▾'):
            self.assertNotIn(redundant, text)
        self.assertFalse(controller.changed)

    def test_dropdown_cancel_keeps_algorithm_and_toggle_remembers_choice(self) -> None:
        controller = AlgorithmConfiguration()
        output = self.output
        frontend = self.frontend(controller, '@Compaction', '@Reduction', 'back', 'space', 'space',
            'back', 'back', '1')
        self.assertTrue(frontend.run_for_active_session().start)
        self.assertFalse(controller.saved)
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertTrue(controller.enabled)
        self.assertNotIn("Settings", output.getvalue())

    def test_space_on_an_algorithm_only_browses_and_required_groups_cannot_be_disabled(self):
        controller = AlgorithmConfiguration()
        original = controller.snapshot
        controller.snapshot = lambda: replace(original(), selection_groups=(
            replace(original().selection_groups[0], allow_disabled=False),))
        frontend = self.frontend(controller, '@Compaction', '@Reduction', 'down', 'space',
            'back', 'space', 'back', 'back')
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertIn('This module cannot be disabled.', self.output.getvalue())
        self.assertEqual(controller.algorithm, 'variant-b')
        self.assertTrue(controller.enabled)
        self.assertFalse(controller.changed)

    def test_disabled_group_help_does_not_claim_the_first_algorithm_is_selected(self):
        from fruitfly_agent.interactive.terminal.features.configuration.presentation import category_rows
        controller = AlgorithmConfiguration()
        controller.enabled = False
        snapshot = controller.snapshot()
        rows, _ = category_rows(snapshot, 'compaction', 'reduction')
        self.assertEqual(rows[0].label, 'Reduction ▴')
        self.assertEqual(rows[0].marker, '[ ]')
        self.assertEqual(rows[0].help.text, 'Choose an implementation.')
        self.assertTrue(all(row.marker != '●' for row in rows))
        self.assertFalse(controller.changed)
        self.assertEqual(snapshot, controller.snapshot())

    def test_single_implementation_settings_can_be_inspected_while_disabled(self):
        controller = AlgorithmConfiguration()
        controller.enabled = False
        original = controller.snapshot
        def snapshot():
            value = original()
            item = next(m for m in value.mechanisms if m.mechanism_id == 'variant-b')
            return replace(value, mechanisms=(replace(item, input_parameters=('max_tokens',)),),
                selection_groups=(replace(value.selection_groups[0], option_ids=('variant-b',)),))
        controller.snapshot = snapshot
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Maximum tokens', '/cancel',
            'back', 'back', 'back')
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertIn('[ ] Reduction ›', self.output.getvalue())
        self.assertIn('Maximum tokens · 1000', self.output.getvalue())
        self.assertFalse(controller.enabled)
        self.assertFalse(controller.changed)

    def test_reenable_restores_the_last_selected_nondefault_algorithm(self):
        controller = AlgorithmConfiguration()
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Variant C', 'back',
            'space', 'space', 'back', 'back', '1')
        self.assertTrue(frontend.run_for_active_session().start)
        self.assertEqual(controller.algorithm, 'variant-c')
        self.assertTrue(controller.enabled)

    def test_declared_user_input_stays_visible_and_cancel_or_invalid_input_preserves_value(self) -> None:
        controller = AlgorithmConfiguration()
        original = controller.snapshot
        controller.snapshot = lambda: replace(original(), mechanisms=tuple(
            replace(m, input_parameters=('max_tokens',)) for m in original().mechanisms))
        frames = []
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Settings…', '@Maximum tokens', '/cancel',
            '@Maximum tokens', '0', 'back', 'back', 'back', 'back')
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertEqual(controller.max_tokens, 1000)
        self.assertFalse(controller.changed)
        self.assertTrue(controller.enabled)
        self.assertEqual(controller.algorithm, 'variant-b')
        self.assertIn('Invalid parameter', self.output.getvalue())
        inputs = [frame for frame in frames if frame.get('field')]
        self.assertTrue(all(frame['title'] == 'Variant B' for frame in inputs))
        self.assertTrue(all(frame['rows'][frame['selected']].label.startswith('Maximum tokens') for frame in inputs))

    def test_context_phases_are_sections_and_augmentation_capabilities_are_peers(self) -> None:
        controller = MockConfiguration(model='offline')
        original = controller.snapshot
        controller.snapshot = lambda: replace(original(), mechanisms=tuple(
            ConfigurationMechanism(identity, 'context-manager', label, 'Description', False, 'new_session',
                display_section=phase) for identity,label,phase in (
                    ('shrink', 'Context shrinker', 'reduction'),
                    ('skills', 'Skills', 'augmentation'), ('memory', 'Memory', 'augmentation'),
                    ('http', 'HTTP', 'augmentation'), ('knowledge', 'Knowledge', 'augmentation'),
                    ('external', 'Externalization', 'externalization'))))
        frontend = self.frontend(controller, '@Context', 'back', 'back')
        frames = []
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        self.assertFalse(frontend.run_for_active_session().start)
        rows = next(frame['rows'] for frame in frames if frame['title']=='Context')
        self.assertEqual([r.label.split(' · ')[0] for r in rows[:4]], ['Skills','Memory','HTTP','Knowledge'])
        self.assertEqual([r.section for r in rows[:4]], ['Context augmentation']*4)
        self.assertEqual(rows[4].section, 'Context externalization')
        self.assertEqual(rows[5].section, 'Context reduction')
        self.assertEqual(len(rows), 7)  # Six capabilities and Back; no numbered heading actions.
        self.assertFalse(controller.changed)

    def test_active_session_configuration_requires_confirmation(self) -> None:
        controller = MockConfiguration(model="offline")
        output = self.output
        frontend = self.frontend(controller, '3', 'space', 'back', 'back', '1')

        result = frontend.run_for_active_session()

        self.assertEqual(result, ConfigurationLaunchResult(start=True))
        self.assertFalse(controller.saved)
        self.assertIn("Apply configuration", output.getvalue())
        self.assertNotIn('Save only', output.getvalue())
        self.assertNotIn('→', output.getvalue())

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

    def test_active_continue_keeps_editing_and_discard_drops_draft(self):
        for decisions in (('3',), ('2', 'back', '3')):
            with self.subTest(decisions=decisions):
                controller = MockConfiguration(model='offline')
                result = self.frontend(controller, '3', 'space', 'back', 'back', *decisions).run_for_active_session()
                self.assertFalse(result.start)
                self.assertFalse(result.saved)
                self.assertFalse(controller.enabled)
                self.assertFalse(controller.changed)
