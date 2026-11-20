import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.components.registry import ComponentRegistry
from fruitfly_agent.improvement.contracts.editing import ResearchProposalRequest
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import Resource, TaskMaterial
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.components.text import TextComponentAdapter
from fruitfly_agent.lab.improvement.editor.factory import create_editor
from fruitfly_agent.lab.improvement.editor.methods.gepa_reflection import compat
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.faux_provider import FauxProvider
from tests.support.stages import Runner, version
from tests.support.reflection import FixtureSignature


class GEPAReflectionTests(IsolatedAsyncioTestCase):
    async def test_one_draft_and_one_attribution_call_make_a_shared_candidate(self):
        artifacts = MemoryArtifacts()
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('Verify output.'), 'system-prompt'),))
        plan = RunPlan('gepa', version(), ('base_prompt',),
                       component_options={'base_prompt': {'editable_fields': ['parameters.instructions.system']}})
        components.configure(plan.component_options)
        baseline = components.snapshot()
        task = TaskMaterial('task', 'Produce a usable output.')
        record = await Runner().execute(plan, task, baseline)
        scope = [{'task_id': task.task_id, 'material_id': task.material_id, 'run_ids': [record.run_id]}]
        packet = {'membership': scope, 'scope_id': content_hash(canonical_json(scope)), 'group_findings': [],
                  'cards': [{'task_id': task.task_id, 'input': {'artifact_id': content_hash(task.instruction)},
                             'executions': [{'run_id': record.run_id, 'events': None,
                                 'output': {'artifact_id': content_hash(record.output)}, 'observations': [],
                                 'observation_supply': 'not_supplied'}]}]}
        resource = Resource('organization/reflection-packet.json', artifacts.put(canonical_json(packet).encode()))
        request = ResearchProposalRequest(plan, (task,), baseline, (record,), (resource,))
        provider = FauxProvider()
        provider.respond_text('Verify the existence and usability of the required output.')
        provider.respond_text(json.dumps({'reasons': [{'component_id': 'base_prompt',
            'explanation': 'The retained output lacks a demonstrated check.',
            'expected_effect': 'Make verification observable.', 'evidence_ids': [record.run_id]}],
            'decision': {'kind': 'candidate', 'explanation': 'One shared verification change',
                         'baseline_applicability': 'Compared against the supplied parent.'}}))
        with patch.object(compat, 'signature', return_value=FixtureSignature):
            editor = create_editor(AgentLoopConfig(provider=provider), artifacts, components,
                                   options={'method': 'gepa-reflection'})
        async with StageServices(plan) as services:
            candidate = await editor.edit('propose', request, services)
            self.assertEqual(candidate.changed_ids, ('base_prompt',))
            self.assertEqual(services.proposal_decision.kind, 'candidate')
            self.assertEqual(services.used['model'], 2)
        self.assertEqual(len(provider.calls), 2)
        self.assertTrue(all(not call['tools'] for call in provider.calls))
        self.assertIn('Verify output.', baseline.component('base_prompt').files[0].text)

    def test_workspace_editor_does_not_load_gepa(self):
        with patch.object(compat, 'signature', side_effect=AssertionError('GEPA dependency loaded')):
            editor = create_editor(AgentLoopConfig(provider=FauxProvider()), MemoryArtifacts(), None)
        self.assertEqual(editor.implementation_id, 'workspace-editor-v1')
