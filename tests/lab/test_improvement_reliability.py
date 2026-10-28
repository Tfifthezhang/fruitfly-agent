"""Stage fault injection preserves completed evidence without granting success."""
import asyncio
from dataclasses import replace
import json
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.contracts.failures import IntegrityError, PersistenceError, CleanupError
from fruitfly_agent.lab.improvement.evidence.query import search_text
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts
from fruitfly_agent.lab.improvement.api import WorkflowServices, TaskMaterial, ProposalRequest, AgentEditor
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.pipeline import build_pipeline, fixture, version
from tests.support.faux_provider import FauxProvider


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_failure_preserves_reference_and_checkpoint(self):
        flow, plan, baseline, runner = build_pipeline()
        flow.generators.factories['rule-generator'] = lambda: type('Broken', (), {
            'generator_id': 'rule-generator', 'required_capabilities': frozenset(), 'propose': AsyncMock(side_effect=RuntimeError('broken'))})()
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
        self.assertEqual(result.stop_reason, 'stage_failed.propose')
        self.assertEqual(result.harness, baseline)
        self.assertIsNotNone(result.selected)
        checkpoints = [fields['outcome'] for event, fields in services.events if event == 'workflow-checkpoint']
        self.assertEqual(checkpoints[-1]['selected']['run_id'], result.selected.run_id)
        await services.close()

    async def test_candidate_timeouts_keep_baseline_and_do_not_invent_measurements(self):
        flow, plan, baseline, runner = build_pipeline()
        original = runner.execute
        async def execute(plan, task, harness):
            if harness != baseline:
                await asyncio.Event().wait()
            return await original(plan, task, harness)
        runner.execute = execute
        plan = replace(plan, operation_timeout=.01)
        services = WorkflowServices(plan)
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, services)
        self.assertEqual(result.harness, baseline)
        self.assertTrue(any(r.status == 'error' for r in result.records))
        self.assertTrue(all(r.model_calls is None for r in result.records if r.status == 'error'))
        self.assertEqual(result.decision.assurance, 'selected')
        await services.close()

    async def test_missing_scores_cannot_promote_a_candidate(self):
        flow, plan, baseline, _ = build_pipeline()
        flow.measurements = type('BrokenScores', (), {'measure': AsyncMock(side_effect=OSError('unavailable'))})()
        plan = replace(plan, feedback='scored')
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        self.assertEqual(result.harness, baseline)
        self.assertIsNotNone(result.selected)
        self.assertNotEqual(result.decision.assurance, 'verified')

    async def test_diagnosable_failed_reference_can_generate_without_fabricating_baseline_score(self):
        flow, plan, baseline, runner = build_pipeline()
        artifacts = flow.artifacts = MemoryArtifacts()
        original = runner.execute
        async def execute(plan, task, harness):
            record = await original(plan, task, harness)
            if harness == baseline:
                record = replace(record, status='error', output='Partial work; tool allowance exhausted')
                record = attach_facts(record, receipt_facts(record, artifacts, diagnosable=True,
                    termination_reason='tool_limit'), artifacts)
            return record
        runner.execute = execute
        result = await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        self.assertTrue(result.candidates)
        self.assertEqual(result.selected.status, 'completed')
        self.assertTrue(all(r.status == 'error' for r in result.records if r.harness_id == baseline.snapshot_id))

    async def test_receipt_mismatch_and_persistence_failure_are_fatal(self):
        flow, plan, baseline, runner = build_pipeline()
        original = runner.execute
        async def wrong(*args):
            return replace(await original(*args), task_id='other-task')
        runner.execute = wrong
        with self.assertRaises(IntegrityError):
            await flow.run(plan, TaskMaterial('task', 'Work'), baseline, WorkflowServices(plan))
        async def work():
            return 1
        def failed_sink(event, **fields):
            raise OSError('disk full')
        services = WorkflowServices(plan, record=failed_sink)
        with self.assertRaises(PersistenceError):
            services.record('checkpoint')
        await services.close()

    async def test_cleanup_attempts_all_resources_and_closes_budget(self):
        _, plan, _, _ = build_pipeline()
        closed = []
        class Resource:
            def __init__(self, name): self.name = name
            async def aclose(self):
                closed.append(self.name)
                if self.name == 'bad': raise OSError('failed close')
        services = WorkflowServices(plan)
        services.own(Resource('good')); services.own(Resource('bad'))
        with self.assertRaises(CleanupError): await services.close()
        self.assertEqual(closed, ['bad', 'good'])
        self.assertTrue(services.budget.closed)

    async def test_submission_tool_finishes_without_an_extra_model_request(self):
        flow, plan, baseline, runner = build_pipeline()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('read_file', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'candidate'})
        provider.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Observed missing procedure', 'evidence_ids': [record.run_id]}]})
        editor = AgentEditor(AgentLoopConfig(provider=provider), MemoryArtifacts(), flow.components, max_tool_calls=2)
        services = WorkflowServices(plan)
        candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual(candidate.changed_ids, ('prompt',))
        self.assertEqual(len(provider.calls), 3)
        self.assertFalse(provider.script)

    async def test_format_repair_keeps_draft_and_removes_large_evidence(self):
        flow, plan, baseline, runner = build_pipeline()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('read_file', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'candidate'})
        provider.respond_text('prose before JSON {"reasons":[]}')
        provider.respond_tool_call('list_files', {})
        provider.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Observed missing procedure', 'evidence_ids': [record.run_id]}]})
        editor = AgentEditor(AgentLoopConfig(provider=provider), MemoryArtifacts(), flow.components)
        services = WorkflowServices(plan)
        candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual(candidate.harness.component('prompt').files[0].text, 'candidate')
        messages = provider.calls[-1]['messages']
        listing = next(message for message in messages if getattr(message, 'role', '') == 'toolResult' and 'context/repair.json' in str(message))
        self.assertIn('context/repair.json', str(listing))
        self.assertNotIn('context/executions/', str(listing))
        self.assertEqual(sum(event == 'editor-invalid' for event, _ in services.events), 1)

    def test_search_has_source_offsets_and_bounded_excerpts(self):
        query = 'q' * 500
        text = ('x' * 200 + query) * 100
        result = search_text(text, query, limit=50)
        self.assertEqual(result['matches'][0]['offset'], 200)
        self.assertLessEqual(sum(len(m['text']) for m in result['matches']), 12000)
        second = search_text(text, query, offset=result['next_offset'])
        self.assertGreater(second['matches'][0]['offset'], result['matches'][-1]['offset'])

    async def test_interrupted_native_execution_keeps_written_files_and_partial_facts(self):
        from fruitfly_agent.lab.improvement.execution.file_runner import FileTaskRunner
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        from fruitfly_agent.improvement.workflow.operations import run_stage
        from fruitfly_agent.improvement.contracts.failures import StageFailure
        from fruitfly_agent.improvement.execution.facts import read_facts
        flow, plan, baseline, _ = build_pipeline()
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path': 'partial.txt', 'content': 'work survived'})
        def blocking(view, *, signal=None):
            async def events():
                await asyncio.Event().wait()
                yield StreamDone(None)
            return AssistantMessageEventStream(events())
        provider.script.append(blocking)
        artifacts = MemoryArtifacts()
        plan = replace(plan, operation_timeout=.02)
        services = WorkflowServices(plan)
        runner = FileTaskRunner(AgentLoopConfig(provider=provider), flow.components, artifacts, services)
        with self.assertRaises(StageFailure) as caught:
            await run_stage(services, 'execute', runner.execute(plan, TaskMaterial('task', 'Work'), baseline))
        record = caught.exception.record
        self.assertIsNotNone(record)
        self.assertEqual(record.status, 'cancelled')
        self.assertEqual(record.model_calls, 2)
        self.assertEqual(artifacts.read(next(r.artifact_id for r in record.artifacts
            if r.path == 'deliverables/partial.txt')), b'work survived')
        facts = read_facts(record, artifacts)
        self.assertTrue(facts.diagnosable)
        self.assertFalse(facts.complete)
        await services.close()
