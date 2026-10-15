"""Main and auxiliary invocations reserve from one bounded trial allocation."""
from dataclasses import replace
from unittest.mock import Mock
import unittest

from fruitfly_agent.core.data_model.runtime import ProviderView
from fruitfly_agent.core.errors import FatalError
from fruitfly_agent.providers.specs import ModelSpec, ProviderSpec
from fruitfly_agent.run.runtime.trial_budget import TrialInvocationBudget, BudgetedRegistry


class TrialBudgetTests(unittest.TestCase):
    def test_main_and_auxiliary_share_precall_limit_and_output_cap(self):
        main, auxiliary = Mock(), Mock()
        registry = Mock()
        registry.create.side_effect = [main, auxiliary]
        budget = TrialInvocationBudget(2, 128)
        bounded = BudgetedRegistry(registry, budget)
        spec = ModelSpec('main', ProviderSpec('fake', 'DUMMY'), 'model', 4096)
        first, second = bounded.create(spec), bounded.create(replace(spec, id='aux'))
        view = ProviderView('prompt', [], [], 'model', 2048)
        first(view)
        second(view)
        self.assertEqual(main.call_args.args[0].max_tokens, 128)
        self.assertEqual(auxiliary.call_args.args[0].max_tokens, 128)
        self.assertEqual(budget.used, 2)
        with self.assertRaises(FatalError):
            second(view)
        self.assertEqual(auxiliary.call_count, 1)
        self.assertTrue(budget.exhausted)

    def test_failed_provider_invocation_still_consumes_allocation(self):
        provider = Mock(side_effect=RuntimeError('transport failed'))
        registry = Mock()
        registry.create.return_value = provider
        budget = TrialInvocationBudget(1, 128)
        bounded = BudgetedRegistry(registry, budget)
        wrapped = bounded.create(ModelSpec('main', ProviderSpec('fake', 'DUMMY'), 'model', 4096))
        with self.assertRaises(RuntimeError):
            wrapped(ProviderView('prompt', [], [], 'model', 128))
        with self.assertRaises(FatalError):
            wrapped(ProviderView('prompt', [], [], 'model', 128))
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(budget.used, 1)

    def test_duplicate_provider_resource_keeps_same_wrapper(self):
        registry = Mock()
        registry.create.return_value = Mock()
        bounded = BudgetedRegistry(registry, TrialInvocationBudget(2, 128))
        spec = ModelSpec('main', ProviderSpec('fake', 'DUMMY'), 'model', 4096)
        self.assertIs(bounded.create(spec), bounded.create(spec))
