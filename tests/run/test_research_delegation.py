"""Research parent tools drive independent, attributed, read-only child loops."""
import asyncio
from pathlib import Path
import json
import tempfile
import unittest
import yaml

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, TextBlock, ToolCallBlock
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.core.session import Session
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.session import EvidenceSession
from fruitfly_agent.run.improvement.roles import ResearchRoles
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from tests.support.assembly import AssemblyWorkspace
from tests.support.faux_provider import FauxProvider
from tests.support.stages import proposal_fixture


def tool_response(name, arguments):
    async def events():
        yield StreamDone(AssistantMessage([ToolCallBlock('child-submit', name, arguments)], 'toolUse'))
    return AssistantMessageEventStream(events())


class ResearchDelegationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.assembly = AssemblyWorkspace(self.root)
        path = self.root / 'config.yaml'
        path.write_text(yaml.safe_dump({'default_profile': 'test', 'profiles': {'test': {
            'models': {'catalog': 'models.yaml', 'roles': {'executor': 'offline', 'subagent': {'inherit': 'executor'}}},
            'H': {'subagent': {'default': True}}, 'S': {}, 'I': {}}}}))
        self.roles = ResearchRoles(self.root, path, registry=self.assembly.registry, environment={})
        self.addAsyncCleanup(self.roles.aclose)
        self.artifacts = DataArtifactStore(self.root / 'artifacts')
        _, self.plan, baseline, _ = proposal_fixture()
        self.workspace = EvidenceWorkspace(baseline=baseline,
            files={'a.txt': b'observed failure', 'private.txt': b'UNASSIGNED PRIVATE MATERIAL'}, writable_ids=())
        self.parent = FauxProvider()
        self.settings = {'delegation': {'enabled': True}}
        self.children = []

    def create(self, child):
        def build(spec, environment):
            self.children.append(child)
            return child
        self.assembly.registry.create.side_effect = build

    def parent_spawn(self, materials):
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect assigned evidence and report uncertainty.',
            'worker': 'evidence-reader', 'materials': materials})
        self.parent.respond_text('Waiting for investigation')
        self.parent.respond_text('Integrated attributed findings')

    async def run_role(self, *, parts=None, mission='Investigate'):
        factory = self.roles.runtime_factory('editor', self.root / 'roles', self.artifacts, self.settings, parts=parts)
        async with StageServices(self.plan) as services:
            response = await EvidenceSession(AgentLoopConfig(self.parent, max_tokens=128), None,
                settings=self.settings, runtime_factory=factory).session(mission, self.workspace, services)
            return response, services.used, list(services.events)

    async def test_parent_delegates_and_integrates_validated_citations_without_original_read_claim(self):
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'a.txt'})
        def submit(view, signal=None):
            source = json.loads(view.messages[-1].text)
            self.assertEqual('observed failure', source['text'])
            return tool_response('submit_findings', {'summary': 'The assigned source records failure.',
                'sources': [{'path': 'a.txt', 'citation_id': source['citation_id']}], 'unknowns': ['Cause is unknown.']})
        child.script.append(submit)
        self.create(child)
        self.parent_spawn(['a.txt'])
        response, usage, events = await self.run_role()
        self.assertEqual('Integrated attributed findings', response)
        self.assertEqual({'catalog', 'search', 'read', 'submit_findings'}, set(child.calls[0]['tools']))
        self.assertNotIn('UNASSIGNED', str(child.calls))
        self.assertEqual(set(), self.workspace.provided_ids)
        self.assertEqual(1, len(self.workspace.eligible_paths('a.txt')))
        self.assertEqual(len('observed failure'), self.workspace.access.supply_characters)
        self.assertEqual(5, usage['model'])
        self.assertEqual(5, self.workspace.access.budget['model_requests'])
        self.assertTrue(any(event == 'delegation-findings' for event, _ in events))
        child_path = next((self.root / 'roles').glob('*.subagents/*/session.jsonl'))
        with Session(child_path) as session:
            metadata = next(e.payload for e in session.read_all() if e.payload.get('kind') == 'child-runtime')
            self.assertEqual({'read': 'assigned', 'write': 'deny', 'delegate': 'deny'}, metadata['manifest']['permissions'])
            self.assertEqual(['a.txt'], list(metadata['manifest']['grant']))

    async def test_invalid_material_grant_never_constructs_child(self):
        self.parent_spawn(['outside.txt'])
        response, _, _ = await self.run_role()
        self.assertIn('Waiting', response)
        self.assertFalse(self.assembly.registry.create.called)
        messages = self.parent.calls[1]['messages']
        self.assertIn('invalid_material_grant', str([m.to_dict() for m in messages]))
        self.assertEqual(set(), self.workspace.eligible_ids)

    async def test_unassigned_read_and_unvalidated_final_text_do_not_supply_parent_citations(self):
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'private.txt'})
        child.respond_tool_call('submit_findings', {'summary': 'Unsupported.',
            'sources': [{'path': 'private.txt', 'citation_id': 'sha256:' + '0' * 64}], 'unknowns': []})
        child.respond_text('This prose has no validated findings.')
        self.create(child)
        self.parent_spawn(['a.txt'])
        await self.run_role()
        self.assertNotIn('UNASSIGNED PRIVATE MATERIAL', str(child.calls))
        self.assertEqual(set(), self.workspace.eligible_ids)
        self.assertIn('invalid_worker_result', str([m.to_dict() for m in self.parent.calls[-1]['messages']]))

    async def test_children_share_stage_reading_allowance(self):
        self.workspace.files['b.txt'] = b'another finding'
        self.settings['supply'] = {'max_characters': 5, 'max_pages': 8}
        def build(spec, environment):
            child = FauxProvider()
            path = 'a.txt' if not self.children else 'b.txt'
            self.children.append(child)
            child.respond_tool_call('read', {'path': path})
            def submit(view, signal=None):
                page = json.loads(view.messages[-1].text)
                sources = [{'path': path, 'citation_id': page['citation_id']}] if 'citation_id' in page else []
                return tool_response('submit_findings', {'summary': 'Only the supplied portion is known.',
                    'sources': sources, 'unknowns': ['Reading allowance limits coverage.']})
            child.script.append(submit)
            return child
        self.assembly.registry.create.side_effect = build
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect a', 'worker': 'evidence-reader', 'materials': ['a.txt']})
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect b', 'worker': 'evidence-reader', 'materials': ['b.txt']})
        self.parent.respond_text('Waiting')
        self.parent.respond_text('Coverage is limited')
        await self.run_role()
        self.assertEqual(5, self.workspace.access.supply_characters)
        self.assertEqual(2, len(self.children))

    async def test_parent_cancellation_retires_child_provider_before_returning(self):
        entered = asyncio.Event()
        class Child(FauxProvider):
            closed = False
            async def aclose(self):
                self.closed = True
        child = Child()
        def blocked(view, signal=None):
            async def events():
                entered.set()
                await asyncio.Event().wait()
                yield StreamDone(AssistantMessage([TextBlock('unreachable')], 'stop'))
            return AssistantMessageEventStream(events())
        child.script.append(blocked)
        self.create(child)
        self.parent_spawn(['a.txt'])
        task = asyncio.create_task(self.run_role())
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(child.closed)
        self.assertEqual(set(), self.workspace.eligible_ids)

    async def test_unenabled_subagent_is_rejected_without_provider_construction(self):
        from dataclasses import replace
        self.roles.profile = replace(self.roles.profile, mechanisms=tuple(
            replace(selection, enabled=False) if selection.mechanism_id == 'subagent' else selection
            for selection in self.roles.profile.mechanisms))
        with self.assertRaisesRegex(ValueError, 'enabled subagent'):
            self.roles.runtime_factory('editor', self.root / 'roles', self.artifacts, self.settings)
        self.assertFalse(self.assembly.registry.create.called)
        self.assertFalse((self.root / 'roles').exists())

    async def test_editor_uses_child_execution_evidence_to_build_isolated_candidate(self):
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
        from fruitfly_agent.improvement.contracts.editing import ProposalRequest
        from fruitfly_agent.lab.improvement.editor import AgentEditor
        from fruitfly_agent.run.storage.research_bundles import ArtifactPort
        from tests.support.stages import fixture
        components, baseline = fixture()
        task = TaskMaterial('task', 'Inspect the source')
        record = ExecutionRecord('reference', task.task_id, task.material_id, baseline.snapshot_id,
            self.plan.parent.state, self.plan.conditions_id, 'completed', 'Missing inspection')
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'context/executions.json'})
        def submit(view, signal=None):
            page = json.loads(view.messages[-1].text)
            return tool_response('submit_findings', {'summary': 'Execution reference omitted inspection.',
                'sources': [{'path': 'context/executions.json', 'citation_id': page['citation_id']}],
                'unknowns': ['No causal proof.']})
        child.script.append(submit)
        self.create(child)
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Read the retained execution and identify omissions.',
            'worker': 'evidence-reader', 'materials': ['context/executions.json']})
        self.parent.respond_text('Waiting for evidence')
        self.parent.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'Inspect the source before modifying it.'})
        self.parent.respond_tool_call('submit_candidate', {'reasons': [{'component_id': 'prompt',
            'explanation': 'The delegated source inspection found an omission.',
            'expected_effect': 'Source inspection appears before modification; absence refutes it.',
            'evidence_ids': ['reference']}]})
        factory = self.roles.runtime_factory('editor', self.root / 'roles', self.artifacts, self.settings)
        editor = AgentEditor(AgentLoopConfig(self.parent, max_tokens=128), ArtifactPort(self.artifacts), components,
            settings=self.settings, runtime_factory=factory)
        request = ProposalRequest(self.plan, task, baseline, (record,), 'invariant', 0)
        async with StageServices(self.plan) as services:
            candidate = await editor.edit('propose', request, services)
        self.assertEqual(('prompt',), candidate.changed_ids)
        self.assertEqual('prompt', baseline.component('prompt').files[0].text)
        self.assertTrue(any(event == 'delegated-evidence-page' for event, _ in services.events))
        self.assertFalse(any(event == 'evidence-page' for event, _ in services.events))
        self.assertNotIn('write_file', child.calls[0]['tools'])

    async def test_terminal_parent_submission_cannot_hide_uncollected_children(self):
        from fruitfly_agent.core.data_model import AgentToolResult
        from fruitfly_agent.core.tool_runtime import AgentTool
        child = FauxProvider()
        def blocked(view, signal=None):
            async def events():
                await asyncio.Event().wait()
                yield StreamDone(AssistantMessage([TextBlock('unreachable')], 'stop'))
            return AssistantMessageEventStream(events())
        child.script.append(blocked)
        self.create(child)
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect assigned material',
            'worker': 'evidence-reader', 'materials': ['a.txt']})
        self.parent.respond_tool_call('finish', {})
        async def finish(ctx):
            return AgentToolResult([TextBlock('accepted format')], terminate=True)
        terminal = AgentTool('finish', 'Finish', 'Submit', {'type': 'object'}, finish)
        factory = self.roles.runtime_factory('editor', self.root / 'roles', self.artifacts, self.settings)
        async with StageServices(self.plan) as services:
            role = EvidenceSession(AgentLoopConfig(self.parent, max_tokens=128), None,
                settings=self.settings, runtime_factory=factory)
            with self.assertRaisesRegex(RuntimeError, 'subagent_results_uncollected'):
                await role.session('Investigate', self.workspace, services, extra_tools=(terminal,),
                    submission_result=lambda: 'accepted format')
        self.assertEqual(set(), self.workspace.eligible_ids)

    async def test_named_worker_yaml_changes_model_prompt_tools_and_local_reading_limit(self):
        from copy import deepcopy
        from fruitfly_agent.lab.catalog import materialize_system, load_system_config
        worker = deepcopy(self.roles.catalog.get('subagent').descriptor.normalize_parameters({})['workers']['evidence-reader'])
        worker.update(description='Inspect only the selected source.', model_role='editor', instructions='WORKER MARKER: inspect only supplied evidence.')
        worker['capabilities']['tools'] = ['read']
        worker['limits'].update(evidence_characters=3, evidence_responses=1, model_requests=8)
        worker['result']['max_characters'] = 2000
        component_path = self.root / 'workers.yaml'
        component_path.write_text(yaml.safe_dump({'id': 'subagent', 'role': 'H', 'implementation': 'subagent',
            'parameters': {'settings': {'workers': {'focused-reader': worker}}}}))
        model_path = self.root / 'models.yaml'
        models = yaml.safe_load(model_path.read_text())
        models['models']['secondary'] = {**models['models']['offline'], 'model': 'secondary-model'}
        model_path.write_text(yaml.safe_dump(models))
        path = self.root / 'config.yaml'
        system = yaml.safe_load(path.read_text())
        profile = system['profiles']['test']
        profile['models']['roles']['editor'] = 'secondary'
        profile['H']['subagent'] = {'file': 'workers.yaml'}
        path.write_text(yaml.safe_dump(system))
        self.roles = ResearchRoles(self.root, path, registry=self.assembly.registry, environment={})
        self.addAsyncCleanup(self.roles.aclose)
        before = component_path.read_bytes()
        self.settings['delegation']['workers'] = ['focused-reader']
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'a.txt'})
        def submit(view, signal=None):
            page = json.loads(view.messages[-1].text)
            self.assertEqual('obs', page['text'])
            return tool_response('submit_findings', {'summary': 'Only three characters were supplied.',
                'sources': [{'path': 'a.txt', 'citation_id': page['citation_id']}], 'unknowns': ['Rest unread.']})
        child.script.append(submit)
        self.create(child)
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect a limited source.',
            'worker': 'focused-reader', 'materials': ['a.txt']})
        self.parent.respond_text('Waiting')
        self.parent.respond_text('Integrated')
        await self.run_role()
        self.assertEqual('secondary-model', child.calls[0]['model'])
        self.assertIn('WORKER MARKER', child.calls[0]['system_prompt'])
        self.assertEqual({'read', 'submit_findings'}, set(child.calls[0]['tools']))
        self.assertEqual(3, self.workspace.access.supply_characters)
        exported = materialize_system(self.roles.profile, self.root / 'export/config.yaml',
            catalog=self.roles.catalog, model_source=model_path)
        restored = load_system_config(exported).select()
        selection = next(s for s in restored.mechanisms if s.mechanism_id == 'subagent')
        self.assertEqual(worker, selection.parameters['workers']['focused-reader'])
        self.assertEqual(before, component_path.read_bytes())

    async def test_worker_request_limit_stops_child_without_granting_unsubmitted_citations(self):
        from dataclasses import replace
        from copy import deepcopy
        worker = deepcopy(self.roles.catalog.get('subagent').descriptor.normalize_parameters({})['workers']['evidence-reader'])
        worker['limits']['model_requests'] = 1
        self.roles.profile = replace(self.roles.profile, mechanisms=tuple(
            replace(s, parameters={**s.parameters, 'workers': {'limited-reader': worker}})
            if s.mechanism_id == 'subagent' else s for s in self.roles.profile.mechanisms))
        self.settings['delegation']['workers'] = ['limited-reader']
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'a.txt'})
        child.respond_text('Must never be requested')
        self.create(child)
        self.parent.respond_tool_call('subagent_spawn', {'task': 'Inspect',
            'worker': 'limited-reader', 'materials': ['a.txt']})
        self.parent.respond_text('Waiting')
        self.parent.respond_text('Reading is incomplete')
        await self.run_role()
        self.assertEqual(1, len(child.calls))
        self.assertEqual(set(), self.workspace.eligible_ids)
        self.assertIn('model_request_limit', str([m.to_dict() for m in self.parent.calls[-1]['messages']]))

    async def test_unknown_worker_and_undeclared_model_role_are_rejected_offline(self):
        from dataclasses import replace
        from copy import deepcopy
        for role in ('subagent', 'unregistered-model-role'):
            worker = deepcopy(self.roles.catalog.get('subagent').descriptor.normalize_parameters({})['workers']['evidence-reader'])
            worker['model_role'] = role
            profile = self.roles.profile
            self.roles.profile = replace(profile, mechanisms=tuple(
                replace(s, parameters={**s.parameters, 'workers': {'custom': worker}})
                if s.mechanism_id == 'subagent' else s for s in profile.mechanisms))
            self.settings['delegation']['workers'] = ['missing'] if role == 'subagent' else ['custom']
            with self.subTest(role=role), self.assertRaises(ValueError):
                self.roles.runtime_factory('editor', self.root / 'roles', self.artifacts, self.settings)
            self.roles.profile = profile
        self.assertFalse(self.assembly.registry.create.called)

    def reader_with_sources(self):
        child = FauxProvider()
        child.respond_tool_call('read', {'path': 'a.txt'})
        def submit(view, signal=None):
            page = json.loads(view.messages[-1].text)
            return tool_response('submit_findings', {'summary': 'Retain this bounded observation.',
                'sources': [{'path': 'a.txt', 'citation_id': page['citation_id']}], 'unknowns': ['Cause unknown.']})
        child.script.append(submit)
        return child

    async def test_completed_parts_survive_parent_failure_and_reuse_with_added_material(self):
        from fruitfly_agent.run.storage.organization_parts import OrganizationPartStore
        from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace
        parts = OrganizationPartStore(self.root / 'parts', self.artifacts)
        self.settings['retention'] = {'enabled': True}
        child = self.reader_with_sources()
        self.create(child)
        self.parent_spawn(['a.txt'])
        self.parent.script.pop()
        self.parent.respond_fatal('Parent integration failed')
        with self.assertRaises(RuntimeError):
            await self.run_role(parts=parts)
        references = parts.entries()
        self.assertEqual(1, len(references))
        retained = parts.read(references[0])
        self.assertTrue(retained.reusable)
        self.workspace = EvidenceWorkspace(baseline=self.workspace.baseline,
            files={'a.txt': b'observed failure', 'new.txt': b'new material'}, writable_ids=())
        self.parent = FauxProvider()
        self.parent.respond_tool_call('catalog_parts', {})
        def read_retained(view, signal=None):
            catalog = json.loads(view.messages[-1].text)
            self.assertEqual(1, catalog['total'])
            return tool_response('read_part', {'part_id': catalog['parts'][0]['part_id']})
        self.parent.script.append(read_retained)
        self.parent.respond_text('Reused historical finding; new material remains uncovered.')
        self.assembly.registry.create.reset_mock()
        self.assembly.registry.create.side_effect = AssertionError('Reuse constructed a child Provider')
        response, _, events = await self.run_role(parts=parts)
        self.assertIn('Reused', response)
        self.assertFalse(self.assembly.registry.create.called)
        self.assertFalse(self.workspace.provided_paths.get('a.txt'))
        self.assertTrue(self.workspace.eligible_paths('a.txt'))
        self.assertEqual(retained.producer, self.workspace.retained_parts[references[0]]['producer'])
        self.assertEqual('reused', self.workspace.retained_parts[references[0]]['disposition'])
        self.assertTrue(any(event == 'organization-part-reused' for event, _ in events))

    async def test_retained_parts_invalidate_on_material_requirements_and_model_changes(self):
        from dataclasses import replace
        from unittest.mock import patch
        from fruitfly_agent.run.storage.organization_parts import OrganizationPartStore
        parts = OrganizationPartStore(self.root / 'parts', self.artifacts)
        self.settings['retention'] = {'enabled': True}
        self.create(self.reader_with_sources())
        self.parent_spawn(['a.txt'])
        await self.run_role(parts=parts)
        reference = parts.entries()[0]
        source = parts.read(reference).grant['a.txt']
        original = self.artifacts.read_bytes
        spec = self.roles.specs['offline']
        for change in ('material', 'requirements', 'model', 'missing-source'):
            self.parent = FauxProvider()
            self.parent.respond_tool_call('catalog_parts', {})
            def inspect(view, signal=None):
                data = json.loads(view.messages[-1].text)
                self.assertEqual(0, data['total'])
                self.assertEqual(1, data['unavailable_count'])
                async def events():
                    yield StreamDone(AssistantMessage([TextBlock('No applicable retained part')], 'stop'))
                return AssistantMessageEventStream(events())
            self.parent.script.append(inspect)
            self.workspace.files['a.txt'] = b'changed' if change == 'material' else b'observed failure'
            self.roles.specs['offline'] = replace(spec, model='different-model') if change == 'model' else spec
            def read(reference):
                if change == 'missing-source' and reference == source:
                    raise ValueError('source unavailable')
                return original(reference)
            with self.subTest(change=change), patch.object(self.artifacts, 'read_bytes', side_effect=read):
                await self.run_role(parts=parts, mission='Different requirements' if change == 'requirements' else 'Investigate')
        self.assertEqual(1, len(parts.entries()))
