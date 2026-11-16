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
    async def test_draft_check_reports_independent_component_errors_without_finishing(self):
        import json
        from fruitfly_agent.lab.improvement.components import ComponentRegistry, FileComponentAdapter
        from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
        flow, plan, baseline, _ = proposal_fixture()
        def validate(document):
            if document.files[0].text == 'INVALID':
                raise ValueError('Invalid component content')
        components = ComponentRegistry(FileComponentAdapter(document, validate,
            optimization=OptimizationSpec(document.role, 'documents')) for document in baseline.components)
        provider = FauxProvider()
        for name in ('prompt', 'memory'):
            provider.respond_tool_call('write_file', {'path': f'harness/{name}/instructions.txt', 'content': 'INVALID'})
        provider.respond_tool_call('check_candidate', {'reasons': []})
        def repair(view, signal=None):
            result = json.loads(view.messages[-1].text)
            self.assertFalse(result['valid'])
            self.assertEqual({'prompt', 'memory'}, {e['component_id'] for e in result['errors'] if 'component_id' in e})
            fake = FauxProvider()
            fake.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'prompt'})
            return fake(view, signal=signal)
        provider.script.append(repair)
        provider.respond_tool_call('write_file', {'path': 'harness/memory/instructions.txt', 'content': 'memory'})
        provider.respond_tool_call('submit_candidate', {'reasons': [], 'decision': {
            'kind': 'retain_baseline', 'explanation': 'No supported change.', 'baseline_applicability': 'Unchanged baseline.'}})
        async with StageServices(plan) as services:
            candidate = await AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), components).edit('propose',
                ProposalRequest(plan, TaskMaterial('task', 'Work'), baseline, (), 'invariant', 0), services)
        self.assertFalse(candidate.changed_ids)
        self.assertFalse(provider.script)

    async def test_runtime_failure_retains_unsubmitted_candidate_without_mutating_baseline(self):
        import json
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        artifacts = MemoryArtifacts()
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'Retained draft'})
        provider.respond_tool_call('read', {'path': 'harness/prompt/instructions.txt'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'Retained draft'})
        provider.respond_fatal('Interrupted after editing')
        editor = AgentEditor(AgentLoopConfig(provider), artifacts, flow.components)
        async with StageServices(plan) as services:
            with self.assertRaises(RuntimeError):
                await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
            reference = [fields['artifact_id'] for event, fields in services.events if event == 'editor-draft-retained'][-1]
        draft = json.loads(artifacts.read(reference))
        self.assertEqual(baseline.snapshot_id, draft['baseline_id'])
        component = next(c for c in draft['harness']['components'] if c['component_id'] == 'prompt')
        self.assertEqual('Retained draft', component['files'][0]['text'])
        self.assertEqual(baseline, flow.components.snapshot())
        from fruitfly_agent.improvement.contracts.tasks import Resource
        resumed = FauxProvider()
        resumed.respond_tool_call('restore_candidate', {'artifact_id': reference})
        resumed.respond_tool_call('read', {'path': 'context/executions.json'})
        resumed.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Continue the retained inspection draft.', 'evidence_ids': [record.run_id],
            'expected_effect': 'Inspection precedes completion.'}]})
        request = ProposalRequest(plan, task, baseline, (record,), 'invariant', 0,
            context=(Resource('draft.json', reference),))
        from fruitfly_agent.lab.improvement.editor.recovery import restore_draft
        from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace
        workspace = EvidenceWorkspace.build(request, artifacts)
        with self.assertRaisesRegex(ValueError, 'explicitly granted'):
            restore_draft(reference, workspace, replace(request, context=()), artifacts, flow.components)
        with self.assertRaisesRegex(ValueError, 'outside current grants'):
            restore_draft(reference, workspace, replace(request, plan=replace(plan, component_ids=('memory',))), artifacts, flow.components)
        self.assertEqual(baseline, workspace.collect())
        async with StageServices(plan) as services:
            candidate = await AgentEditor(AgentLoopConfig(resumed), artifacts, flow.components).edit('propose', request, services)
        self.assertEqual('Retained draft', candidate.harness.component('prompt').files[0].text)
        self.assertEqual(3, len(resumed.calls))
        self.assertFalse(resumed.script)

    def test_explicit_draft_hash_resolves_through_research_stage_context(self):
        import tempfile
        from pathlib import Path
        import yaml
        from fruitfly_agent.run.improvement.context import ResearchContext
        reference = 'sha256:' + 'a' * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'improvement.yaml'
            path.write_text(yaml.safe_dump({'research': {'id': 'restore'}, 'stages': {'propose': {
                'inputs': {'batches': [{'bundle': 'batch.json'}]}, 'context': [{'artifact': reference}]}},
                'next': {'stage': 'propose'}}))
            context = ResearchContext.resolve(path)
            self.assertEqual([reference], context.inputs['context'])

    async def test_target_discovery_exposes_real_readable_candidate_files(self):
        import json
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('list_targets', {})
        provider.respond_tool_call('describe_target', {'component_id': 'prompt'})
        provider.respond_tool_call('read', {'path': 'harness/prompt/instructions.txt'})
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'candidate'})
        provider.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'Observed missing procedure', 'evidence_ids': [record.run_id],
            'expected_effect': 'Inspection precedes completion.'}]})
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components)
        async with StageServices(plan) as services:
            candidate = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        messages = provider.calls[1]['messages']
        result = next(m for m in messages if getattr(m, 'role', '') == 'toolResult')
        target = json.loads(result.text)['targets'][0]
        self.assertEqual(['harness/prompt/instructions.txt'], target['candidate_files'])
        self.assertEqual(('prompt',), candidate.changed_ids)
        self.assertEqual(baseline, flow.components.snapshot())

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

    async def test_submission_tool_links_organization_findings_through_core_validation(self):
        import json
        from fruitfly_agent.improvement.contracts.tasks import Resource
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        artifacts = MemoryArtifacts()
        guide = Resource('organization/guide.json', artifacts.put(json.dumps({
            'findings': [{'issue_id': 'missing-inspection'}]}).encode()))
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {
            'path': 'harness/prompt/instructions.txt', 'content': 'Inspect the supplied material first.'})
        provider.respond_tool_call('submit_candidate', {'reasons': [{
            'component_id': 'prompt', 'explanation': 'An inspection step was omitted.',
            'evidence_ids': [record.run_id], 'issue_ids': ['missing-inspection'],
            'expected_effect': 'Inspection precedes the answer; another omission refutes the hypothesis.'}]})
        editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, flow.components)
        request = ProposalRequest(plan, task, baseline, (record,), 'invariant', 0, context=(guide,))
        async with StageServices(plan) as services:
            candidate = await editor.edit('propose', request, services)
        self.assertEqual(('prompt',), candidate.changed_ids)
        self.assertEqual(('missing-inspection',), candidate.reasons[0].issue_ids)
        self.assertEqual(3, len(provider.calls))
        self.assertFalse(provider.script)
        self.assertEqual(baseline, flow.components.snapshot())

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
        provider.respond_tool_call('submit_candidate', {'reasons': [], 'decision': {
            'kind': 'retain_baseline', 'explanation': 'The supplied record does not establish a useful change.',
            'baseline_applicability': 'No behavioral defect in the current component is established.'}})
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components, instructions=instructions)
        async with StageServices(plan) as services:
            result = await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
        self.assertEqual((), result.changed_ids)
        self.assertIn('CUSTOM REPAIR', provider.calls[-1]['system_prompt'])
        self.assertIn('CUSTOM TOOL', observed[0])
        self.assertNotIn('CUSTOM TOOL', owner.instructions.submit_candidate)

    async def test_no_change_requires_a_decision_and_generator_returns_no_new_candidate(self):
        from fruitfly_agent.lab.improvement.editor.generators import AgentGenerator
        from fruitfly_agent.improvement.stages.services import GeneratorServices
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('submit_candidate', {'reasons': []})
        provider.respond_tool_call('submit_candidate', {'reasons': [], 'decision': {
            'kind': 'needs_evidence', 'explanation': 'The observed omission has no known cause.',
            'baseline_applicability': 'Historical settings are unavailable.',
            'required_materials': ['context/history/configuration.json']}})
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components)
        request = ProposalRequest(plan, task, baseline, (record,), 'invariant', 0)
        async with StageServices(plan, edit=editor.edit) as services:
            result = await AgentGenerator().propose(request, GeneratorServices(services))
        self.assertEqual((), result.candidates)
        self.assertEqual('needs_evidence', result.decision.kind)
        self.assertFalse(result.stop)
        self.assertEqual(2, len(provider.calls))

    async def test_repeated_identical_tool_errors_fail_without_becoming_a_baseline_decision(self):
        flow, plan, baseline, _ = proposal_fixture()
        provider = FauxProvider()
        for index in range(4):
            provider.respond_tool_call('read', {'path': 'outside-grant'})
        provider.respond_text('Should never be requested')
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components,
            settings={'supply': {'repeated_error_limit': 3}})
        async with StageServices(plan) as services:
            with self.assertRaisesRegex(RuntimeError, 'required hook failed'):
                await editor.edit('propose', ProposalRequest(plan, TaskMaterial('task', 'Work'),
                    baseline, (), 'invariant', 0), services)
            self.assertIsNone(services.proposal_decision)
            self.assertTrue(any(event == 'tool-recovery-exhausted' and fields['feedback_opportunities'] == 3
                for event, fields in services.events))
        self.assertEqual(4, len(provider.calls))

    async def test_parallel_navigation_errors_allow_the_editor_to_read_feedback_and_recover(self):
        from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
        flow, plan, baseline, _ = proposal_fixture()
        provider = FauxProvider()
        provider.respond(AssistantMessage([ToolCallBlock('catalog-' + str(index), 'catalog',
            {'path': 'context/executions'}) for index in range(4)], 'toolUse'))
        provider.respond_tool_call('catalog', {'prefix': 'context/'})
        provider.respond_tool_call('submit_candidate', {'reasons': [], 'decision': {
            'kind': 'retain_baseline', 'explanation': 'Navigation alone supplies no support for a change.',
            'baseline_applicability': 'No executable defect was established.'}})
        editor = AgentEditor(AgentLoopConfig(provider), MemoryArtifacts(), flow.components,
            settings={'supply': {'repeated_error_limit': 3}})
        async with StageServices(plan) as services:
            result = await editor.edit('propose', ProposalRequest(plan, TaskMaterial('task', 'Work'),
                baseline, (), 'invariant', 0), services)
            self.assertEqual('retain_baseline', services.proposal_decision.kind)
            self.assertFalse(any(event == 'tool-recovery-exhausted' for event, _ in services.events))
        self.assertFalse(result.changed_ids)
        errors = [m for m in provider.calls[1]['messages'] if getattr(m, 'is_error', False)]
        self.assertEqual(4, len(errors))
        self.assertEqual(3, len(provider.calls))
