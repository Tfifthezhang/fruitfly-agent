"""Discovery is offline; bind only supported methods and clean failed resources."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.methods import MethodDefinition
from fruitfly_agent.lab.improvement.methods.opro import definition
from fruitfly_agent.lab.improvement.runtime.selection import MethodSelection
from fruitfly_agent.lab.improvement.runtime.host import HostedTextImprover


class MethodSelectionTests(unittest.TestCase):
    def setup_selection(self, bind):
        original = definition()
        candidate = replace(original, descriptor=replace(original.descriptor, mechanism_id='alternative'),
            improvement=replace(original.improvement, bind=bind))
        template = Mock(spec=HostedTextImprover)
        template.services_factory = SimpleNamespace(capabilities=frozenset({'evaluate', 'complete', 'history'}))
        template.target = BasePromptTarget('seed')
        template.parameters = original.descriptor.normalize_parameters({})
        return MethodSelection((original, candidate), 'opro', template, {'base_prompt': template.target})

    def test_discovery_checks_support_without_constructing_strategies(self):
        bind = Mock()
        methods = self.setup_selection(bind)
        self.assertTrue(all(m.available for m in methods.options('H', 'base_prompt')))
        self.assertFalse(any(m.available for m in methods.options('I', 'base_prompt')))
        self.assertFalse(any(m.available for m in methods.options('H', 'missing')))
        methods.default.services_factory.capabilities = frozenset()
        self.assertIn('Missing execution capabilities', methods.options('H', 'base_prompt')[0].reason)
        with self.assertRaisesRegex(ValueError, 'Missing execution capabilities'):
            methods.select(method_id='alternative', target_id='base_prompt')
        bind.assert_not_called()

    def test_failed_binder_closes_owned_resources_and_keeps_default(self):
        resource = SimpleNamespace(close=Mock())
        def broken(binding):
            binding.own(resource)
            raise RuntimeError('construction failed')
        methods = self.setup_selection(broken)
        default = methods.default
        with self.assertRaisesRegex(RuntimeError, 'construction failed'):
            methods.select(method_id='alternative', target_id='base_prompt')
        resource.close.assert_called_once()
        self.assertIs(methods.default, default)
        self.assertEqual(methods.bound, [])

    def test_invalid_support_declarations_reject(self):
        for roles, schemas in (({'unknown'}, {'text-v1'}), (set(), {'text-v1'}), ({'H'}, set())):
            with self.assertRaises(ValueError):
                MethodDefinition(roles, schemas, frozenset(), lambda binding: None)


    def test_runtime_closes_all_bound_resources_even_after_a_close_failure(self):
        methods = self.setup_selection(Mock())
        first = SimpleNamespace(close=Mock())
        second = SimpleNamespace(close=Mock(side_effect=RuntimeError('close failed')))
        methods.bound.extend((first, second))
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            methods.close()
        first.close.assert_called_once()
        second.close.assert_called_once()
        self.assertEqual(methods.bound, [])


    def test_declared_runtime_dependencies_cannot_be_bypassed_by_job_selection(self):
        methods = self.setup_selection(Mock())
        alternative = methods.definitions['alternative']
        methods.definitions['alternative'] = replace(alternative,
            requires_capabilities=frozenset({'missing-executor'}))
        option = next(m for m in methods.options('H', 'base_prompt') if m.method_id == 'alternative')
        self.assertFalse(option.available)
        self.assertIn('missing-executor', option.reason)
        with self.assertRaisesRegex(ValueError, 'missing-executor'):
            methods.select(method_id='alternative', target_id='base_prompt')
