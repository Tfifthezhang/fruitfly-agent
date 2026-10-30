"""Model configuration behavior and failure contracts."""
import tempfile
import unittest
from fruitfly_agent.providers.model_setup import default_parameters
from tests.support.run import _write_catalog

from tests.support.model_setup import ModelSetupWorkspace


class ModelSetupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.workspace = ModelSetupWorkspace(self.enterContext(tempfile.TemporaryDirectory()))

    def test_readiness_includes_main_credentials_and_staged_keys_without_writes(self):
        _write_catalog(self.workspace.root / '.fruitfly/models.yaml', {'existing': 'offline-model'})
        missing = self.workspace.controller.snapshot()
        self.assertFalse(missing.ready)
        self.assertIn('missing model credential: TEST_API_KEY', missing.warnings)
        self.workspace.setup.stage_credential('existing', 'offline-placeholder')
        self.assertTrue(self.workspace.controller.snapshot().ready)
        self.assertNotIn('offline-placeholder', repr(self.workspace.controller.snapshot()))
        self.assertFalse((self.workspace.root / '.fruitfly/secrets.env').exists())
        self.workspace.controller.reset()
        self.assertFalse(self.workspace.controller.snapshot().ready)

    def test_required_or_invalid_capabilities_are_rejected_before_staging(self):
        for field, value in (("tools", "false"), ("streaming", "false"), ("vision", "yes")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.workspace.stage(**{f"capabilities.{field}": value})
            self.assertFalse(self.workspace.setup.changed)

    def test_invalid_fields_never_stage_or_echo_secret(self):
        cases = ({"profile": "bad label"}, {"model": ""}, {"context_window": "no"},
                 {"max_output_tokens": "8192"}, {"base_url": "https://user:password@example.invalid"},
                 {"api_key_env": "INVALID-NAME"})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError) as failure:
                self.workspace.stage(**changes)
            self.assertNotIn("offline-placeholder", str(failure.exception))
            self.assertFalse(self.workspace.setup.changed)
        with self.assertRaisesRegex(ValueError, "API base URL"):
            self.workspace.setup.stage("custom", self.workspace.values, "offline-placeholder")

    def test_protocol_choices_filter_by_service_and_sdk_is_automatic(self):
        descriptor = self.workspace.setup.field('custom', 'protocol', {'sdk': 'anthropic', 'protocol': 'responses'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        self.assertEqual(descriptor.value, 'responses')
        descriptor = self.workspace.setup.field('qwen', 'protocol', {'sdk': 'openai'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        descriptor = self.workspace.setup.field('deepseek', 'protocol', {'sdk': 'openai'})
        self.assertEqual(descriptor.choices, ('responses', 'messages', 'chat-completions'))
        with self.assertRaisesRegex(ValueError, 'SDK is automatic'):
            self.workspace.setup.stage('custom', {**self.workspace.values, 'base_url': 'https://fixture.invalid/v1',
                'sdk': 'anthropic', 'protocol': 'responses'}, 'offline-placeholder')
        self.assertFalse(self.workspace.setup.changed)

    def test_reasoning_declaration_does_not_change_protocol_parameter_defaults(self):
        for option in self.workspace.setup.options():
            for reasoning in ('true', 'false'):
                with self.subTest(service=option.option_id, reasoning=reasoning):
                    values = {**self.workspace.values, 'capabilities.reasoning': reasoning}
                    if option.option_id == 'custom':
                        values['base_url'] = 'https://fixture.invalid/v1'
                    self.assertEqual(self.workspace.setup.defaults(option.option_id, values)['parameters'], default_parameters(self.workspace.setup.field(option.option_id, 'protocol', values).value))
                    self.workspace.setup.stage(option.option_id, values, 'offline-placeholder')
                    staged = self.workspace.setup.models(self.workspace.controller.profile())['local']
                    self.assertEqual(staged.parameters, default_parameters(staged.provider.protocol))
                    self.assertEqual(staged.capabilities.reasoning, reasoning == 'true')
                    self.workspace.controller.reset()

    def test_service_defaults_are_isolated_between_reviews(self):
        defaults = self.workspace.setup.defaults('qwen', {})
        defaults['parameters']['extra_body'] = {'future_feature': True}
        defaults['transport']['retry_max'] = 99
        again = self.workspace.setup.defaults('qwen', {})
        self.assertEqual(again['parameters'], {'reasoning_effort': 'medium'})
        self.assertEqual(again['transport']['retry_max'], 3)
