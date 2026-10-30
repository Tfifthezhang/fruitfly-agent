"""Optimization classifications constrain execution, not only discovery."""
import asyncio
from dataclasses import replace
import unittest

from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from fruitfly_agent.improvement.workflow.budget import BudgetScope, AllocationExhausted
from fruitfly_agent.lab.improvement.components.files import FileComponentAdapter
from fruitfly_agent.lab.improvement.components.text import TextComponentAdapter
from fruitfly_agent.improvement.components.registry import ComponentRegistry
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from tests.support.pipeline import fixture, build_pipeline
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.workflow.services import WorkflowServices


class OptimizationProtocolTests(unittest.IsolatedAsyncioTestCase):
    def test_text_owner_must_declare_semantics_instead_of_inheriting_kind_defaults(self):
        owner = BasePromptTarget('baseline')
        owner.optimization = None
        with self.assertRaisesRegex(ValueError, 'explicitly declare'):
            TextComponentAdapter(owner, 'mechanism-parameters')
        owner.optimization = OptimizationSpec('H', 'text')
        adapter = TextComponentAdapter(owner, 'mechanism-parameters')
        self.assertIs(adapter.optimization, owner.optimization)
        self.assertEqual(adapter.optimization.representation, 'text')
        owner.optimization = OptimizationSpec('S', 'text', state='retained')
        with self.assertRaisesRegex(ValueError, 'owner-matching'):
            ComponentRegistry((adapter,))

    def test_file_owner_cannot_register_a_missing_or_mismatched_declaration(self):
        _, baseline = fixture()
        document = baseline.component('prompt')
        for spec in (None, OptimizationSpec('S', 'documents', state='retained')):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, 'matching explicit'):
                FileComponentAdapter(document, lambda document: None, optimization=spec)

    def test_algorithm_without_optimization_and_empty_target_declarations_are_rejected(self):
        from fruitfly_agent.lab.catalog import builtin_catalog, resolve_harness, MechanismSelection
        from fruitfly_agent.runtime_spec import HarnessProfile
        catalog = builtin_catalog()
        original = catalog.get('local-env')
        definition = replace(original, descriptor=replace(original.descriptor, mechanism_id='uneditable'),
            optimization_exemption='')
        with self.assertRaisesRegex(ValueError, 'optimization declaration'):
            catalog.extended((definition,)).require_optimization()
        empty = replace(definition, component_specs=lambda parameters, enabled: ())
        with self.assertRaisesRegex(ValueError, 'no optimization component'):
            resolve_harness(HarnessProfile('test', mechanisms=(MechanismSelection('uneditable'),)),
                catalog.extended((empty,)))

    def test_representation_timing_and_state_are_independent(self):
        spec = OptimizationSpec('S', 'documents', frozenset({'add', 'remove'}),
            update='between-tasks', state='retained', required_capabilities=frozenset({'snapshot'}))
        for capabilities, updates in ((set(), {'between-tasks'}), ({'snapshot'}, {'offline'})):
            with self.assertRaises(ValueError):
                spec.admit(role='S', capabilities=capabilities, boundaries={'task'}, updates=updates)
        spec.admit(role='S', capabilities={'snapshot'}, boundaries={'task'}, updates={'between-tasks'})

    async def test_unsupported_online_surface_rejects_before_any_trial(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.components.adapters['prompt'] = FileComponentAdapter(baseline.component('prompt'), lambda doc: None,
            optimization=OptimizationSpec('H', 'text', update='within-task', boundary='turn'))
        async with WorkflowServices(plan) as services:
            with self.assertRaisesRegex(ValueError, 'optimization surface'):
                await flow.run(plan, TaskMaterial('task', 'Do the task'), baseline, services)
        self.assertEqual(runner.calls, [])

    def test_nested_zero_work_cannot_allocate_unbounded_depth_or_change_root_limits(self):
        root = BudgetScope({'model': 2, 'execution': 2}, max_depth=2)
        child = root.child({'model': 1, 'execution': 1})
        grandchild = child.child({'model': 0, 'execution': 0})
        with self.assertRaisesRegex(AllocationExhausted, 'depth'):
            grandchild.child({'model': 0, 'execution': 0})
        root.close()
        self.assertEqual(root.held, {'model': 0, 'execution': 0})

    def test_restart_cannot_raise_the_recorded_recursion_allowance(self):
        root = BudgetScope({'model': 2, 'execution': 2}, max_depth=2)
        saved = root.snapshot()
        changed = BudgetScope({'model': 2, 'execution': 2}, max_depth=3)
        with self.assertRaisesRegex(ValueError, 'persisted root allocation'):
            changed.restore(saved)
