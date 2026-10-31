"""Configured I values reach bounded inner execution and exact evidence pages."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructionTarget
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.experiments import EpisodeRequest
from fruitfly_agent.lab.improvement.assessment.instructions import EvaluatorInstructionTarget, EvaluatorInstructions
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
from fruitfly_agent.lab.improvement.improver.episodes import NativeEpisodeExecutor
from tests.support.faux_provider import FauxProvider
from tests.support.pipeline import version


class ImprovementConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_receipt_records_actual_returned_interval(self):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),))
        workspace = EvidenceWorkspace(baseline=components.snapshot(), files={'evidence.txt': b'01234567890123456789'}, writable_ids=())
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'evidence.txt'})
        provider.respond_text('done')
        services = WorkflowServices(RunPlan('pages', version(), ('base_prompt',)))
        try:
            await EvidenceSession(AgentLoopConfig(provider=provider), artifacts, page_characters=7).session(
                'Inspect the evidence.', workspace, services)
            pages = [fields for event, fields in services.events if event == 'evidence-page']
            self.assertEqual(len(pages), 1)
            self.assertEqual((pages[0]['start'], pages[0]['end'], pages[0]['characters']), (0, 7, 20))
            self.assertEqual(pages[0]['next_offset'],7)
            result = provider.calls[-1]['messages'][-1]
            self.assertEqual(json.loads(result.content[0].text)['text'],'0123456')
        finally:
            await services.close()

    async def test_fixed_experiment_settings_drive_inner_research_and_rounds(self):
        artifacts = MemoryArtifacts()
        evaluator = EvaluatorInstructionTarget()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'), 'system-prompt'),
            TextComponentAdapter(EditorInstructionTarget(), 'improvement-instructions'),
            TextComponentAdapter(evaluator, 'evaluator-instructions')))
        baseline = components.snapshot()
        old = baseline.component('improvement-evaluator')
        changed_values = json.loads(old.files[0].text); changed_values['instructions']['compare'] = 'Prefer verified task completion. EVALUATOR_CANDIDATE'
        changed = replace(old, files=(ComponentFile('instructions.txt', json.dumps(changed_values)),))
        candidate = HarnessSnapshot(tuple(changed if doc.component_id == changed.component_id else doc for doc in baseline.components))
        provider = FauxProvider()
        def response(view, *, signal=None):
            async def stream():
                yield StreamDone(AssistantMessage(content=[TextBlock('answer')], stop_reason='stop'))
            return AssistantMessageEventStream(stream())
        provider.script = [response] * 30
        outer = RunPlan('i-settings', version(), ('improvement-evaluator',))
        services = WorkflowServices(outer)
        config = AgentLoopConfig(provider=provider)
        context = ExecutionContext('.', artifacts, components, None, config, config, plan=outer, services=services,
                                   workflow_settings={'research': {'enabled': True}})
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
                    (EditReason('base_prompt', 'Synthetic wiring check.', (request.records[0].run_id,),expected_effect='Change the observed task response.'),)),))
        class Policy:
            async def score(self, output, case):
                return SimpleNamespace(score=float(output == 'answer'))
        episode = SimpleNamespace(evaluations=(SimpleNamespace(input='Private check.'),),
                                  suite=SimpleNamespace(evaluation_policy=Policy()))
        parameters = {'inner_depth': 3, 'inner_model_calls': 32, 'inner_executions': 16, 'evaluation_model_calls': 1,
                      'inner_strategy': 'simple'}
        try:
            executor = NativeEpisodeExecutor(context, episode, parameters, generator_factory=Generator)
            request = EpisodeRequest('episode', baseline.component('improvement-editor').files[0].text, baseline,
                                     ('base_prompt',), TaskMaterial('adaptation', 'Do the task.'), 0, candidate)
            result = await executor.run(request, signal=services.signal)
            self.assertEqual(Generator.count, 3)
            self.assertEqual([r.path for r in Generator.contexts], ['research.json', 'research.json', 'research.json'])
            self.assertTrue(all(json.loads(artifacts.read(r.artifact_id))['entries'] for r in Generator.contexts))
            self.assertEqual(result.episode_id, 'episode')
            self.assertLessEqual(services.used['model'], 40)
            self.assertNotIn('EVALUATOR_CANDIDATE', evaluator.instructions.compare)
        finally:
            await services.close()

    def test_evaluator_grants_allow_only_prompts_and_enforce_fixed_fields(self):
        target = EvaluatorInstructionTarget()
        value = json.loads(target.snapshot().text)
        value['instructions']['assess'] = 'Identify unsupported completion claims.'
        target.validate_change(json.dumps(value), {'editable_fields': ['parameters.instructions.assess']})
        with self.assertRaisesRegex(ValueError, 'fixed'):
            target.validate_change(json.dumps(value), {'editable_fields': ['parameters.instructions.compare']})
        value['max_model_calls'] = 100
        with self.assertRaises(ValueError): target.validate(json.dumps(value))
        with self.assertRaises(ValueError): target.validate_options({'editable_fields': ['max_model_calls']})

    async def test_candidate_editor_prompt_changes_actual_inner_editing(self):
        from tests.support.self_improver import ProceduralProvider
        from fruitfly_agent.lab.improvement.editor.instructions import EditorInstructions
        components=ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'),'system-prompt'),
            TextComponentAdapter(EditorInstructionTarget(),'improvement-instructions')))
        baseline=components.snapshot();artifacts=MemoryArtifacts();provider=ProceduralProvider()
        plan=RunPlan('editor-policy',version(),('improvement-editor',))
        services=WorkflowServices(plan);config=AgentLoopConfig(provider=provider)
        context=ExecutionContext('.',artifacts,components,None,config,config,plan=plan,services=services)
        class Policy:
            def score(self,output,case):return SimpleNamespace(score=float(output=='A'))
        episode=SimpleNamespace(evaluations=(SimpleNamespace(input='Private check.'),),suite=SimpleNamespace(evaluation_policy=Policy()))
        results=[]
        try:
            for index,mission in enumerate(('STEP: improve from observed evidence','Keep the original procedure')):
                old=baseline.component('improvement-editor');value=json.loads(old.files[0].text)
                value['instructions']['propose']=mission
                changed=replace(old,files=(ComponentFile('instructions.txt',json.dumps(value)),))
                candidate=HarnessSnapshot(tuple(changed if d.component_id==changed.component_id else d for d in baseline.components))
                result=await NativeEpisodeExecutor(context,episode,{'inner_depth':1,'inner_strategy':'simple'}).run(
                    EpisodeRequest('episode-'+str(index),changed.files[0].text,baseline,('base_prompt',),TaskMaterial('adaptation','Do work'),0,candidate),signal=services.signal)
                results.append(result)
            self.assertEqual(results[0].scores_after,(1,))
            self.assertEqual(results[1].scores_after,(0,))
            self.assertEqual(components.snapshot(),baseline)
        finally:await services.close()

    def test_editor_rejects_removed_allowances(self):
        target=EditorInstructionTarget();value=json.loads(target.snapshot().text)
        value['max_tool_calls']=1
        with self.assertRaises(ValueError):target.validate(json.dumps(value))
        with self.assertRaises(ValueError):target.validate_options({'editable_fields':['max_turns']})
