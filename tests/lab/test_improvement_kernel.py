"""Outer-loop faults, extension isolation and bounded long-run accounting."""
import asyncio
from dataclasses import FrozenInstanceError, replace
import json
from types import SimpleNamespace
import unittest

from fruitfly_agent.improvement.contracts.lifecycle import ContextContribution
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.failures import StageFailure
from fruitfly_agent.improvement.extensions import HookRegistry
from fruitfly_agent.improvement.workflow.budget import BudgetScope
from fruitfly_agent.lab.improvement.api import (WorkflowServices, TaskMaterial, ExecutionContext,
    ProposalRequest, AgentEditor)
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess, EvidenceUnavailable
from fruitfly_agent.lab.improvement.research import ResearchLedger
from fruitfly_agent.lab.improvement.system_configuration import search_parameters
from fruitfly_agent.lab.improvement.workflow.mechanisms import install_workflow_mechanisms
from fruitfly_agent.lab.improvement.components.configuration import ImprovementSettingsTarget
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.pipeline import build_pipeline, RuleGenerator
from tests.support.faux_provider import FauxProvider


class KernelTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_faults_bad_results_and_stop_fault_preserve_prior_executions(self):
        for target in ('propose', 'execute', 'select', 'stop', 'explore', 'assess'):
            with self.subTest(stage=target):
                flow, plan, baseline, runner = build_pipeline()
                plan = replace(plan, mode='sequential', depth=2)
                def broken(*args, **kwargs):
                    raise RuntimeError('synchronous plugin failure')
                if target == 'propose':
                    generator = RuleGenerator(); generator.propose = broken
                    flow.generators.factories['rule-generator'] = lambda: generator
                elif target == 'execute':
                    original = runner.execute
                    def execute(plan, task, harness):
                        return original(plan, task, harness) if harness == baseline else object()
                    runner.execute = execute
                elif target == 'select':
                    flow.selector.select = lambda *a: object()
                elif target == 'stop':
                    flow.stop_policy = SimpleNamespace(decide=broken)
                elif target == 'explore':
                    flow.exploration = SimpleNamespace(choose=lambda *a: object())
                else:
                    flow.completed_assessment = SimpleNamespace(assess=broken, ensure_available=lambda: None)
                services = WorkflowServices(plan)
                try:
                    outcome = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
                    self.assertTrue(outcome.records)
                    self.assertIsNotNone(outcome.selected)
                    self.assertNotEqual(outcome.decision.assurance, 'verified')
                    self.assertTrue(any(e == 'stage-failed' for e, _ in services.events))
                finally:
                    await services.close()

    async def test_hook_order_immutability_and_invalid_results_are_isolated(self):
        _, plan, _, _ = build_pipeline()
        hooks, order = HookRegistry(), []
        artifacts = MemoryArtifacts()
        resource = Resource('context.json', artifacts.put(b'{}'), 'application/json', 'input')
        def active(event):
            order.append('active')
            with self.assertRaises(FrozenInstanceError):
                event.phase = 'tampered'
            return ContextContribution((resource,))
        hooks.register('before_proposal', lambda e: order.append('observer'), priority=0)
        hooks.register('before_proposal', active, active=True)
        hooks.register('before_proposal', lambda e: ContextContribution((resource,)), active=True)
        hooks.register('before_proposal', lambda e: 'bad control result')
        services = WorkflowServices(plan, hooks=hooks)
        try:
            result = await services.emit('before_proposal')
            self.assertEqual(result.resources, (resource,))
            self.assertEqual(order, ['active', 'observer'])
            self.assertEqual(sum(e == 'hook-failed' for e, _ in services.events), 2)
        finally:
            await services.close()

    async def test_required_hook_stops_job_and_optional_timeout_does_not(self):
        for required in (False, True):
            flow, plan, baseline, _ = build_pipeline()
            plan = replace(plan, operation_timeout=.01)
            services = WorkflowServices(plan)
            async def hanging(event):
                await asyncio.Event().wait()
            services.hooks.register('before_proposal', hanging, required=required)
            try:
                result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
                self.assertEqual(result.stop_reason, 'stage_failed.hook' if required else 'completed')
                self.assertIsNotNone(result.selected)
            finally:
                await services.close()

    async def test_cancellation_is_not_swallowed_by_optional_hook(self):
        _, plan, _, _ = build_pipeline()
        services = WorkflowServices(plan)
        entered = asyncio.Event()
        async def hanging(event):
            entered.set(); await asyncio.Event().wait()
        services.hooks.register('before_proposal', hanging)
        pending = asyncio.create_task(services.emit('before_proposal'))
        await entered.wait()
        services.signal.set()
        try:
            with self.assertRaises(asyncio.CancelledError):
                await pending
        finally:
            await services.close()

    async def test_verification_refusal_still_emits_end_without_assurance(self):
        flow, plan, baseline, _ = build_pipeline()
        plan = replace(plan, purpose='persistent')
        async def refuse(outcome): return None
        flow.verifier = SimpleNamespace(verify=refuse)
        services, seen = WorkflowServices(plan), []
        services.hooks.register('before_run_end', lambda e: seen.append(json.loads(e.snapshot_json)))
        try:
            outcome = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            self.assertEqual(outcome.stop_reason, 'verification_failed')
            self.assertIsNone(outcome.decision)
            self.assertEqual(seen[-1]['stop_reason'], 'verification_failed')
        finally:
            await services.close()

    async def test_research_context_reaches_generator_and_is_task_local(self):
        flow, plan, baseline, _ = build_pipeline()
        flow.artifacts = artifacts = MemoryArtifacts()
        generator = RuleGenerator()
        flow.generators.factories['rule-generator'] = lambda: generator
        services = WorkflowServices(plan)
        saved = []
        context = ExecutionContext('.', artifacts, flow.components, None, None, None,
            plan=plan, services=services, system_settings={'search': {'research': {'enabled': True}}},
            save_record=lambda path, value: saved.append((path, value)))
        flow.stop_policy = install_workflow_mechanisms(context)
        try:
            await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            request = generator.requests[0]
            self.assertEqual(request.context[0].path, 'research.json')
            value = json.loads(artifacts.read(request.context[0].artifact_id))
            self.assertTrue(value['entries'])
            self.assertEqual(value['entries'][0]['kind'], 'observation')
            workspace = EvidenceWorkspace.build(request, artifacts)
            self.assertEqual(json.loads(workspace.read('context/extensions/research.json')), value)
            self.assertTrue(saved)
            other = ResearchLedger(replace(context, services=WorkflowServices(plan)))
            self.assertEqual(list(other.entries), [])
            await other.context.services.close()
        finally:
            await services.close()

    async def test_finalization_reserve_returns_quota_without_increasing_limits(self):
        flow, plan, baseline, runner = build_pipeline()
        plan = replace(plan, max_executions=5)
        services = WorkflowServices(plan)
        context = ExecutionContext('.', MemoryArtifacts(), flow.components, None, None, None,
            plan=plan, services=services, system_settings={'search': {'finalization': {'reserve_executions': 2}}})
        flow.stop_policy = install_workflow_mechanisms(context)
        try:
            result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
            self.assertIsNotNone(result.selected)
            self.assertEqual(services.used['execution'], 3)
            self.assertEqual(services.budget.available('execution'), 2)
            self.assertEqual(services.budget.limits['execution'], 5)
        finally:
            await services.close()

    async def test_long_sequence_bounds_closed_children_events_and_unknown_usage(self):
        _, plan, _, _ = build_pipeline()
        services = WorkflowServices(plan)
        for index in range(3000):
            child = services.budget.child({'model': 0, 'execution': 0})
            child.close()
            services.record('external-budget-settled', observed_calls=None, charged_allowance=1)
            services.record('transition', index=index)
        self.assertEqual(services.budget.children, [])
        self.assertEqual(len(services.events), 256)
        self.assertEqual(services.uncertain_model_allowance, 3000)
        self.assertEqual(services.used['model'], 0)
        await services.close()

    async def test_long_sequence_of_stage_transitions_isolates_deterministic_faults(self):
        from fruitfly_agent.improvement.workflow.operations import run_stage, require_type
        _, plan, _, _ = build_pipeline()
        services = WorkflowServices(plan)
        failures = 0
        try:
            for index in range(1000):
                def operation():
                    if index % 11 == 0:
                        raise OSError('deterministic injected fault')
                    return index if index % 13 else None
                try:
                    value = await run_stage(services, 'probe', operation,
                        validator=lambda result: require_type(result, int))
                    self.assertEqual(value, index)
                except StageFailure:
                    failures += 1
            self.assertEqual(failures, len([i for i in range(1000) if i % 11 == 0 or i % 13 == 0]))
            self.assertEqual(services.used, {'model': 0, 'execution': 0})
            self.assertLessEqual(len(services.events), 256)
            self.assertEqual(services.resources, [])
        finally:
            await services.close()

    async def test_missing_evidence_cannot_justify_changed_candidate_or_forge_supply(self):
        flow, plan, baseline, runner = build_pipeline()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        artifacts, provider = MemoryArtifacts(), FauxProvider()
        for _ in range(2):
            provider.respond_tool_call('read_file', {'path': 'context/executions/' + record.run_id + '/missing.log'})
            provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'unsupported edit'})
            provider.respond_text(json.dumps({'reasons': [{'component_id': 'prompt', 'explanation': 'Unseen evidence', 'evidence_ids': [record.run_id]}]}))
        services = WorkflowServices(plan)
        try:
            editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, flow.components)
            candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
            self.assertEqual(candidate.harness, baseline)
            self.assertTrue(any(e == 'editor-evidence-unavailable' for e, _ in services.events))
            access = EvidenceAccess((record.run_id,))
            access.provided('harness/prompt/fake.json', '{"run_id":"' + record.run_id + '"}')
            self.assertEqual(access.supplied, set())
        finally:
            await services.close()

    def test_new_policy_fields_are_strict_editable_and_identity_bound(self):
        target = ImprovementSettingsTarget('search', {})
        original = target.snapshot()
        value = json.loads(original.text)
        value['research']['enabled'] = True
        value['progress']['patience'] = 2
        value['finalization']['reserve_model_calls'] = 4
        target.validate_change(json.dumps(value), {'editable_fields': ['research.enabled', 'progress.patience', 'finalization.reserve_model_calls']})
        self.assertNotEqual(ImprovementSettingsTarget('search', value).snapshot().text, original.text)
        value['progress']['unknown'] = 1
        with self.assertRaises(ValueError): search_parameters(value)
