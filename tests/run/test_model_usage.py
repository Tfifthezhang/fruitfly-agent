"""Main and auxiliary Provider usage is observed without limiting requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from fruitfly_agent.run.cli import create_parser
from fruitfly_agent.run.runtime.usage import ModelUsage,ObservedProviderRegistry
from fruitfly_agent.core.data_model import ProviderView
from tests.support.faux_provider import FauxProvider
from fruitfly_agent.providers import ProviderRegistry,ModelSpec


class ModelUsageTests(unittest.IsolatedAsyncioTestCase):
    def test_discovery_and_validation_do_not_construct_or_record_requests(self):
        registry=ProviderRegistry();constructed=Mock();registry.register('fixture-sdk','fixture-api',constructed)
        usage=ModelUsage();wrapped=ObservedProviderRegistry(registry,usage)
        spec=ModelSpec.from_dict('fixture',{'sdk':'fixture-sdk','protocol':'fixture-api','model':'offline','context_window':8192,'api_key_env':'OFFLINE_KEY'})
        self.assertEqual(wrapped.registered_pairs(),(('fixture-sdk','fixture-api'),))
        wrapped.validate(spec);self.assertEqual(usage.used,0);constructed.assert_not_called()

    async def test_main_and_auxiliary_are_recorded_without_a_shared_allowance(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'usage.json';usage=ModelUsage(receipt=path)
            first,second=FauxProvider(),FauxProvider();first.respond_text('main')
            second.respond_text('auxiliary');second.respond_text('again')
            registry=Mock();registry.create.side_effect=[first,second]
            wrapped=ObservedProviderRegistry(registry,usage)
            main,auxiliary=wrapped.create('main',{}),wrapped.create('auxiliary',{})
            view=ProviderView('',[],[],'model',128)
            await main(view).result();await auxiliary(view).result();await auxiliary(view).result()
            value=json.loads(path.read_text())
            self.assertEqual(value['used'],3);self.assertNotIn('limit',value)
            self.assertEqual(len({r['id']for r in value['requests']}),3)
            self.assertTrue(all(r['status']=='completed'for r in value['requests']))

    def test_removed_cli_option_is_rejected(self):
        with self.assertRaises(SystemExit):create_parser().parse_args(['--max-model-calls','8','task'])

    def test_interrupted_observation_remains_unknown(self):
        usage=ModelUsage();identity=usage.begin('model');usage.finish(identity,status='interrupted')
        self.assertIsNone(usage.requests[identity]['usage'])
        self.assertEqual(usage.used,1)

    def test_partial_token_receipts_report_a_subtotal_and_unknown_total(self):
        from fruitfly_agent.improvement.execution.facts import model_usage_facts
        rows = [{'kind': 'request', 'id': 'first'}, {'kind': 'request', 'id': 'second'},
                {'kind': 'response', 'attempt_id': 'first',
                 'usage': {'input_tokens': 100, 'output_tokens': 20}}]
        facts = {v.resource: v.used for v in model_usage_facts(rows, 2)}
        self.assertEqual(facts['reported_model_calls'], 1)
        self.assertEqual(facts['reported_input_tokens'], 100)
        self.assertIsNone(facts['input_tokens'])
        self.assertIsNone(facts['output_tokens'])
