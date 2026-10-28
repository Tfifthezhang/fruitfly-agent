"""Configured I values reach bounded inner execution and exact evidence pages."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.api import (ComponentRegistry, TextComponentAdapter, RunPlan, WorkflowServices,
    TaskMaterial, HarnessSnapshot, ComponentFile, CandidateBundle, EditReason, ProposalResult,
    EditorInstructionTarget, ExecutionContext, EpisodeRequest)
from fruitfly_agent.lab.improvement.components.configuration import ImprovementSettingsTarget
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
from fruitfly_agent.lab.improvement.workspaces import WorkspaceSession
from fruitfly_agent.lab.improvement.improver.episodes import NativeEpisodeExecutor
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import version


class ImprovementConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_receipt_records_actual_returned_interval(self):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),))
        workspace = EvidenceWorkspace(baseline=components.snapshot(), files={'evidence.txt': b'01234567890123456789'}, writable_ids=())
        provider = FauxProvider()
        provider.respond_tool_call('read_file', {'path': 'evidence.txt'})
        provider.respond_text('done')
        services = WorkflowServices(RunPlan('pages', version(), ('base_prompt',)))
        try:
            await WorkspaceSession(AgentLoopConfig(provider=provider), artifacts, page_characters=7).session(
                'Inspect the evidence.', workspace, services)
            pages = [fields for event, fields in services.events if event == 'editor-evidence-page']
            self.assertEqual(len(pages), 1)
            self.assertEqual((pages[0]['start'], pages[0]['end'], pages[0]['characters']), (0, 7, 20))
            self.assertTrue(pages[0]['truncated'])
            self.assertEqual(pages[0]['projection'], 'granted-full')
            result = provider.calls[-1]['messages'][-1]
            self.assertIn('0123456\n[Partial text:', result.content[0].text)
        finally:
            await services.close()

    async def test_candidate_search_settings_change_actual_inner_round_count_under_fixed_budget(self):
        artifacts = MemoryArtifacts()
        search = ImprovementSettingsTarget('search', {'strategy': 'simple', 'rounds': 1})
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),
            TextComponentAdapter(EditorInstructionTarget(), 'improvement-instructions'),
            TextComponentAdapter(search, 'improvement-settings')))
        baseline = components.snapshot()
        old = baseline.component('improvement-search')
        changed_values = json.loads(old.files[0].text); changed_values['rounds'] = 2
        changed_values['research']['enabled'] = True
        changed = replace(old, files=(ComponentFile('instructions.txt', json.dumps(changed_values)),))
        candidate = HarnessSnapshot(tuple(changed if doc.component_id == changed.component_id else doc for doc in baseline.components))
        provider = FauxProvider()
        def response(view, *, signal=None):
            async def stream():
                yield StreamDone(AssistantMessage(content=[TextBlock('answer')], stop_reason='stop'))
            return AssistantMessageEventStream(stream())
        provider.script = [response] * 30
        outer = RunPlan('i-settings', version(), ('improvement-search',), max_model_calls=128, max_executions=64)
        services = WorkflowServices(outer)
        config = AgentLoopConfig(provider=provider)
        context = ExecutionContext('.', artifacts, components, None, config, config, plan=outer, services=services,
                                   system_settings={'search': search.parameters})
        class Generator:
            generator_id = 'inner-fixture'
            required_capabilities = frozenset()
            count = 0
            contexts = []
            async def propose(self, request, generation):
                type(self).count += 1
                type(self).contexts.extend(request.context)
                old = request.baseline.component('base_prompt')
                changed = replace(old, files=(ComponentFile('instructions.txt', 'variant ' + str(type(self).count)),))
                harness = HarnessSnapshot(tuple(changed if d.component_id == changed.component_id else d for d in request.baseline.components))
                return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
                    (EditReason('base_prompt', 'Synthetic wiring check.', (request.records[0].run_id,)),)),))
        class Policy:
            async def score(self, output, case):
                return SimpleNamespace(score=float(output == 'answer'))
        episode = SimpleNamespace(evaluations=(SimpleNamespace(input='Private check.'),),
                                  suite=SimpleNamespace(evaluation_policy=Policy()))
        parameters = {'inner_depth': 3, 'inner_model_calls': 32, 'inner_executions': 16, 'evaluation_model_calls': 1,
                      'inner_strategy': 'simple'}
        budget = services.budget.child({'model': 40, 'execution': 24})
        try:
            executor = NativeEpisodeExecutor(context, episode, parameters, generator_factory=Generator)
            request = EpisodeRequest('episode', baseline.component('improvement-editor').files[0].text, baseline,
                                     ('base_prompt',), TaskMaterial('adaptation', 'Do the task.'), 0, candidate)
            result = await executor.run(request, budget=budget, signal=services.signal)
            self.assertEqual(Generator.count, 2)
            self.assertEqual([r.path for r in Generator.contexts], ['research.json', 'research.json'])
            self.assertTrue(all(json.loads(artifacts.read(r.artifact_id))['entries'] for r in Generator.contexts))
            self.assertEqual(result.episode_id, 'episode')
            self.assertLessEqual(services.used['model'], 40)
            self.assertEqual(search.parameters['rounds'], 1)
        finally:
            budget.close()
            await services.close()

    def test_feedback_editing_cannot_change_hard_local_assessor_allowance(self):
        target = ImprovementSettingsTarget('feedback', {})
        value = json.loads(target.snapshot().text)
        value['judgment_guidance'] = 'Identify unsupported completion claims.'
        target.validate(json.dumps(value))
        value['process_assessment']['max_model_calls'] += 1
        with self.assertRaisesRegex(ValueError, 'fixed'):
            target.validate(json.dumps(value))

    async def test_configured_assessor_guidance_reaches_both_actual_model_protocols(self):
        from fruitfly_agent.lab.improvement.assessment.completed_assessors import CompletedModelAssessor
        calls = []
        evidence = 'sha256:' + 'a' * 64
        async def complete(instruction, payload):
            calls.append(instruction)
            if 'incumbent' in payload:
                return {'run_id': 'run', 'reason': 'Observed.', 'evidence_ids': [evidence]}
            return {'metrics': [], 'detail': 'Observed.', 'evidence_ids': [evidence]}
        service = SimpleNamespace(complete=complete, render=lambda values: {}, instructions={
            'judgment_guidance': 'Identify unfinished verification.',
            'comparison_guidance': 'Investigate repeated failed calls.'})
        assessor = CompletedModelAssessor(service)
        # No model request is needed to establish that configured text reaches
        # the independent model protocol; this fake observes that boundary.
        from fruitfly_agent.improvement.contracts.live import EvidencePosition
        value = SimpleNamespace(position=EvidencePosition('run', evidence, 'segment', 0), facts_id=evidence)
        await assessor.assess(value)
        await assessor.compare((value,), 'run')
        self.assertIn('Identify unfinished verification.', calls[0])
        self.assertIn('Investigate repeated failed calls.', calls[1])

    async def test_candidate_editor_allowance_changes_actual_inner_editing(self):
        from tests.support.self_improver import ProceduralProvider
        from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructions
        instructions = replace(EditorInstructions(), propose='STEP: improve the procedure from supplied evidence')
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),
            TextComponentAdapter(EditorInstructionTarget(instructions), 'improvement-instructions')))
        baseline = components.snapshot()
        provider = ProceduralProvider()
        artifacts = MemoryArtifacts()
        plan = RunPlan('editor-policy', version(), ('improvement-editor',), max_model_calls=256, max_executions=64)
        services = WorkflowServices(plan)
        config = AgentLoopConfig(provider=provider)
        context = ExecutionContext('.', artifacts, components, None, config, config, plan=plan, services=services)
        class Policy:
            def score(self, output, case): return SimpleNamespace(score=float(output == 'A'))
        episode = SimpleNamespace(evaluations=(SimpleNamespace(input='Private check.'),),
                                  suite=SimpleNamespace(evaluation_policy=Policy()))
        parameters = {'inner_depth': 1, 'inner_strategy': 'simple', 'inner_model_calls': 64,
            'inner_executions': 8, 'evaluation_model_calls': 1}
        results = []
        try:
            for calls in (48, 1):
                old = baseline.component('improvement-editor')
                value = json.loads(old.files[0].text); value['max_tool_calls'] = calls
                changed = replace(old, files=(ComponentFile('instructions.txt', json.dumps(value)),))
                candidate = HarnessSnapshot(tuple(changed if d.component_id == changed.component_id else d for d in baseline.components))
                budget = services.budget.child({'model': 80, 'execution': 12})
                try:
                    result = await NativeEpisodeExecutor(context, episode, parameters).run(EpisodeRequest(
                        'episode-' + str(calls), changed.files[0].text, baseline, ('base_prompt',),
                        TaskMaterial('adaptation', 'Do work'), 0, candidate), budget=budget, signal=services.signal)
                    results.append(result)
                finally: budget.close()
            self.assertEqual(results[0].scores_after, (1,))
            self.assertNotEqual(results[0].outcome.harness, baseline)
            self.assertEqual(results[1].scores_after, (0,))
            self.assertEqual(results[1].outcome.harness.component('base_prompt'), baseline.component('base_prompt'))
            self.assertEqual(components.snapshot(), baseline)
        finally: await services.close()

    async def test_editor_turn_allowance_is_enforced_by_existing_core_loop(self):
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),))
        workspace = EvidenceWorkspace(baseline=components.snapshot(), files={}, writable_ids=())
        for turns, expected_calls in ((2, 2), (6, 5)):
            provider = FauxProvider()
            for _ in range(4): provider.respond(AssistantMessage([TextBlock('continued')], stop_reason='stop', continue_turn=True))
            provider.respond_text('done')
            services = WorkflowServices(RunPlan('turns-' + str(turns), version(), ('base_prompt',)))
            try:
                session = WorkspaceSession(AgentLoopConfig(provider=provider), MemoryArtifacts(), max_turns=turns)
                if turns == 2:
                    with self.assertRaisesRegex(ValueError, 'did not finish'):
                        await session.session('Inspect.', workspace, services)
                else:
                    self.assertEqual(await session.session('Inspect.', workspace, services), 'done')
                self.assertEqual(len(provider.calls), expected_calls)
            finally: await services.close()
