"""Configuration menu choices, drafts, and startup confirmation."""

from dataclasses import replace
import io
import unittest

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.contracts.configuration import ConfigurationLaunchResult, ConfigurationMechanism
from tests.support.terminal import MenuScriptedLines


from tests.support.configuration import MockConfiguration, AlgorithmConfiguration


class TerminalConfigurationFrontendTest(unittest.TestCase):
    def test_details_open_and_back_collapse_without_staging_configuration(self):
        controller = AlgorithmConfiguration()
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Details · Variant A',
            'back', 'back', 'back', 'back')
        frames = []
        render = frontend.renderer.render
        def capture(**frame):
            frames.append(frame)
            render(**frame)
        frontend.renderer.render = capture
        self.assertFalse(frontend.run_for_active_session().start)
        category = [f for f in frames if f['title'] == 'Compaction']
        self.assertFalse(any(r.references for r in category[1]['rows']))
        self.assertTrue(any(r.references for r in category[2]['rows']))
        self.assertFalse(any(r.references for r in category[3]['rows']))
        self.assertEqual(category[2]['rows'][category[2]['selected']].label, 'Details · Variant A ▴')
        self.assertFalse(any(r.label == 'Configuration location' for f in frames for r in f['rows']))
        self.assertEqual(controller.algorithm, 'variant-b')
        self.assertFalse(controller.changed)

    def test_real_lab_configuration_hides_tuning_but_keeps_resource_inputs_and_values(self):
        from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection
        from fruitfly_agent.run.configuration.profile import HarnessProfile
        from fruitfly_agent.run.configuration.views import mechanism_views
        from fruitfly_agent.interactive.terminal.features.configuration.menu import _category_rows
        catalog=builtin_catalog()
        profile=HarnessProfile('daily', mechanisms=(
            MechanismSelection('compaction', parameters={'keep_recent_tokens':12345}),
            MechanismSelection('live-http', parameters={'endpoint':'https://example.test/?q={query}'}),
            MechanismSelection('skill-document', parameters={'source_path':'.skills/check/SKILL.md'})))
        mechanisms,groups=mechanism_views(profile,catalog,[])
        snapshot=replace(MockConfiguration(model='offline').snapshot(), mechanisms=mechanisms,selection_groups=groups)
        rows,actions=_category_rows(snapshot,'context-manager','reduction',{}, details={'compaction'})
        self.assertFalse(any(a.kind=='parameter' for a in actions))
        self.assertNotIn('Enabled · True',[r.label for r in rows])
        compaction=next(m for m in mechanisms if m.mechanism_id=='compaction')
        self.assertEqual(next(p.value for p in compaction.parameters if p.name=='keep_recent_tokens'),12345)
        self.assertTrue(any(('Implementation',compaction.implementation_path) in r.references for r in rows))
        _,actions=_category_rows(snapshot,'context-manager','live-http',{})
        self.assertEqual([a.parameter.name for a in actions if a.kind=='parameter'],['endpoint'])
        _,actions=_category_rows(snapshot,'context-manager','skill-document',{})
        self.assertEqual([a.parameter.name for a in actions if a.kind=='parameter'],['initial_text','source_path'])

    def setUp(self) -> None:
        self.output = io.StringIO()

    def frontend(self, controller, *lines):
        return TerminalConfigurationFrontend(
            controller, output_stream=self.output, line_editor=MenuScriptedLines(self.output, *lines),
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

    def test_module_expands_readable_algorithms_and_references_without_tuning_fields(self) -> None:
        controller = AlgorithmConfiguration()
        output = self.output
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Variant C', '@Details · Variant C', 'back', 'back', 'back', 'back', '1')
        result = frontend.run_for_active_session()
        self.assertEqual(result, ConfigurationLaunchResult(start=True, saved=True))
        self.assertEqual(controller.algorithm, "variant-c")
        rendered = output.getvalue()
        self.assertIn('[✓] Reduction · Variant B', rendered)
        self.assertIn('[✓] Reduction · Variant C', rendered)
        self.assertIn('○ Variant A', rendered)
        self.assertIn('● Variant C', rendered)
        self.assertNotIn('Maximum tokens', rendered)
        self.assertIn('Detailed algorithm tuning', rendered)
        self.assertIn('Implementation: tests/support/configuration.py', rendered)
        self.assertIn('Guide: tests/support/README.md', rendered)
        self.assertIn('Configuration: /workspace/fruitfly.yaml', rendered)
        self.assertIn('profiles.default.mechanisms', rendered)
        self.assertIn('Modified', rendered)

    def test_single_implementation_has_description_and_paths_without_tuning_fields(self) -> None:
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
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Details · Variant B',
            'back', 'back', 'back', 'back')
        self.assertFalse(frontend.run_for_active_session().start)
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertEqual(controller.max_tokens, 1000)
        self.assertIn('Details · Variant B', output.getvalue())
        self.assertNotIn('● Variant B', output.getvalue())
        self.assertNotIn('Maximum tokens', output.getvalue())
        self.assertIn('Implementation: tests/support/configuration.py', output.getvalue())
        self.assertFalse(controller.changed)

    def test_dropdown_cancel_keeps_algorithm_and_toggle_remembers_choice(self) -> None:
        controller = AlgorithmConfiguration()
        output = self.output
        frontend = self.frontend(controller, '@Compaction', '@Reduction', 'back', 'space', 'space',
            'back', 'back', '1')
        self.assertTrue(frontend.run_for_active_session().saved)
        self.assertEqual(controller.algorithm, "variant-b")
        self.assertTrue(controller.enabled)
        self.assertNotIn("Settings", output.getvalue())

    def test_declared_user_input_stays_visible_and_cancel_or_invalid_input_preserves_value(self) -> None:
        controller = AlgorithmConfiguration()
        original = controller.snapshot
        controller.snapshot = lambda: replace(original(), mechanisms=tuple(
            replace(m, input_parameters=('max_tokens',)) for m in original().mechanisms))
        frames = []
        frontend = self.frontend(controller, '@Compaction', '@Reduction', '@Maximum tokens', '/cancel',
            '@Maximum tokens', '0', 'back', 'back', 'back')
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
        self.assertTrue(all(frame['title'] == 'Compaction' for frame in inputs))
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
