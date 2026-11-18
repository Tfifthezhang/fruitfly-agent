"""All research roles assemble real isolated context policy and archive readers."""
import json
import re
from uuid import uuid4
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from pathlib import Path
import tempfile
import unittest
import yaml
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
from fruitfly_agent.run.improvement.roles import ResearchRoles
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from tests.support.assembly import AssemblyWorkspace
from tests.support.stages import proposal_fixture
from tests.support.faux_provider import FauxProvider


def tool_response(name, arguments):
    async def events():
        yield StreamDone(AssistantMessage([ToolCallBlock(uuid4().hex, name, arguments)], 'toolUse'))
    return AssistantMessageEventStream(events())


class ResearchRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_roles_without_delegation_compact_and_read_original_archive_without_new_citations(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        assembly = AssemblyWorkspace(root)
        path = root / 'config.yaml'
        path.write_text(yaml.safe_dump({'default_profile': 'test', 'profiles': {'test': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {'local-env': {'default': True}, 'read-tool': {'default': True},
                'context-budget': {'inline': {'id': 'context-budget', 'role': 'H',
                    'implementation': 'context-budget', 'parameters': {'settings': {
                        'trigger_ratio': .6, 'target_ratio': .4}}}},
                'layered-compaction': {'default': True}, 'work-products': {'default': True}}, 'S': {}, 'I': {}}}}))
        roles = ResearchRoles(root, path, registry=assembly.registry, environment={})
        self.addAsyncCleanup(roles.aclose)
        artifacts = DataArtifactStore(root / 'artifacts')
        _, plan, baseline, _ = proposal_fixture()
        for role in ('organizer', 'editor', 'assessor'):
            with self.subTest(role=role):
                provider = FauxProvider()
                for _ in range(4):
                    provider.respond_tool_call('read', {'path': 'material.txt'})
                def read_index(view, signal=None):
                    text = '\n'.join(getattr(m, 'text', '') for m in view.messages)
                    reference = re.search(r'resource://[^/\s]+/[^/\s]+/', text).group(0) + 'index'
                    return tool_response('read', {'path': reference, 'limit': 6000})
                def read_original(view, signal=None):
                    page = json.loads(view.messages[-1].text)
                    self.assertNotIn('citation_id', page)
                    index = json.loads(page['text'])
                    original = next(row for row in index['messages'] if row['excerpt'].startswith('toolResult '))
                    return tool_response('read', {'path': original['reference'], 'limit': 1000})
                def confirm(view, signal=None):
                    page = json.loads(view.messages[-1].text)
                    self.assertIn('EVIDENCE', page['text'])
                    self.assertNotIn('citation_id', page)
                    async def events():
                        yield StreamDone(AssistantMessage([], 'stop'))
                    return AssistantMessageEventStream(events())
                provider.script.extend((read_index, read_original, confirm))
                workspace = EvidenceWorkspace(baseline=baseline, files={'material.txt': b'EVIDENCE ' * 2000}, writable_ids=())
                factory = roles.runtime_factory(role, root / role, artifacts, {})
                async with StageServices(plan) as services:
                    response = await EvidenceSession(AgentLoopConfig(provider, max_tokens=128, context_window=9000), None,
                        runtime_factory=factory, settings={'supply': {'max_pages': 32}}).session('Inspect material', workspace, services)
                self.assertEqual('', response)
                session_path = next((root / role).glob('*.jsonl'))
                with Session(session_path) as session:
                    entries = session.read_all()
                    self.assertTrue(any(e.type == 'compaction' for e in entries))
                    manifest = next(e.payload['manifest'] for e in entries if e.payload.get('kind') == 'research-runtime')
                    self.assertEqual({'context-budget', 'layered-compaction', 'work-products'}, {r['id'] for r in manifest['components']})
                    self.assertEqual({'trigger_ratio': .6, 'target_ratio': .4}, manifest['context_budget'])
                    self.assertEqual(.6, manifest['context_budget']['trigger_ratio'])
                retained = next(fields['artifact_id'] for event, fields in services.events if event == 'research-session')
                self.assertEqual(session_path.read_bytes(), artifacts.read_bytes(retained))
                # The final model projection has a recoverable, session-scoped archive reference.
                serialized = str(provider.calls[-1]['messages'])
                self.assertIn('resource://', serialized)
                self.assertLess(len(serialized), 4 * 12000)
                self.assertEqual(0, assembly.registry.create.call_count)

    async def test_owner_submission_repairs_a_saved_report_without_retransmitting_it(self):
        from fruitfly_agent.lab.improvement.organizer import LayeredOrganizer
        from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.run.storage.research_bundles import ArtifactPort
        from tests.support.stages import Runner
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        fixture = AssemblyWorkspace(root)
        config_path = root / 'config.yaml'
        config_path.write_text(yaml.safe_dump({'default_profile': 'test', 'profiles': {'test': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline'}},
            'H': {'work-products': {'default': True}}, 'S': {}, 'I': {}}}}))
        roles = ResearchRoles(root, config_path, registry=fixture.registry, environment={})
        self.addAsyncCleanup(roles.aclose)
        artifacts = DataArtifactStore(root / 'artifacts')
        _, plan, baseline, _ = proposal_fixture()
        task = TaskMaterial('task', 'Inspect supplied execution')
        record = await Runner().execute(plan, task, baseline)
        provider = FauxProvider()
        provider.respond_tool_call('read', {'path': 'context/batch.json'})
        body = 'Factual navigation text. ' * 200
        def draft(view, signal=None):
            source = json.loads(view.messages[-1].text)
            citation = {'path': source['path'], 'citation_id': source['citation_id']}
            document = {'schema_version': 2, 'sections': [{'title': 'Observations', 'summary': body,
                'sources': [citation]}], 'findings': [{'issue_id': 'inspect-scope',
                'signal': 'Further evidence is needed.', 'facts': [{'text': 'A batch was supplied.', 'sources': [citation]}],
                'hypotheses': [], 'counterevidence': [], 'unknowns': [{'question': 'Which historical settings applied?',
                    'materials': ['/remote/history/configuration.json'], 'availability': 'not_granted'}],
                'run_ids': [record.run_id], 'control_ids': [], 'status': 'needs_evidence', 'sources_note': 'unsupported field'}]}
            return tool_response('save_checkpoint', {'name': 'guide', 'content': json.dumps(document), 'expected_revision': 0})
        provider.script.append(draft)
        provider.respond_tool_call('submit_work_product', {'producer': 'parent', 'name': 'guide', 'revision': 1})
        provider.respond_tool_call('patch_checkpoint', {'name': 'guide', 'expected_revision': 1,
            'changes': [{'path': ['findings', '0', 'sources_note'], 'operation': 'remove'}]})
        provider.respond_tool_call('submit_work_product', {'producer': 'parent', 'name': 'guide', 'revision': 2})
        provider.respond_tool_call('patch_checkpoint', {'name': 'guide', 'expected_revision': 2,
            'changes': [{'path': ['findings', '0', 'unknowns', '0', 'materials'], 'operation': 'replace',
                'value': '["context/history/configuration.json"]'}]})
        provider.respond_tool_call('submit_work_product', {'producer': 'parent', 'name': 'guide', 'revision': 3})
        organizer = LayeredOrganizer(AgentLoopConfig(provider, max_tokens=128, context_window=16000), ArtifactPort(artifacts),
            runtime_factory=roles.runtime_factory('organizer', root / 'roles', artifacts, {}))
        async with StageServices(plan) as services:
            view = await organizer.organize(OrganizationRequest((task,), (record,)), services)
        guide = next(r for r in view.resources if r.path == 'organization/guide.json')
        result = json.loads(artifacts.read_bytes(guide.artifact_id))
        self.assertEqual(body, result['sections'][0]['summary'])
        self.assertNotIn('sources_note', result['findings'][0])
        self.assertEqual(['context/history/configuration.json'], result['findings'][0]['unknowns'][0]['materials'])
        errors = [fields['result'] for event, fields in services.events
            if event == 'tool-result' and fields['result']['isError']]
        self.assertEqual(2, len(errors))
        calls = [call for message in provider.calls[-1]['messages'] if isinstance(message, AssistantMessage)
                 for call in message.tool_calls if call.name == 'save_checkpoint']
        self.assertEqual(1, len(calls))
        self.assertEqual(0, fixture.registry.create.call_count)

    async def test_context_auxiliary_role_inherits_the_actual_role_model(self):
        from dataclasses import replace
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        fixture = AssemblyWorkspace(root)
        path = root / 'config.yaml'
        path.write_text(yaml.safe_dump({'default_profile': 'test', 'profiles': {'test': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline', 'context_summary': {'inherit': 'executor'}}},
            'H': {'local-env': {'default': True}, 'read-tool': {'default': True},
                'layered-compaction': {'inline': {'id': 'layered-compaction', 'role': 'H',
                    'implementation': 'layered-compaction', 'parameters': {'settings': {'mode': 'hybrid'}}}}}, 'S': {}, 'I': {}}}}))
        roles = ResearchRoles(root, path, registry=fixture.registry, environment={})
        self.addAsyncCleanup(roles.aclose)
        roles.specs['secondary'] = replace(roles.specs['offline'], model='role-specific-model')
        roles.overrides['organizer'] = 'secondary'
        artifacts = DataArtifactStore(root / 'artifacts')
        _, plan, baseline, _ = proposal_fixture()
        provider = FauxProvider(); provider.respond_text('done')
        workspace = EvidenceWorkspace(baseline=baseline, files={'a.txt': b'evidence'}, writable_ids=())
        factory = roles.runtime_factory('organizer', root / 'roles', artifacts, {})
        async with StageServices(plan) as services:
            await EvidenceSession(AgentLoopConfig(provider), None, runtime_factory=factory).session('Inspect', workspace, services)
        self.assertEqual('role-specific-model', fixture.registry.create.call_args.args[0].model)
        self.assertEqual(1, fixture.registry.create.call_count)
