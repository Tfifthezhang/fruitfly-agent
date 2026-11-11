"""Editor execution behavior and failure contracts."""
import asyncio
from dataclasses import replace
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.lab.improvement.evidence.query import search_text
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.editing import ProposalRequest
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.stages import proposal_fixture
from tests.support.faux_provider import FauxProvider


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_submission_tool_finishes_without_an_extra_model_request(self):
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'candidate'})
        provider.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Observed missing procedure', 'evidence_ids': [record.run_id], 'expected_effect':'The proposed behavior appears in the subsequent execution.'}]})
        editor = AgentEditor(AgentLoopConfig(provider=provider), MemoryArtifacts(), flow.components)
        services = StageServices(plan)
        candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual(candidate.changed_ids, ('prompt',))
        self.assertEqual(len(provider.calls), 3)
        self.assertFalse(provider.script)

    async def test_format_repair_keeps_draft_and_source_access_without_replaying_evidence(self):
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'candidate'})
        provider.respond_text('prose before JSON {"reasons":[]}')
        provider.respond_tool_call('catalog', {})
        provider.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Observed missing procedure', 'evidence_ids': [record.run_id], 'expected_effect':'The proposed behavior appears in the subsequent execution.'}]})
        editor = AgentEditor(AgentLoopConfig(provider=provider), MemoryArtifacts(), flow.components)
        services = StageServices(plan)
        candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual(candidate.harness.component('prompt').files[0].text, 'candidate')
        messages = provider.calls[-1]['messages']
        listing = next(message for message in messages if getattr(message, 'role', '') == 'toolResult' and 'context/repair.json' in str(message))
        self.assertIn('context/repair.json', str(listing))
        self.assertIn('context/executions/', str(listing))
        self.assertEqual(sum(event == 'evidence-page' and fields.get('path') == 'context/executions.json'
            for event, fields in services.events), 1)
        self.assertNotIn(record.output, str(messages))
        self.assertEqual(sum(event == 'editor-invalid' for event, _ in services.events), 1)

    def test_search_has_source_offsets_and_bounded_excerpts(self):
        query = 'q' * 500
        text = ('x' * 200 + query) * 100
        result = search_text(text, query, limit=50)
        self.assertEqual(result['matches'][0]['offset'], 200)
        self.assertLessEqual(sum(len(m['text']) for m in result['matches']), 12000)
        second = search_text(text, query, offset=result['next_offset'])
        self.assertGreater(second['matches'][0]['offset'], result['matches'][-1]['offset'])

    async def test_interrupted_registered_execution_keeps_written_files_and_partial_facts(self):
        from tests.support.task_execution import TaskRunnerFixture
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        from fruitfly_agent.improvement.stages.operations import run_stage
        from fruitfly_agent.improvement.contracts.failures import StageFailure
        from fruitfly_agent.improvement.execution.facts import read_facts
        flow, plan, baseline, _ = proposal_fixture()
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path': 'partial.txt', 'content': 'work survived'})
        def blocking(view, *, signal=None):
            async def events():
                await asyncio.Event().wait()
                yield StreamDone(None)
            return AssistantMessageEventStream(events())
        provider.script.append(blocking)
        artifacts = MemoryArtifacts()
        plan = replace(plan, timeouts={'editor_seconds':.02,'execution_seconds':.02,'evaluator_seconds':.02})
        services = StageServices(plan)
        runner = TaskRunnerFixture(AgentLoopConfig(provider=provider), flow.components, artifacts, services)
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

    async def test_configured_repair_and_tool_guidance_reach_candidate_execution(self):
        import json
        from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructionTarget
        owner = EditorInstructionTarget()
        source = json.loads(owner.snapshot().text)
        source['instructions']['repair'] = 'CUSTOM REPAIR: finish the existing draft using retained evidence.'
        source['instructions']['submit_candidate'] = 'CUSTOM TOOL: submit a supported hypothesis.'
        owner.validate_change(json.dumps(source), {'editable_fields': [
            'parameters.instructions.repair', 'parameters.instructions.submit_candidate']})
        instructions = owner.parse_document(json.dumps(source))
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        observed = []
        from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        def read(view, signal=None):
            observed.extend(t.description for t in view.tools if t.name == 'submit_candidate')
            async def events():
                yield StreamDone(AssistantMessage([ToolCallBlock('read', 'read', {'path': 'context/executions.json'})], 'toolUse'))
            return AssistantMessageEventStream(events())
        provider.script.append(read)
        provider.respond_text('invalid submission')
        provider.respond_tool_call('submit_candidate', {'reasons': []})
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components, instructions=instructions)
        async with StageServices(plan) as services:
            result = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual((), result.changed_ids)
        self.assertIn('CUSTOM REPAIR', provider.calls[-1]['system_prompt'])
        self.assertIn('CUSTOM TOOL', observed[0])
        self.assertNotIn('CUSTOM TOOL', owner.instructions.submit_candidate)
