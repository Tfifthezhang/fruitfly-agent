"""Catalog validation, service rules and construction share one offline contract."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.providers.registry import load_model_specs, default_registry, ProviderRegistry
from fruitfly_agent.providers.specs import ModelSpec


class ModelConfigurationTests(unittest.TestCase):
    def spec(self, **changes):
        return ModelSpec.from_dict('model', {'sdk': 'openai', 'protocol': 'responses', 'model': 'deepseek-flash',
            'service': 'deepseek', 'context_window': 1048576, 'max_output_tokens': 32768,
            'api_key_env': 'OFFLINE_KEY', **changes})

    def test_request_transport_and_service_survive_round_trip_and_real_factory(self):
        spec = self.spec(parameters={'reasoning': {'effort': 'high'}}, transport={'total_timeout': 123})
        self.assertEqual(ModelSpec.from_dict(spec.id, spec.to_dict()), spec)
        with patch('openai.AsyncOpenAI') as sdk:
            provider = default_registry().create(spec, {'OFFLINE_KEY': 'offline-placeholder'})
        self.assertEqual(provider.request_options, {'reasoning': {'effort': 'high'}})
        self.assertEqual(provider.transport_parameters['total_timeout'], 123)
        self.assertEqual(provider.service, 'deepseek')
        sdk.assert_called_once()

    def test_sdk_and_protocol_choose_the_matching_native_adapter(self):
        with patch('openai.AsyncOpenAI') as openai, patch('anthropic.AsyncAnthropic') as anthropic:
            for sdk, protocol in (('openai', 'responses'), ('openai', 'chat-completions'), ('anthropic', 'messages')):
                with self.subTest(sdk=sdk, protocol=protocol):
                    spec = self.spec(sdk=sdk, protocol=protocol, service='generic')
                    self.assertEqual((spec.provider.sdk, spec.provider.protocol), (sdk, protocol))
                    self.assertNotIn('provider', spec.to_dict())
                    self.assertEqual(ModelSpec.from_dict(spec.id, spec.to_dict()), spec)
                    provider = default_registry().create(spec, {'OFFLINE_KEY': 'offline-placeholder'})
                    self.assertEqual(provider.protocol, protocol)
            self.assertEqual(openai.call_count, 2)
            self.assertEqual(anthropic.call_count, 1)

    def test_old_or_missing_fields_and_unsupported_sdk_protocol_pairs_fail_offline(self):
        base = self.spec().to_dict()
        cases = [
            {**base, 'provider': 'openai'},
            {**base, 'provider': 'openai-chat'},
            {k: v for k, v in base.items() if k != 'sdk'},
            {k: v for k, v in base.items() if k != 'protocol'},
            {**base, 'protocol': 'openai-chat'},
        ]
        with patch('openai.AsyncOpenAI') as openai, patch('anthropic.AsyncAnthropic') as anthropic:
            for raw in cases:
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    ModelSpec.from_dict('model', raw)
            for sdk, protocol in (('anthropic', 'responses'), ('anthropic', 'chat-completions'), ('openai', 'messages')):
                with self.subTest(sdk=sdk, protocol=protocol), self.assertRaisesRegex(ValueError, 'unregistered SDK/protocol'):
                    default_registry().create(self.spec(sdk=sdk, protocol=protocol), {'OFFLINE_KEY': 'offline-placeholder'})
        openai.assert_not_called()
        anthropic.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'models.yaml'
            path.write_text('models: {old: {provider: openai-chat, model: fixture, context_window: 8192}}')
            with self.assertRaises(ValueError):
                load_model_specs(path)

    def test_registration_dispatches_on_both_sdk_and_protocol(self):
        registry = ProviderRegistry()
        first, second, third = object(), object(), object()
        registry.register('openai', 'responses', lambda spec, key: first)
        registry.register('openai', 'chat-completions', lambda spec, key: second)
        registry.register('fixture-sdk', 'responses', lambda spec, key: third)
        for sdk, protocol, marker in (('openai', 'responses', first),
                ('openai', 'chat-completions', second), ('fixture-sdk', 'responses', third)):
            with self.subTest(sdk=sdk, protocol=protocol):
                spec = self.spec(sdk=sdk, protocol=protocol, service='generic')
                self.assertIs(registry.create(spec, {'OFFLINE_KEY': 'offline-placeholder'}), marker)
        with self.assertRaisesRegex(ValueError, 'unregistered SDK/protocol'):
            registry.create(self.spec(sdk='unregistered-sdk', service='generic'), {'OFFLINE_KEY': 'offline-placeholder'})

    def test_invalid_parameters_and_false_capabilities_fail_without_constructing_clients(self):
        cases = [
            {'schema_version': 1}, {'unexpected': 2}, {'context_window': True},
            {'max_output_tokens': 0}, {'context_window': '1000'},
            {'capabilities': {'reasoning': 'false'}}, {'capabilities': []},
            {'parameters': {'retry_max': 2}}, {'transport': {'reasoning': {'effort': 'high'}}},
            {'parameters': {'stream': False}}, {'parameters': {'model': 'override'}},
            {'parameters': {'extra_body': {'max_output_tokens': 999999}}},
            {'parameters': {'extra_body': {'tools': []}}},
            {'parameters': {'extra_headers': {'Authorization': 'offline-placeholder'}}},
            {'parameters': {'reasoning': {'effort': 'medium'}}},
            {'parameters': {'temperature': 0.2}}, {'parameters': {'top_p': 0.5}},
            {'parameters': {'include': ['reasoning.encrypted_content']}},
            {'parameters': {'text': {'verbosity': 'high'}}},
            {'parameters': {'reasoning': {'summary': 'auto'}}},
            {'parameters': {'reasoning_effort': 'high'}},
            {'parameters': {'temperature': float('nan')}},
            {'service': 'missing-service'}, {'service': 'anthropic'},
        ]
        with patch('openai.AsyncOpenAI') as sdk:
            for case in cases:
                with self.subTest(case=case), self.assertRaises((ValueError, TypeError)):
                    self.spec(**case)
        sdk.assert_not_called()

    def test_deepseek_off_and_native_protocol_fields_are_explicit(self):
        self.spec(parameters={'reasoning': {'effort': 'none'}, 'temperature': .2})
        self.spec(sdk='anthropic', protocol='messages', parameters={'thinking': {'type': 'enabled'}, 'output_config': {'effort': 'high'}})
        self.spec(protocol='chat-completions', parameters={'reasoning_effort': 'max',
            'extra_body': {'thinking': {'type': 'enabled'}}})
        for options in ({'thinking': {'type': 'adaptive'}}, {'thinking': {'type': 'enabled', 'budget_tokens': 1024}},
                        {'output_config': {'effort': 'invalid'}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.spec(sdk='anthropic', protocol='messages', parameters=options)

    def test_generic_extension_does_not_infer_vendor_from_url_or_model(self):
        spec = self.spec(service='generic', parameters={'reasoning': {'effort': 'medium'},
            'extra_body': {'custom_feature': {'enabled': True}}})
        self.assertEqual(spec.parameters['reasoning']['effort'], 'medium')

    def test_catalog_rejects_duplicate_keys_instead_of_silently_replacing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'models.yaml'
            for text in ('models: {}\nmodels: {}\n', 'models: {one: {sdk: openai, protocol: responses, sdk: anthropic, protocol: messages}}',
                         'schema_version: 1\nmodels: {}'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    load_model_specs(path)

    def test_chat_is_registered_and_factory_validates_before_sdk(self):
        spec = self.spec(protocol='chat-completions', parameters={'reasoning_effort': 'high'})
        with patch('openai.AsyncOpenAI') as sdk:
            provider = default_registry().create(spec, {'OFFLINE_KEY': 'offline-placeholder'})
            self.assertEqual(provider.protocol, 'chat-completions')
            sdk.assert_called_once()

    def test_registered_service_extends_existing_protocol_without_changing_hosts(self):
        import fruitfly_agent.providers.services as services
        seen = []
        def validate(protocol, model, options):
            seen.append((protocol, model))
            if options.get('temperature', 0) > 1:
                raise ValueError('fixture endpoint temperature limit')
        with patch.dict(services._SERVICES):
            services.register_service(services.ServiceDefinition('fixture-endpoint', frozenset({'responses'}), validate))
            spec = self.spec(service='fixture-endpoint', parameters={'temperature': .5})
            self.assertEqual(spec.service, 'fixture-endpoint')
            self.assertEqual(seen, [('responses', 'deepseek-flash')])
            with self.assertRaisesRegex(ValueError, 'temperature limit'):
                self.spec(service='fixture-endpoint', parameters={'temperature': 1.5})
            with self.assertRaisesRegex(ValueError, 'distinct'):
                services.register_service(services.ServiceDefinition('fixture-endpoint', frozenset({'responses'}), validate))

    def test_structured_output_requires_its_protocol_shape_and_thinking_budget_must_fit(self):
        self.spec(parameters={'text': {'format': {'type': 'json_schema', 'name': 'result',
            'schema': {'type': 'object'}, 'strict': True}}})
        for options in ({'text': {'format': {'type': 'json_schema'}}},
                        {'text': {'format': {'type': 'json_schema', 'name': 'x', 'schema': [], 'strict': True}}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.spec(parameters=options)
        self.spec(sdk='anthropic', protocol='messages', service='anthropic', parameters={
            'thinking': {'type': 'enabled', 'budget_tokens': 1024}})
        with self.assertRaises(ValueError):
            self.spec(sdk='anthropic', protocol='messages', service='anthropic', max_output_tokens=1024,
                parameters={'thinking': {'type': 'enabled', 'budget_tokens': 1024}})
