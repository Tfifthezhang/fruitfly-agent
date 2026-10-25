"""Fresh-task Provider allowances include main and auxiliary requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.run.cli import create_parser
from fruitfly_agent.run.runtime.limits import BudgetedProviderRegistry, ModelCallBudget
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.core.data_model import ProviderView
from tests.support.faux_provider import FauxProvider


class ModelBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_and_auxiliary_share_enforced_counter_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / 'usage.json'
            budget = ModelCallBudget(2, receipt=receipt)
            first, second = FauxProvider(), FauxProvider()
            first.respond_text('main'); second.respond_text('auxiliary')
            registry = Mock(); registry.create.side_effect = [first, second]
            wrapped = BudgetedProviderRegistry(registry, budget)
            main = wrapped.create('main', {}); auxiliary = wrapped.create('auxiliary', {})
            view = ProviderView('', [], [], 'model', 128)
            await main(view).result(); await auxiliary(view).result()
            with self.assertRaises(FatalError): auxiliary(view)
            self.assertEqual(len(second.calls), 1)
            self.assertEqual(json.loads(receipt.read_text()), {'schema_version': 1, 'limit': 2, 'used': 2})

    def test_invalid_limits_and_explicit_cli_option(self):
        for value in (True, 0, -1, '2'):
            with self.assertRaises(ValueError): ModelCallBudget(value)
        self.assertEqual(create_parser().parse_args(['--max-model-calls', '8', 'task']).max_model_calls, 8)

    def test_unknown_external_usage_is_not_presented_as_actual_calls(self):
        from fruitfly_agent.lab.improvement.api import SearchReport
        from fruitfly_agent.run.adapters.improvement_results import model_usage
        text = model_usage(SearchReport(model_calls=2, model_limit=10, uncertain_model_allowance=5))
        self.assertIn('unknown (2 confirmed)', text)
        self.assertIn('quota charged: 7/10', text)
