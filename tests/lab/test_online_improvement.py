"""Streaming evidence, independent assessment and scoped online control."""
import asyncio
from dataclasses import replace, asdict
import json
import unittest

from fruitfly_agent.lab.improvement.assessment.online import AssessedRunner
from fruitfly_agent.improvement.contracts.live import Assessment, ControlRequest, EvidencePosition, ExecutionEvent, Metric
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.lab.improvement.execution.file_runner import FileTaskRunner
from fruitfly_agent.lab.improvement.assessment.metrics import ProcessMetrics
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.lab.improvement.assessment.inspection import ReadOnlyInspector
from fruitfly_agent.lab.improvement.termination import MetricThreshold
from fruitfly_agent.lab.improvement.workflow.adaptive import StopExecutionPolicy
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.improvement.execution.control import ControlDispatcher
from fruitfly_agent.improvement.execution.events import EventJournal
from fruitfly_agent.improvement.execution.handles import ManagedExecution
from fruitfly_agent.improvement.workflow.budget import AllocationExhausted
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import fixture, version


class LiveExecutionTests(unittest.IsolatedAsyncioTestCase):
    def setup_task(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        plan = RunPlan('live-job', version(), ('prompt',))
        task = TaskMaterial('live-task', 'Create the requested output.')
        return registry, baseline, artifacts, plan, task, WorkflowServices(plan)

    async def test_file_tools_stream_and_final_assessments_preserve_actual_usage(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path': 'answer.txt', 'content': 'delivered'})
        provider.respond_text('done')
        runner = FileTaskRunner(AgentLoopConfig(provider=provider), registry, artifacts, services)
        assessed = AssessedRunner(runner, artifacts=artifacts, services=services,
            assessors=(ProcessMetrics,), interval=3)
        record = await assessed.execute(plan, task, baseline)
        self.assertEqual(record.status, 'completed')
        self.assertEqual(record.model_calls, 2)
        index = json.loads(artifacts.read(record.artifacts[-1].artifact_id))
        values = [json.loads(artifacts.read(ref)) for ref in index['assessments']]
        self.assertEqual(values[-1]['status'], 'final')
        metrics = {m['name']: m['value'] for m in values[-1]['metrics']}
        self.assertEqual({k: metrics[k] for k in ('model_calls', 'tool_calls', 'tool_errors')},
            {'model_calls': 2, 'tool_calls': 1, 'tool_errors': 0})
        self.assertEqual(metrics['input_tokens'], 20)
        self.assertEqual(metrics['output_tokens'], 10)
        self.assertGreaterEqual(metrics['elapsed_seconds'], 0)
        kinds = [json.loads(artifacts.read(ref))['kind'] for ref in index['events']]
        self.assertIn('model-request', kinds)
        self.assertIn('tool-finished', kinds)
        self.assertIn('artifact-written', kinds)
        intermediate = [json.loads(artifacts.read(ref)) for ref in index['events']
            if json.loads(artifacts.read(ref))['kind'] == 'artifact-written'][0]
        body = json.loads(intermediate['payload_json'])
        self.assertEqual(artifacts.read(body['artifact_id']), b'delivered')
        self.assertEqual(kinds[-1], 'finished')
        self.assertTrue(values[-1]['supersedes'])
        self.assertFalse(services.signal.is_set())
        await services.close()

    async def test_completion_only_backend_has_no_fabricated_tool_counts(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        class Runner:
            capabilities = frozenset()
            async def execute(self, plan, task, harness):
                return ExecutionRecord('opaque', task.task_id, task.material_id, harness.snapshot_id,
                    plan.parent.state, plan.conditions_id, 'completed', 'answer', model_calls=None)
        runner = AssessedRunner(Runner(), artifacts=artifacts, services=services, assessors=(ProcessMetrics,))
        result = await runner.execute(plan, task, baseline)
        index = json.loads(artifacts.read(result.artifacts[-1].artifact_id))
        final = json.loads(artifacts.read(index['assessments'][-1]))
        self.assertTrue(all(m['value'] is None for m in final['metrics'] if m['name'] != 'elapsed_seconds'))
        self.assertGreaterEqual(next(m['value'] for m in final['metrics'] if m['name'] == 'elapsed_seconds'), 0)
        self.assertEqual(len(index['events']), 2)
        await services.close()

    async def test_assessment_failure_is_recorded_without_inventing_task_failure(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        provider = FauxProvider(); provider.respond_text('answer')
        class Broken:
            assessor_id = 'broken'
            async def assess(self, event): raise RuntimeError('judge unavailable')
        runner = AssessedRunner(FileTaskRunner(AgentLoopConfig(provider=provider), registry, artifacts, services),
            artifacts=artifacts, services=services, assessors=(Broken,))
        result = await runner.execute(plan, task, baseline)
        self.assertEqual(result.status, 'completed')
        self.assertTrue(any(e == 'online-assessment' and f['status'] == 'failed' for e, f in services.events))
        await services.close()

    async def test_online_judge_cannot_swallow_root_budget_exhaustion(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        class Exhausted:
            assessor_id = 'exhausted'
            async def assess(self, event): raise AllocationExhausted('model allocation exhausted')
        provider = FauxProvider(); provider.respond_text('answer')
        runner = AssessedRunner(FileTaskRunner(AgentLoopConfig(provider=provider), registry, artifacts, services),
            artifacts=artifacts, services=services, assessors=(Exhausted,))
        with self.assertRaises(AllocationExhausted):
            await runner.execute(plan, task, baseline)
        await services.close()

    async def test_control_rejects_stale_unknown_and_changed_id_and_is_idempotent(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        journal = EventJournal('run', baseline.snapshot_id, artifacts)
        first = journal.publish('started')
        applied = []
        async def stop(request): applied.append(request.request_id)
        dispatcher = ControlDispatcher(lambda: journal.position, {'stop': stop})
        request = ControlRequest('one', 'stop', first.position)
        self.assertEqual((await dispatcher.apply(request)).status, 'applied')
        self.assertEqual((await dispatcher.apply(request)).status, 'applied')
        self.assertEqual(applied, ['one'])
        with self.assertRaises(ValueError):
            await dispatcher.apply(replace(request, action='fork'))
        journal.publish('model-request')
        self.assertEqual((await dispatcher.apply(replace(request, request_id='stale'))).status, 'rejected')
        self.assertEqual((await dispatcher.apply(ControlRequest('fork', 'fork', journal.position))).status, 'rejected')
        journal.close()
        self.assertEqual([e.position.sequence async for e in journal.events()], [1, 2])
        self.assertEqual([e.position.sequence async for e in journal.events()], [1, 2])
        await services.close()

    async def test_scoped_stop_cancels_probe_without_cancelling_root_job(self):
        registry, baseline, artifacts, plan, task, services = self.setup_task()
        entered, cleaned = asyncio.Event(), asyncio.Event()
        class Runner:
            capabilities = frozenset({'events', 'stop'})
            async def start(self, plan, task, harness):
                async def execute(journal):
                    entered.set()
                    try: await asyncio.Event().wait()
                    finally: cleaned.set()
                return ManagedExecution(execute, execution_id='probe', version_id=harness.snapshot_id,
                    artifacts=artifacts, record=services.record)
        class Ready:
            assessor_id = 'ready'
            async def assess(self, event):
                return Assessment(event.position, self.assessor_id, (Metric('ready', 1),),
                    status='final', scope='segment')
        policy = StopExecutionPolicy(MetricThreshold('ready', 'ready', 1, scope='segment'), max_event_lag=2)
        runner = AssessedRunner(Runner(), artifacts=artifacts, services=services, assessors=(Ready,), control_policy=policy)
        result = await asyncio.wait_for(runner.execute(plan, task, baseline), 1)
        self.assertEqual(result.status, 'cancelled')
        self.assertTrue(cleaned.is_set())
        self.assertFalse(services.signal.is_set())
        await services.close()

    async def test_inspector_never_exposes_write_tools(self):
        _, _, artifacts, plan, task, services = self.setup_task()
        provider = FauxProvider(); provider.respond_text('NO_CLEAR_CHOICE')
        inspector = ReadOnlyInspector(AgentLoopConfig(provider=provider), artifacts)
        class Workspace:
            def paths(self): return ()
            def read(self, path): return b''
        await inspector.session('compare', Workspace(), services)
        self.assertEqual(set(provider.calls[0]['tools']), {'list_files', 'read_file', 'search_file'})
        with self.assertRaises(ValueError):
            await inspector.session('edit', Workspace(), services, writable=True)
        await services.close()

    def test_events_are_immutable_and_partial_assessments_do_not_satisfy_final_goals(self):
        _, baseline, _, _, _, _ = self.setup_task()
        p = EvidencePosition('run', baseline.snapshot_id, 'initial', 1)
        event = ExecutionEvent(p, 'started', '{"nested":{"value":1}}')
        event.payload['nested']['value'] = 99
        self.assertEqual(event.payload['nested']['value'], 1)
        from fruitfly_agent.improvement.contracts.stopping import SearchState
        goal = MetricThreshold('judge', 'quality', 1)
        value = Assessment(p, 'judge', (Metric('quality', 1),), scope='execution')
        self.assertIsNone(goal.decide(SearchState(0, 1, 1, False, False, assessments=(value,))))
        final = replace(value, status='final')
        self.assertIsNotNone(goal.decide(SearchState(0, 1, 1, False, False, assessments=(final,))))

    async def test_uncertain_control_is_not_replayed(self):
        _, baseline, artifacts, _, _, services = self.setup_task()
        journal = EventJournal('run', baseline.snapshot_id, artifacts)
        event = journal.publish('started')
        attempts = []
        async def uncertain(request):
            attempts.append(request.request_id)
            raise RuntimeError('acknowledgment lost')
        dispatcher = ControlDispatcher(lambda: journal.position, {'checkpoint': uncertain})
        request = ControlRequest('checkpoint', 'checkpoint', event.position)
        with self.assertRaises(RuntimeError): await dispatcher.apply(request)
        self.assertEqual((await dispatcher.apply(request)).status, 'unknown')
        self.assertEqual(attempts, ['checkpoint'])
        await services.close()

    async def test_event_capacity_keeps_a_terminal_record(self):
        _, baseline, artifacts, _, _, services = self.setup_task()
        journal = EventJournal('run', baseline.snapshot_id, artifacts, maximum=2)
        journal.publish('started')
        with self.assertRaises(ValueError): journal.publish('model-request')
        journal.publish('failed', error='event allocation exhausted'); journal.close()
        self.assertEqual([e.kind async for e in journal.events()], ['started', 'failed'])
        await services.close()

    async def test_partial_assessor_construction_closes_products_without_starting_task(self):
        _, baseline, artifacts, plan, task, services = self.setup_task()
        closed = []
        class Resource:
            async def aclose(self): closed.append('assessor')
        class Runner:
            capabilities = frozenset()
            async def start(self, *args): self.fail('task must not start')
        def fail(): raise RuntimeError('construction failed')
        runner = AssessedRunner(Runner(), artifacts=artifacts, services=services, assessors=(Resource, fail))
        with self.assertRaisesRegex(RuntimeError, 'construction failed'):
            await runner.execute(plan, task, baseline)
        self.assertEqual(closed, ['assessor'])
        await services.close()
        self.assertEqual(closed, ['assessor'])

    async def test_missing_native_token_receipts_remain_unknown(self):
        _, baseline, artifacts, _, _, services = self.setup_task()
        journal = EventJournal('run', baseline.snapshot_id, artifacts)
        assessor = ProcessMetrics()
        for kind, fields in (('started', {'process_events': True}), ('model-request', {}),
                ('model-response', {'input_tokens': None, 'output_tokens': None, 'usage_reported': False}),
                ('finished', {'model_calls': 1})):
            value = await assessor.assess(journal.publish(kind, **fields))
        metrics = {m.name: m.value for m in value.metrics}
        self.assertEqual(metrics['model_calls'], 1)
        self.assertIsNone(metrics['input_tokens'])
        self.assertIsNone(metrics['output_tokens'])
        journal.close()
        await services.close()
