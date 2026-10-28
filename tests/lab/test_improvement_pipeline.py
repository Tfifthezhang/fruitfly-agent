"""Public pipeline ports support unscored work and feedback-driven algorithms."""
import asyncio
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.lab.improvement.api import (RunPlan, TaskMaterial, ComponentDocument, ComponentFile,
    HarnessSnapshot, CandidateBundle, EditReason, ExecutionRecord, Measurement, SelectionDecision,
    ProposalResult, ComponentRegistry, FileComponentAdapter, GeneratorRegistry, WorkflowServices, ComponentWorkflow,
    AgentEditor, AgentSelector, AgentReflector, WorkspaceTaskSource)
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.faux_provider import FauxProvider


from tests.support.pipeline import version, fixture, RuleGenerator, build_pipeline


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def build(self, **kwargs):
        return build_pipeline(**kwargs)

    async def test_non_model_generator_runs_unscored_joint_h_s_flow(self):
        flow, plan, baseline, runner = self.build()
        task = TaskMaterial('task', 'Complete the supplied work without an answer key')
        services = WorkflowServices(plan)
        outcome = await flow.run(plan, task, baseline, services)
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual(outcome.decision.assurance, 'selected')
        self.assertTrue(all('improved' in c.files[0].text for c in outcome.harness.components))
        self.assertEqual(services.used, {'execution': 4, 'model': 0})
        self.assertEqual(outcome.plan.parent, version())
        self.assertEqual([c.files[0].text for c in baseline.components], ['memory', 'prompt'])

    async def test_parallel_width_and_sequential_depth_have_explicit_evidence(self):
        for mode in ('parallel', 'sequential'):
            with self.subTest(mode=mode):
                flow, plan, baseline, runner = self.build()
                plan = replace(plan, mode=mode, width=2 if mode == 'parallel' else 1,
                               depth=2 if mode == 'sequential' else 1)
                outcome = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
                self.assertEqual(len(runner.calls), 8 if mode == 'parallel' else 7)
                self.assertEqual(len(outcome.candidates), 6)
                if mode == 'sequential':
                    self.assertTrue(all(c.files[0].text.endswith('improved improved') for c in outcome.harness.components))

    async def test_feedback_generator_receives_measurements_only_when_declared(self):
        source = type('Scores', (), {'measure': AsyncMock(side_effect=lambda task, record:
            Measurement(record.run_id, 'private-policy', 0.5, 'Measured feedback'))})()
        flow, plan, baseline, runner = self.build(measurements=source)
        generated = RuleGenerator()
        generated.required_capabilities = frozenset({'measurements'})
        flow.generators = GeneratorRegistry()
        flow.generators.register('rule-generator', lambda: generated, required_capabilities=generated.required_capabilities)
        with self.assertRaisesRegex(ValueError, 'capabilities'):
            await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(runner.calls, [])
        plan = replace(plan, feedback='scored')
        await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(generated.requests[0].feedback[0].score, 0.5)

    async def test_persistent_publication_requires_verification_and_exact_selection(self):
        flow, plan, baseline, runner = self.build()
        plan = replace(plan, purpose='persistent')
        with self.assertRaisesRegex(ValueError, 'verification'):
            await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(runner.calls, [])
        flow.verifier = type('Verifier', (), {'verify': AsyncMock(return_value=None)})()
        outcome = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(outcome.stop_reason, 'verification_failed')
        self.assertIsNone(outcome.decision)

    async def test_wrong_receipt_scope_and_budget_are_not_invented_success(self):
        flow, plan, baseline, runner = self.build()
        task = TaskMaterial('task', 'Do work')
        original = runner.execute
        async def wrong(*args):
            return replace(await original(*args), conditions_id=content_hash('wrong'))
        runner.execute = wrong
        with self.assertRaisesRegex(ValueError, 'receipt'):
            await flow.run(plan, task, baseline, WorkflowServices(plan))
        runner.execute = original
        plan = replace(plan, max_executions=1)
        outcome = await flow.run(plan, task, baseline, WorkflowServices(plan))
        self.assertEqual(outcome.stop_reason, 'budget_exhausted')
        self.assertEqual(outcome.harness, baseline)
        self.assertEqual(outcome.decision.assurance, 'selected')
        self.assertIsNotNone(outcome.selected)
        plan = replace(plan, component_ids=('prompt',), max_executions=8)
        guarded = WorkflowServices(plan)
        rejected = await flow.run(plan, task, baseline, guarded)
        self.assertTrue(all(set(c.changed_ids) <= {'prompt'} for c in rejected.candidates))
        self.assertTrue(all(r.harness_id in {baseline.snapshot_id, *(c.harness.snapshot_id for c in rejected.candidates)} for r in rejected.records))
        self.assertTrue(any(event == 'stage-failed' and fields['stage'] == 'propose' for event, fields in guarded.events))


    async def test_cancellation_closes_running_operation(self):
        flow, plan, baseline, runner = self.build()
        entered, closed = asyncio.Event(), asyncio.Event()
        async def execute(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        runner.execute = execute
        services = WorkflowServices(plan)
        pending = asyncio.create_task(flow.run(plan, TaskMaterial('task', 'Do work'), baseline, services))
        await entered.wait()
        services.signal.set()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertTrue(closed.is_set())

    async def test_agent_edits_a_detached_workspace_using_public_tools(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        provider = FauxProvider()
        provider.respond_tool_call('read_file', {'path': 'context/task.md'})
        provider.respond_tool_call('read_file', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'New task procedure'})
        provider.respond_text('{"reasons":[{"component_id":"prompt","explanation":"Observed omission","evidence_ids":["reference"]}]}')
        plan = RunPlan('job', version(), ('prompt',))
        task = TaskMaterial('task', 'Inspect the source')
        record = ExecutionRecord('reference', task.task_id, task.material_id, baseline.snapshot_id,
                                 plan.parent.state, plan.conditions_id, 'completed', 'Missing inspection')
        from fruitfly_agent.lab.improvement.api import ProposalRequest
        request = ProposalRequest(plan, task, baseline, (record,), 'invariant', 0)
        services = WorkflowServices(plan)
        editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, registry)
        candidate = await editor.edit('propose', request, services)
        self.assertEqual(candidate.changed_ids, ('prompt',))
        self.assertEqual(services.used['model'], 4)
        self.assertEqual(baseline.component('prompt').files[0].text, 'prompt')
        self.assertTrue(any(event == 'editor-read' for event, _ in services.events))

    def test_workspace_paths_binary_sources_and_read_only_evidence(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'input.bin').write_bytes(b'\x00\xff')
            task = WorkspaceTaskSource(root, artifacts).freeze('task', 'Read binary source', paths=('input.bin',))
            self.assertEqual(artifacts.read(task.inputs[0].artifact_id), b'\x00\xff')
        workspace = EvidenceWorkspace(baseline=baseline, files={'context/task.md': b'task'}, writable_ids=('prompt',))
        for path in ('../escape', '/etc/passwd', 'context/task.md', 'harness/memory/instructions.txt'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                workspace.write(path, 'unexpected')
        self.assertEqual(workspace.read('context/task.md'), b'task')
        self.assertEqual(HarnessSnapshot.from_dict(baseline.to_dict()), baseline)

    async def test_parallel_proposals_share_evidence_without_seeing_peer_edits(self):
        flow, plan, baseline, _ = self.build()
        generator = RuleGenerator()
        flow.generators = GeneratorRegistry()
        flow.generators.register('rule-generator', lambda: generator)
        plan = replace(plan, width=2)
        await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(len(generator.requests), 4)
        self.assertEqual({tuple(r.run_id for r in q.records) for q in generator.requests}, {('run-1', 'run-2')})
        self.assertTrue(all(q.history == () for q in generator.requests))

    async def test_model_based_algorithm_can_use_budgeted_completion_without_editor(self):
        flow, plan, baseline, runner = self.build()
        class NumericalSearch(RuleGenerator):
            required_capabilities = frozenset({'model'})
            async def propose(self, request, services):
                self.assertion = await services.complete('Return a proposed edit', request.scope)
                return await super().propose(request, services)
        generator = NumericalSearch()
        flow.generators = GeneratorRegistry()
        flow.generators.register('rule-generator', lambda: generator, required_capabilities=generator.required_capabilities)
        completion = AsyncMock(return_value='proposed')
        services = WorkflowServices(plan, complete=completion)
        result = await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, services)
        self.assertEqual(result.stop_reason, 'completed')
        self.assertEqual(completion.await_count, 2)
        self.assertEqual(services.used['model'], 2)
        self.assertIsNone(services.editor)

    def test_discovery_does_not_construct_generators_and_instances_are_job_local(self):
        constructed = []
        def create():
            value = RuleGenerator()
            constructed.append(value)
            return value
        registry = GeneratorRegistry()
        registry.register('rule-generator', create, label='Custom search')
        self.assertEqual(registry.definitions()[0].label, 'Custom search')
        self.assertEqual(constructed, [])
        self.assertIsNot(registry.create('rule-generator'), registry.create('rule-generator'))

    async def test_i_components_require_improver_comparison_before_execution(self):
        flow, plan, baseline, runner = self.build()
        document = replace(baseline.component('prompt'), role='I')
        adapter = FileComponentAdapter(document, lambda doc: None)
        flow.components = ComponentRegistry((adapter,))
        baseline = flow.components.snapshot()
        plan = replace(plan, component_ids=('prompt',))
        with self.assertRaisesRegex(ValueError, 'improver comparison'):
            await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
        self.assertEqual(runner.calls, [])

    async def test_timeout_closes_running_work_and_selector_cannot_invent_output(self):
        flow, plan, baseline, runner = self.build()
        services = WorkflowServices(replace(plan, operation_timeout=0.01))
        closed = asyncio.Event()
        async def blocking():
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        with self.assertRaises(TimeoutError):
            await services.operation(blocking())
        self.assertTrue(closed.is_set())
        flow.selector.select = AsyncMock(return_value=SelectionDecision('invented', 'No real result'))
        plan = replace(plan, width=2)
        with self.assertRaisesRegex(ValueError, 'existing completed execution'):
            await flow.run(plan, TaskMaterial('task', 'Do work'), baseline, WorkflowServices(plan))
