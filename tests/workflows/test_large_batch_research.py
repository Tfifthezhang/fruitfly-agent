"""Large retained batches produce traceable organization and detached candidates."""
import json
import unittest
import tempfile
import subprocess
import sys
from pathlib import Path
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
from fruitfly_agent.improvement.contracts.editing import ResearchProposalRequest
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.organizer import LayeredOrganizer
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.stages import proposal_fixture
from tests.support.faux_provider import FauxProvider


class LargeBatchResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_required_entry_fails_before_any_model_request(self):
        from fruitfly_agent.lab.improvement.evidence.resources import ReferenceWorkspace
        from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
        _, plan, baseline, _ = proposal_fixture()
        artifacts = MemoryArtifacts()
        workspace = ReferenceWorkspace(artifacts=artifacts, references={'INDEX.json': 'sha256:' + 'a' * 64},
            baseline=baseline, files={}, writable_ids=())
        provider = FauxProvider()
        async with StageServices(plan) as services:
            with self.assertRaisesRegex(ValueError, 'required entry documents unavailable'):
                await EvidenceSession(AgentLoopConfig(provider), artifacts).session('Inspect', workspace, services)
            self.assertTrue(any(event == 'research-preflight' for event, _ in services.events))
        self.assertFalse(provider.calls)

    async def test_large_batch_organizes_and_proposes_with_portable_source_spans(self):
        for count in (89, 256):
            with self.subTest(count=count):
                flow, plan, baseline, runner = proposal_fixture()
                artifacts = MemoryArtifacts()
                tasks = tuple(TaskMaterial('task-' + str(i), 'Inspect supplied material') for i in range(count))
                records = tuple([await runner.execute(plan, task, baseline) for task in tasks])
                organizer_provider = FauxProvider()
                organizer_provider.respond_tool_call('catalog', {'kind': 'executions', 'limit': 8})
                organizer_provider.respond_tool_call('read', {'path': 'context/executions/' + records[0].run_id + '/output.txt'})
                saved_guide = {}
                def submit_organization(view, signal=None):
                    page = json.loads(view.messages[-1].text)
                    source = {'path': page['path'], 'citation_id': page['citation_id']}
                    value = {'schema_version': 2, 'sections': [{'title': 'Observation',
                        'summary': 'Inspect the retained output.', 'sources': [source]}], 'findings': [{
                        'issue_id': 'inspection', 'signal': 'Inspection is absent',
                        'facts': [{'text': 'Output contains only component names.', 'sources': [source]}],
                        'hypotheses': ['Inspection guidance may help'], 'counterevidence': [], 'unknowns': [],
                        'run_ids': [records[0].run_id], 'control_ids': [], 'status': 'ready_for_proposal'}]}
                    fake = FauxProvider()
                    saved_guide.update(value)
                    bad_source = {'path': source['path'], 'citation_id': 'sha256:' + '0' * 64}
                    fake.respond_tool_call('check_organization', {'schema_version': 2, 'findings': [],
                        'sections': [{'title': str(i), 'summary': 'Unsupported draft', 'sources': [bad_source]} for i in range(2)]})
                    return fake(view, signal=signal)
                organizer_provider.script.append(submit_organization)
                def publish_organization(view, signal=None):
                    errors = json.loads(view.messages[-1].text)
                    self.assertFalse(errors['valid'])
                    self.assertEqual(2, len(errors['errors']))
                    fake = FauxProvider()
                    fake.respond_tool_call('submit_organization', saved_guide)
                    return fake(view, signal=signal)
                organizer_provider.script.append(publish_organization)
                async with StageServices(plan) as services:
                    view = await LayeredOrganizer(AgentLoopConfig(organizer_provider), artifacts).organize(
                        OrganizationRequest(tasks, records), services)
                provenance = next(r for r in view.resources if r.path == 'organization/provenance.json')
                spans = json.loads(artifacts.read(provenance.artifact_id))['sources']
                self.assertTrue(spans)
                for span in spans:
                    self.assertTrue(artifacts.read(span['artifact_id']).decode()[span['start']:span['end']])
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    for reference, data in artifacts.values.items():
                        (root / reference[7:]).write_bytes(data)
                    checked = subprocess.run([sys.executable, '-I', '-c', '''
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
index = json.loads((root / sys.argv[2]).read_bytes())
for span in index['sources']:
    data = (root / span['artifact_id'][7:]).read_bytes()
    assert 'sha256:' + hashlib.sha256(data).hexdigest() == span['artifact_id']
    assert data.decode()[span['start']:span['end']]
''', str(root), provenance.artifact_id[7:]], cwd=root, capture_output=True, text=True, timeout=10)
                    self.assertEqual(0, checked.returncode, checked.stderr)
                editor_provider = FauxProvider()
                editor_provider.respond_tool_call('list_targets', {})
                editor_provider.respond_tool_call('read', {'path': 'context/executions/' + records[0].run_id + '/output.txt'})
                editor_provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'Inspect first.'})
                draft = {'reasons': [{'component_id': 'prompt', 'explanation': 'Add inspection guidance.',
                    'expected_effect': 'Inspection precedes completion.', 'evidence_ids': [records[0].run_id],
                    'issue_ids': ['inspection']}]}
                editor_provider.respond_tool_call('check_candidate', draft)
                editor_provider.respond_tool_call('submit_candidate', draft)
                async with StageServices(plan) as services:
                    candidate = await AgentEditor(AgentLoopConfig(editor_provider), artifacts, flow.components).edit(
                        'propose', ResearchProposalRequest(plan, tasks, baseline, records, view.resources), services)
                self.assertEqual(('prompt',), candidate.changed_ids)
                self.assertEqual(baseline, flow.components.snapshot())
                self.assertFalse(editor_provider.script)
