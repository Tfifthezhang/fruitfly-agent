"""Organizer I changes the actual reading guide while retaining original grants."""
from dataclasses import replace
import json
import unittest
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.organizer import LayeredOrganizer, OrganizerInstructions
from fruitfly_agent.lab.improvement.organizer.improvement import candidate_organizer
from fruitfly_agent.lab.improvement.organizer.instructions import instruction_target
from fruitfly_agent.lab.improvement.components.text import TextComponentAdapter
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.faux_provider import FauxProvider
from tests.support.stages import proposal_fixture, Runner
from tests.support.configuration import with_component_text, component_text


class OrganizerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_supplies_official_observations_to_organizer(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from fruitfly_agent.lab.improvement.stages.organize import organize
        from fruitfly_agent.improvement.contracts.stages import StageInputs
        from fruitfly_agent.improvement.contracts.organization import EvidenceView
        from fruitfly_agent.improvement.contracts.tasks import Resource
        _, plan, _, _ = proposal_fixture()
        artifacts = MemoryArtifacts()
        observation = {'run_id': 'execution', 'name': 'official_reward',
            'value': {'reward': 1.0}}
        def put(path, value, kind='diagnostic'):
            return Resource(path, artifacts.put(json.dumps(value).encode()),
                'application/json', kind)
        worker = SimpleNamespace(organize=AsyncMock(return_value=EvidenceView((), (), 'fixture', 'fixture')))
        ports = SimpleNamespace(organizer=worker, put=put,
            input_batch=lambda resources: SimpleNamespace(tasks=(TaskMaterial('task', 'Inspect'),), records=(), observations=(observation,)),
            create_services=lambda: StageServices(plan))
        await organize(ports, SimpleNamespace(parameters={}), StageInputs())
        request = worker.organize.call_args.args[0]
        resource = next(r for r in request.context if r.path == 'observations.json')
        self.assertEqual([observation], json.loads(artifacts.read(resource.artifact_id)))

    async def test_readable_batch_and_authorized_i_candidate_reach_actual_model(self):
        _, plan, baseline, _ = proposal_fixture()
        artifacts = MemoryArtifacts()
        task = TaskMaterial('task', 'Supply the fixture output')
        record = await Runner().execute(plan, task, baseline)
        request = OrganizationRequest((task,), (record,), instruction='Keep the guide compact for this invocation.')
        provider = FauxProvider()
        def answer(view, signal=None):
            self.assertIn('Invocation requirements:\nKeep the guide compact for this invocation.', view.system_prompt)
            tool_result = json.loads(view.messages[-1].text)
            source = {'path': 'context/batch.json', 'citation_id': tool_result['citation_id']}
            guide = {'findings': [{'issue_id': 'missing-diagnostics', 'signal': 'Unknown execution diagnostics',
                'facts': ['One retained execution'], 'hypotheses': ['Collection may be incomplete'],
                'counterevidence': [], 'unknowns': ['No terminal reason supplied'], 'sources': [source]}], 'sections': [{'title': 'Candidate view' if 'CANDIDATE GUIDE' in view.system_prompt else 'Task view',
                'summary': 'One retained execution; inspect the output.',
                'sources': [{'path': 'context/batch.json', 'citation_id': tool_result['citation_id']}]}]}
            async def events():
                yield StreamDone(AssistantMessage([TextBlock(json.dumps(guide))], stop_reason='stop'))
            return AssistantMessageEventStream(events())
        owner = instruction_target()
        adapter = TextComponentAdapter(owner, 'improvement-instructions')
        document = adapter.snapshot()
        import yaml
        from fruitfly_agent.improvement.contracts.components import ComponentFile
        values = yaml.safe_load(document.files[0].text)
        values['parameters']['instructions']['organize'] = 'CANDIDATE GUIDE: organize only a readable task guide.'
        changed = replace(document, files=(ComponentFile('parameters.yaml', yaml.safe_dump(values)),))
        trial = candidate_organizer(AgentLoopConfig(provider), artifacts, changed,
            options={'editable_fields': ['parameters.instructions.organize']})
        titles = []
        for organizer in (LayeredOrganizer(AgentLoopConfig(provider), artifacts), trial):
            provider.respond_tool_call('read', {'path': 'context/batch.json'})
            provider.script.append(answer)
            async with StageServices(plan) as services:
                view = await organizer.organize(request, services)
                guide = next(r for r in view.resources if r.path == 'organization/guide.json')
                document = json.loads(artifacts.read(guide.artifact_id))
                titles.append(document['sections'][0]['title'])
                self.assertEqual('missing-diagnostics', document['findings'][0]['issue_id'])
                self.assertTrue(any(fields.get('role') == 'organizer' for _, fields in services.events))
        self.assertEqual(titles, ['Task view', 'Candidate view'])
        self.assertEqual(record.output, '\n'.join(c.files[0].text for c in baseline.components))
        self.assertTrue(all('write_file' not in row['tools'] for row in provider.calls))

