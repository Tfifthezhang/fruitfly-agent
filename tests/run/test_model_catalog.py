"""Catalog ordering preserves authored values and comments across existing entries."""
import unittest

import yaml

from fruitfly_agent.providers.specs import MODEL_FIELD_ORDER
from fruitfly_agent.run.configuration.model_catalog import order_model_catalog
from fruitfly_agent.run.configuration.model_setup import _append_models


class ModelCatalogOrderTests(unittest.TestCase):
    def test_block_comments_inline_comments_and_literal_content_survive_ordering(self):
        text = '''# Keep header
models:
  original:
    sdk: openai # client comment
    transport:
      timeout: 123 # waiting comment
    # output budget
    max_output_tokens: 1024
    parameters:
      extra_body:
        instructions: |
          # literal content
          keep this line
    # context budget
    context_window: 8192
    model: fixture
    protocol: responses
# Keep footer
metadata:
  notes: unchanged
'''
        result = order_model_catalog(text)
        self.assertEqual(yaml.safe_load(result), yaml.safe_load(text))
        for comment in ('# Keep header', '# client comment', '# waiting comment', '# output budget',
                        '# context budget', '# literal content', '# Keep footer'):
            self.assertIn(comment, result)
        self.assertIn('# context budget\n    context_window', result)
        self.assertIn('# output budget\n    max_output_tokens', result)
        entry = yaml.safe_load(result)['models']['original']
        self.assertEqual(list(entry), [name for name in MODEL_FIELD_ORDER if name in entry])
        self.assertEqual(list(entry)[-1], 'transport')
        self.assertEqual(order_model_catalog(result), result)
        self.assertTrue(result.endswith('# Keep footer\nmetadata:\n  notes: unchanged\n'))

    def test_flow_entries_keep_authored_values_and_receive_the_same_field_order(self):
        text = 'models:\n  fixture: {sdk: openai, transport: {timeout: 12}, model: fixture, protocol: responses, context_window: 8192}\n'
        result = order_model_catalog(text)
        self.assertEqual(yaml.safe_load(result), yaml.safe_load(text))
        self.assertEqual(list(yaml.safe_load(result)['models']['fixture']),
            ['protocol', 'sdk', 'model', 'context_window', 'transport'])

    def test_append_orders_existing_and_new_models_with_transport_last(self):
        existing = {'sdk': 'openai', 'transport': {'timeout': 12}, 'model': 'old',
                    'protocol': 'responses', 'context_window': 8192}
        incoming = {**existing, 'model': 'new', 'parameters': {'reasoning': {'effort': 'medium'}}}
        text = '# existing header\n' + yaml.safe_dump({'models': {'old': existing}}, sort_keys=False)
        result = _append_models(text, {'new': incoming})
        models = yaml.safe_load(result)['models']
        self.assertEqual(models, {'old': existing, 'new': incoming})
        self.assertIn('# existing header', result)
        for entry in models.values():
            self.assertEqual(list(entry), [name for name in MODEL_FIELD_ORDER if name in entry])
            self.assertEqual(list(entry)[-1], 'transport')

    def test_duplicate_fields_are_rejected_instead_of_lost_during_reordering(self):
        text = 'models:\n  fixture:\n    sdk: openai\n    sdk: anthropic\n    protocol: messages\n'
        with self.assertRaisesRegex(ValueError, 'distinct field names'):
            order_model_catalog(text)

    def test_block_catalog_without_a_final_newline_does_not_join_reordered_fields(self):
        text = 'models:\n  fixture:\n    transport: {timeout: 12}\n    sdk: openai\n    model: fixture\n    protocol: responses\n    context_window: 8192'
        result = order_model_catalog(text)
        self.assertEqual(yaml.safe_load(result), yaml.safe_load(text))
        self.assertEqual(list(yaml.safe_load(result)['models']['fixture'])[-1], 'transport')
