"""Services behavior and failure contracts."""
import asyncio
from dataclasses import FrozenInstanceError, replace
import unittest
from fruitfly_agent.improvement.contracts.lifecycle import ContextContribution
from fruitfly_agent.improvement.contracts.tasks import Resource
from fruitfly_agent.improvement.contracts.failures import StageFailure
from fruitfly_agent.improvement.extensions import HookRegistry
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.pipeline import build_pipeline


class KernelTests(unittest.IsolatedAsyncioTestCase):
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
            plan = replace(plan, timeouts={'editor_seconds':.01,'execution_seconds':.01,'evaluator_seconds':.01})
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

    async def test_long_sequence_bounds_events_without_quota_control(self):
        _,plan,_,_=build_pipeline()
        services=WorkflowServices(plan)
        for index in range(3000):
            services.observe('model')
            services.record('transition',index=index)
        self.assertEqual(len(services.events),256)
        self.assertEqual(services.used['model'],3000)
        self.assertFalse(hasattr(services,'budget'))
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
