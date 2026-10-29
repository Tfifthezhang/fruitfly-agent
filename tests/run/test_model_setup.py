"""Model wizard persistence, cancellation, and immediate offline assembly."""

import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.interactive.terminal.io.input import ReadlineLineEditor
from fruitfly_agent.interactive.terminal.io.menu import RawTerminalMenuInput
from fruitfly_agent.interactive.terminal.features.configuration.model_setup import _capabilities, _review, run_model_setup
from fruitfly_agent.providers import ProviderRegistry
from fruitfly_agent.providers.model_setup import default_parameters
from fruitfly_agent.providers.specs import MODEL_FIELD_ORDER
from fruitfly_agent.providers.config import load_env
from fruitfly_agent.providers.registry import load_model_specs, default_registry
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

    def test_readiness_includes_main_credentials_and_staged_keys_without_writes(self):
        _write_catalog(self.root / '.fruitfly/models.yaml', {'existing': 'offline-model'})
        missing = self.controller.snapshot()
        self.assertFalse(missing.ready)
        self.assertIn('missing model credential: TEST_API_KEY', missing.warnings)
        self.setup.stage_credential('existing', 'offline-placeholder')
        self.assertTrue(self.controller.snapshot().ready)
        self.assertNotIn('offline-placeholder', repr(self.controller.snapshot()))
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
        self.controller.reset()
        self.assertFalse(self.controller.snapshot().ready)

    def frontend(self, *lines, secret="offline-placeholder"):
        self.output = io.StringIO()
        return TerminalConfigurationFrontend(self.controller, input_stream=io.StringIO(secret + "\n"),
            output_stream=self.output, line_editor=ScriptedLines(*lines))

    async def test_first_run_wizard_saves_then_assembles_without_restarting_process(self):
        frontend = self.frontend("1", "", "local", "offline-model", "", "8192", "1024", "", "", "", "2", "1")
        result = frontend.run()
        self.assertTrue(result.start)
        self.assertTrue(result.saved)
        self.assertNotIn("offline-placeholder", self.output.getvalue())
        self.assertIn("Add model · Step 1 of 9", self.output.getvalue())
        self.assertIn("Service: OpenAI", self.output.getvalue())
        self.assertIn('OpenAI · Choose API protocol', self.output.getvalue())
        self.assertIn("Press Enter to use: my-model", self.output.getvalue())
        self.assertIn("This is not the model ID", self.output.getvalue())
        self.assertIn('Request and transport defaults (confirm to save)', self.output.getvalue())
        self.assertIn('"effort": "medium"', self.output.getvalue())
        self.assertIn('"first_progress_timeout": 180.0', self.output.getvalue())
        spec = load_model_specs(self.root / ".fruitfly/models.yaml")["local"]
        self.assertEqual(spec.parameters, default_parameters(spec.provider.protocol))
        self.assertEqual(spec.transport, self.setup.defaults('openai', self.values)['transport'])
        self.assertNotIn("offline-placeholder", (self.root / ".fruitfly/models.yaml").read_text())
        self.assertNotIn("offline-placeholder", (self.root / ".fruitfly/config.yaml").read_text())
        self.assertEqual((self.root / ".fruitfly/secrets.env").stat().st_mode & 0o777, 0o600)
        self.assertEqual(load_env(self.root / ".fruitfly/secrets.env")["OPENAI_API_KEY"], "offline-placeholder")
        self.factory.reload_configuration()
        provider = FauxProvider()
        provider.respond_text("configured")
        registry = ProviderRegistry()
        registry.register("openai", "responses", lambda spec, key: provider)
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
        lines = iter(("1", "", "/cancel", "3"))
        def reader(_prompt):
            output.write(_prompt)
            screens.append(output.getvalue().rsplit("\x1b[2J\x1b[H", 1)[-1])
            return next(lines)
        frontend = TerminalConfigurationFrontend(self.controller, input_stream=io.StringIO(),
            output_stream=output, line_editor=ReadlineLineEditor(output, reader=reader))
        frontend.renderer.ansi = True
        self.assertFalse(frontend.run().start)
        field_screen = screens[2]
        self.assertIn("Step 1 of 9", field_screen)
        self.assertIn("Service: OpenAI", field_screen)
        self.assertIn("models.<name>> ", field_screen)
        self.assertNotIn("╭", field_screen)
        self.assertNotIn("╭─ prompt ", field_screen)
        self.assertNotIn("1. OpenAI", field_screen)
        self.assertNotIn("↑↓", field_screen)
        self.assertFalse(self.setup.changed)

    def test_capabilities_checkboxes_persist_booleans_and_yaml_field_names(self):
        frontend = self.frontend("1", "", "local", "offline-model", "", "8192", "1024", "",
                                 "1", "5", "2", "3", "4", "2", "6", "", "2", "1")
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
        self.assertIn('sdk: openai', rendered)
        self.assertIn('protocol: responses', rendered)
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
        frontend = self.frontend("1", "", "local", "offline-model", "", "8192", "1024", "", "3", "back", "3")
        self.assertFalse(frontend.run().start)
        self.assertFalse(self.setup.changed)
        self.assertFalse((self.root / ".fruitfly/models.yaml").exists())

    def test_required_or_invalid_capabilities_are_rejected_before_staging(self):
        for field, value in (("tools", "false"), ("streaming", "false"), ("vision", "yes")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.stage(**{f"capabilities.{field}": value})
            self.assertFalse(self.setup.changed)

    def test_cancel_and_exit_write_nothing(self):
        for lines in (("back", "3"), ("1", "", "/cancel", "3"),
                      ("1", "", "local", "offline-model", "", "8192", "1024", "", "", "", "1", "3"),
                      ("1", "", "local", "offline-model", "", "8192", "1024", "", "", "", "2", "3")):
            with self.subTest(lines=lines):
                self.assertFalse(self.frontend(*lines).run().start)
                self.assertFalse(self.setup.changed)
                for name in (".fruitfly/models.yaml", ".fruitfly/secrets.env", ".fruitfly/config.yaml"):
                    self.assertFalse((self.root / name).exists())

    def test_catalog_and_environment_content_are_preserved(self):
        catalog = self.root / ".fruitfly/models.yaml"
        _write_catalog(catalog, {"existing": "old-model"})
        original = "# Keep this comment\n" + catalog.read_text() + "# Tail comment\nmetadata:\n  other: preserved\n"
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
            self.setup.stage("custom", self.values, "offline-placeholder")

    def test_existing_environment_key_is_reused_without_writing_env(self):
        self.factory.environment["EXISTING_KEY"] = "offline-placeholder"
        self.setup.stage("anthropic", {**self.values, "api_key_env": "EXISTING_KEY"}, "")
        self.controller.save()
        self.assertFalse((self.root / ".fruitfly/secrets.env").exists())
        self.assertEqual(load_model_specs(self.root / ".fruitfly/models.yaml")["local"].provider.sdk, "anthropic")

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
        with patch("fruitfly_agent.run.configuration.controller.save_harness_config", side_effect=OSError("offline write failure")):
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
        frontend = self.frontend("1", "2", "1", "", "second", "another-model", "", "8192", "1024", "", "", "", "2", "back", "3")
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
        self.assertFalse(result.saved)
        self.assertTrue(self.setup.changed)
        self.assertFalse((self.root / '.fruitfly/secrets.env').exists())
        self.assertEqual(self.factory.environment, {})
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
        with patch("fruitfly_agent.run.configuration.resolution.default_model_catalog_path", return_value=fallback):
            factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True)
            self.assertEqual(factory.configuration.snapshot().model_profiles, ())
            self.assertEqual(factory.configuration.snapshot().model_catalog, "models.yaml")
            one_shot = RunApplicationFactory(cwd=self.root, environment={})
            self.assertEqual(one_shot.selection.profile.model_profile, "shared")

    def test_chat_service_addition_uses_the_shared_catalog_contract(self):
        self.assertIn('custom', {option.option_id for option in self.setup.options()})
        self.setup.stage('custom', {**self.values, 'protocol': 'chat-completions', 'base_url': 'https://fixture.invalid/v1'}, 'offline-placeholder')
        self.controller.save()
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual((spec.provider.sdk, spec.provider.protocol), ('openai', 'chat-completions'))
        self.assertEqual(spec.service, 'generic')

    def test_sdk_and_protocol_choices_follow_the_injected_registry_without_constructing_clients(self):
        registry = default_registry()
        self.factory = RunApplicationFactory(cwd=self.root, environment={}, allow_incomplete=True,
                                            provider_registry=registry)
        self.controller = self.factory.configuration
        self.setup = self.controller.model_setup
        self.assertNotIn('demo-api', self.setup.field('custom', 'protocol', {}).choices)
        construct = Mock()
        registry.register('demo-sdk', 'demo-api', construct)
        descriptor = self.setup.field('custom', 'protocol', {'protocol': 'demo-api'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions', 'demo-api'))
        self.assertEqual(descriptor.value, 'demo-api')
        frontend = self.frontend('5', '4', 'local', 'offline-model', 'https://fixture.invalid/v1',
                                 '8192', '1024', '', '', '', '2', '1')
        self.assertTrue(frontend.run().saved)
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual((spec.provider.sdk, spec.provider.protocol), ('demo-sdk', 'demo-api'))
        self.assertIn('demo-sdk', self.output.getvalue())
        self.assertIn('demo-api', self.output.getvalue())
        construct.assert_not_called()

    def test_protocol_choices_filter_by_service_and_sdk_is_automatic(self):
        descriptor = self.setup.field('custom', 'protocol', {'sdk': 'anthropic', 'protocol': 'responses'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        self.assertEqual(descriptor.value, 'responses')
        descriptor = self.setup.field('qwen', 'protocol', {'sdk': 'openai'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        descriptor = self.setup.field('deepseek', 'protocol', {'sdk': 'openai'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        with self.assertRaisesRegex(ValueError, 'SDK is automatic'):
            self.setup.stage('custom', {**self.values, 'base_url': 'https://fixture.invalid/v1',
                'sdk': 'anthropic', 'protocol': 'responses'}, 'offline-placeholder')
        self.assertFalse(self.setup.changed)

    def test_named_service_asks_for_model_and_limits_without_model_defaults(self):
        frontend = self.frontend('4', '', 'local', 'my-qwen-model', '', '8192', '1024', '', '', '', '2', '1')
        self.assertTrue(frontend.run().saved)
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual(spec.model, 'my-qwen-model')
        self.assertEqual(spec.service, 'qwen')
        self.assertEqual(spec.provider.api_key_env, 'DASHSCOPE_API_KEY')
        self.assertEqual(spec.parameters, default_parameters(spec.provider.protocol))
        self.assertFalse(spec.capabilities.vision)
        self.assertFalse(spec.capabilities.reasoning)
        self.assertIn('Some models may not support the selected protocol', self.output.getvalue())
        self.assertIn('"total_timeout": 900.0', self.output.getvalue())
        self.assertNotIn('offline-placeholder', self.output.getvalue())

    def test_custom_service_selects_protocol_on_a_separate_screen(self):
        frontend = self.frontend('5', '3', 'local', 'offline-model', 'https://fixture.invalid/v1',
                                 '8192', '1024', '', '', '', '2', '1')
        self.assertTrue(frontend.run().saved)
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual((spec.provider.sdk, spec.provider.protocol), ('openai', 'chat-completions'))
        self.assertEqual(spec.service, 'generic')
        self.assertEqual(spec.provider.base_url, 'https://fixture.invalid/v1')
        rendered = self.output.getvalue()
        root_screen, protocol_screen = rendered.split('Add model · Custom service… · Choose API protocol', 1)
        self.assertRegex(root_screen, r'5\.\s+Custom service…')
        self.assertNotRegex(root_screen, r'1\.\s+Responses API')
        self.assertNotRegex(root_screen, r'2\.\s+Messages API')
        self.assertNotRegex(root_screen, r'3\.\s+Chat Completions API')
        self.assertRegex(protocol_screen, r'3\.\s+chat-completions')
        self.assertNotIn('offline-placeholder', rendered)

    def test_back_from_custom_protocol_returns_to_services_without_staging(self):
        frontend = self.frontend('5', 'back', '1', '', '/cancel', '3')
        self.assertFalse(frontend.run().start)
        rendered = self.output.getvalue()
        self.assertEqual(rendered.count('Add model · Choose a service'), 2)
        self.assertIn('Add model · Custom service… · Choose API protocol', rendered)
        self.assertIn('Service: OpenAI', rendered)
        self.assertFalse(self.setup.changed)
        self.assertFalse((self.root / '.fruitfly/models.yaml').exists())

    def test_quit_custom_protocol_and_preset_field_cancel_write_nothing(self):
        for lines in (('5', 'q', '3'), ('3', '', '/cancel', '3'), ('4', '', '/cancel', '3')):
            with self.subTest(lines=lines):
                self.assertFalse(self.frontend(*lines).run().start)
                self.assertFalse(self.setup.changed)
                self.assertFalse((self.root / '.fruitfly/models.yaml').exists())

    def test_reasoning_declaration_does_not_change_protocol_parameter_defaults(self):
        for option in self.setup.options():
            for reasoning in ('true', 'false'):
                with self.subTest(service=option.option_id, reasoning=reasoning):
                    values = {**self.values, 'capabilities.reasoning': reasoning}
                    if option.option_id == 'custom':
                        values['base_url'] = 'https://fixture.invalid/v1'
                    self.assertEqual(self.setup.defaults(option.option_id, values)['parameters'], default_parameters(self.setup.field(option.option_id, 'protocol', values).value))
                    self.setup.stage(option.option_id, values, 'offline-placeholder')
                    staged = self.setup.models(self.controller.profile())['local']
                    self.assertEqual(staged.parameters, default_parameters(staged.provider.protocol))
                    self.assertEqual(staged.capabilities.reasoning, reasoning == 'true')
                    self.controller.reset()

    def test_service_defaults_are_isolated_between_reviews(self):
        defaults = self.setup.defaults('qwen', {})
        defaults['parameters']['extra_body'] = {'future_feature': True}
        defaults['transport']['retry_max'] = 99
        again = self.setup.defaults('qwen', {})
        self.assertEqual(again['parameters'], {'reasoning_effort': 'medium'})
        self.assertEqual(again['transport']['retry_max'], 3)

    def test_every_service_protocol_can_be_selected_and_saved_without_a_sdk_question(self):
        expected = {'openai': ('responses', 'chat-completions'),
            'anthropic': ('messages', 'chat-completions'),
            'deepseek': ('responses', 'messages', 'chat-completions'),
            'qwen': ('responses', 'messages', 'chat-completions'),
            'custom': ('responses', 'messages', 'chat-completions')}
        self.assertEqual(len(self.setup.options()), 5)
        with patch('openai.AsyncOpenAI') as openai, patch('anthropic.AsyncAnthropic') as anthropic:
            for index, (name, protocols) in enumerate(expected.items(), 1):
                field = self.setup.field(name, 'protocol', {})
                self.assertEqual(field.choices, protocols)
                for protocol in protocols:
                    with self.subTest(service=name, protocol=protocol):
                        alias = name + '-' + protocol
                        values = {'protocol': protocol}
                        model = self.setup.field(name, 'model', values).value or 'fixture-model'
                        frontend = self.frontend(str(index), str(field.choices.index(protocol) + 1),
                            alias, model, 'https://fixture.invalid/v1' if name == 'custom' else '',
                            '100000', '4096', '', '', '', '2')
                        run_model_setup(frontend._model_form(), self.setup)
                        self.controller.save()
                        spec = load_model_specs(self.root / '.fruitfly/models.yaml')[alias]
                        self.assertEqual(spec.provider.protocol, protocol)
                        self.assertEqual(spec.provider.sdk, 'anthropic' if protocol == 'messages' else 'openai')
                        self.assertEqual(spec.parameters, default_parameters(protocol))
                        import yaml
                        raw = yaml.safe_load((self.root / '.fruitfly/models.yaml').read_text())['models'][alias]
                        self.assertEqual(tuple(raw), MODEL_FIELD_ORDER)
                        rendered = self.output.getvalue()
                        self.assertLess(rendered.index('Choose API protocol'), rendered.index('models.<name>'))
                        self.assertNotIn('Add model · sdk', rendered)
                        self.assertNotIn('offline-placeholder', rendered)
        openai.assert_not_called()
        anthropic.assert_not_called()

    def test_back_to_protocol_recalculates_endpoint_parameters_and_keeps_edited_alias(self):
        frontend = self.frontend('4', '3', 'local', 'my-model', '', 'back', '2', '', '', '', '8192', '1024', '', '', '', '2', '1')
        self.assertTrue(frontend.run().saved)
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual(spec.provider.protocol, 'messages')
        self.assertEqual(spec.provider.sdk, 'anthropic')
        self.assertEqual(spec.provider.base_url, 'https://maas.qianwenaiapi.com/apps/anthropic')
        self.assertEqual(spec.parameters, default_parameters(spec.provider.protocol))
        self.assertEqual(spec.model, 'my-model')
        self.assertNotIn('extra_body', spec.parameters)

    def test_ambiguous_sdk_reports_a_configuration_error_without_staging(self):
        registry = self.setup.registry
        construct = Mock()
        registry.register('first', 'fixture-api', construct)
        registry.register('second', 'fixture-api', construct)
        frontend = self.frontend('5', '4', 'q')
        self.assertFalse(frontend.run().start)
        self.assertIn('explicit default adapter', self.output.getvalue())
        self.assertFalse(self.setup.changed)
        construct.assert_not_called()

    def test_parameters_editor_retries_invalid_input_and_saves_the_reviewed_mapping(self):
        parameters = '{"reasoning":{"effort":"high"},"temperature":0.3,"extra_body":{"future_feature":true}}'
        frontend = self.frontend('1', '', 'local', 'offline-model', '', '8192', '1024', '', '',
            '{broken', '[]', '{"model":"override"}', parameters, '2', '1')
        self.assertTrue(frontend.run().saved)
        import json
        spec = load_model_specs(self.root / '.fruitfly/models.yaml')['local']
        self.assertEqual(spec.parameters, json.loads(parameters))
        rendered = self.output.getvalue()
        self.assertIn('parameters must be a JSON object', rendered)
        self.assertIn('runtime-owned request fields', rendered)
        self.assertIn('"effort": "high"', rendered)
        self.assertNotIn('offline-placeholder', rendered)

    def test_parameters_can_explicitly_use_server_defaults(self):
        frontend = self.frontend('1', '', 'local', 'offline-model', '', '8192', '1024', '', '', '{}', '2', '1')
        self.assertTrue(frontend.run().saved)
        self.assertEqual(load_model_specs(self.root / '.fruitfly/models.yaml')['local'].parameters, {})

    def test_parameters_cancellation_writes_nothing_and_does_not_read_the_key(self):
        frontend = self.frontend('1', '', 'local', 'offline-model', '', '8192', '1024', '', '', '/cancel', '3')
        self.assertFalse(frontend.run().start)
        self.assertFalse(self.setup.changed)
        self.assertEqual(frontend.input.tell(), 0)
        self.assertFalse((self.root / '.fruitfly/models.yaml').exists())

    def test_failed_save_restores_original_catalog_before_field_reordering(self):
        catalog = self.root / '.fruitfly/models.yaml'
        _write_catalog(catalog, {'existing': 'old-model'})
        original = catalog.read_bytes()
        self.stage()
        with patch('fruitfly_agent.run.configuration.controller.save_harness_config', side_effect=OSError('offline write failure')):
            with self.assertRaises(OSError):
                self.controller.save()
        self.assertEqual(catalog.read_bytes(), original)
        self.assertTrue(self.setup.changed)

    def test_ansi_review_pages_expose_all_values_before_confirmation(self):
        frontend = self.frontend('3', '3', '3', '2')
        frontend.renderer.ansi = True
        text = '\n'.join(f'transport.offline_field_{index}: {index}' for index in range(35))
        with patch('shutil.get_terminal_size', return_value=os.terminal_size((80, 24))):
            self.assertEqual(_review(frontend._model_form(), text), 'Stage model')
        rendered = self.output.getvalue()
        for index in range(35):
            self.assertIn(f'transport.offline_field_{index}: {index}', rendered)
        self.assertIn('Review 4/4', rendered)
        self.assertFalse(self.setup.changed)
