"""One packaged data table supplies service discovery and runtime controls."""
from importlib.resources import files
from unittest import TestCase
from unittest.mock import patch

import yaml

from fruitfly_agent.providers import services
from fruitfly_agent.providers.model_setup import SERVICES, setup_initial, setup_defaults, default_parameters
from fruitfly_agent.providers.openai import OpenAIProvider


class ServiceTableTests(TestCase):
    def table(self):
        return yaml.safe_load(files('fruitfly_agent.providers').joinpath('services.yaml').read_text(encoding='utf-8'))

    def test_packaged_table_drives_setup_without_a_separate_vendor_list(self):
        table = self.table()
        self.assertEqual(set(table['services']), {'openai', 'anthropic', 'deepseek', 'qwen', 'generic'})
        self.assertEqual([item.service for item in SERVICES], list(table['services']))
        for choice in SERVICES:
            row = table['services'][choice.service]
            self.assertEqual(choice.label, row['label'])
            self.assertEqual(choice.protocol, row['default_protocol'])
            self.assertNotIn('model', setup_initial(choice.id, choice.protocol))
            self.assertNotIn('context_window', setup_initial(choice.id, choice.protocol))
            self.assertEqual(setup_defaults(choice.id, {})['parameters'], default_parameters(choice.protocol))

    def test_changing_a_table_endpoint_changes_both_setup_and_sdk_construction(self):
        table = self.table()
        row = table['services']['qwen']['protocols']['responses']
        row.update(base_url='https://fixture.invalid/v2', input_count=True)
        entries = services.parse_service_table(yaml.safe_dump(table))
        with patch.dict(services._SERVICES, {item.id: item for item in entries}):
            self.assertEqual(setup_initial('qwen', 'responses')['base_url'], row['base_url'])
            with patch('openai.AsyncOpenAI') as sdk:
                provider = OpenAIProvider(api_key='offline-placeholder', model='any-model', service='qwen')
            self.assertEqual(sdk.call_args.kwargs['base_url'], row['base_url'])
            self.assertTrue(provider.input_count_supported)

    def test_table_rejects_model_policies_and_invalid_client_metadata(self):
        for change in ('model', 'parameters', 'flag', 'endpoint', 'default'):
            table = self.table()
            row = table['services']['qwen']
            if change in {'model', 'parameters'}:
                row[change] = 'not-a-service-field'
            elif change == 'flag':
                row['protocols']['responses']['input_count'] = 1
            elif change == 'endpoint':
                row['protocols']['responses']['base_url'] = 'https://user:secret@fixture.invalid'
            else:
                row['default_protocol'] = 'not-supported'
            with self.subTest(change=change), self.assertRaises(ValueError):
                services.parse_service_table(yaml.safe_dump(table))
