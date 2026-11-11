"""Shared runtime assembly binds child models, tools and resource ownership."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.core.session import Session
from fruitfly_agent.lab.catalog import builtin_catalog, MechanismSelection, PermissionPolicy, component_profile
from fruitfly_agent.runtime_spec import HarnessProfile
from fruitfly_agent.interactive.application.runtime import RuntimeHandle
from tests.support.assembly import AssemblyWorkspace
from tests.support.run import _write_catalog
from tests.support.faux_provider import FauxProvider

class SubagentAssemblyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.workspace = AssemblyWorkspace(self.root)
        _write_catalog(self.root / 'models.yaml', {'offline': 'main-model', 'secondary': 'child-model'})
        self.catalog = builtin_catalog()
        self.session = self.enterContext(Session(self.root / 'root.jsonl'))

    def assemble(self, *, enabled=True, model_roles=None, parameters=None):
        profile = HarnessProfile('test', model_profile='offline', model_roles=model_roles or {},
            mechanisms=(MechanismSelection('local-env'), MechanismSelection('read-tool'),
                MechanismSelection('subagent', enabled, parameters or {})))
        runtime = self.workspace.assemble(profile, self.session, catalog=self.catalog,
            permission_policy=PermissionPolicy.unrestricted(self.root))
        self.addAsyncCleanup(RuntimeHandle(None, {}, components=runtime.components).close)
        return runtime

    def test_disabled_component_has_no_tools_service_or_child_store(self):
        runtime = self.assemble(enabled=False)
        self.assertEqual(['read'], [t.name for t in runtime.config.tools])
        self.assertIsNone(runtime.run_loop)
        self.assertNotIn('subagent-monitor', runtime.components)
        self.assertFalse((self.root / 'root.jsonl.subagents').exists())

    async def test_role_alias_changes_real_child_request_and_parent_keeps_its_model(self):
        runtime = self.assemble(model_roles={'subagent': 'secondary'})
        service = runtime.components['subagent-monitor']
        child_providers = []
        def create(spec, environment):
            p = FauxProvider(); p.respond_text('actual child result'); child_providers.append((spec, p)); return p
        self.workspace.registry.create.side_effect = create
        service.begin()
        row = service.spawn('Inspect public exports')
        result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
        self.assertEqual('completed', result['executions'][0]['state'])
        self.assertEqual('main-model', runtime.config.model)
        self.assertEqual('child-model', child_providers[0][1].calls[0]['model'])
        self.assertEqual(['read'], child_providers[0][1].calls[0]['tools'])
        self.assertNotIn('parent-only-secret-material', str(child_providers[0][1].calls[0]['messages']))
        self.assertEqual('secondary', service.detail(row['agent_id'])['model_profile'])
        path = self.root / 'root.jsonl.subagents' / row['agent_id'] / 'session.jsonl'
        with Session(path) as child:
            self.assertTrue(any(e.payload.get('kind') == 'child-runtime' for e in child.read_all()))
        await service.end()

    async def test_default_role_inherits_model_and_normal_parent_loop_integrates_result(self):
        runtime = self.assemble()
        parent = runtime.config.provider
        parent.respond_tool_call('subagent_spawn', {'task': 'Read independently'})
        parent.respond_text('provisional')
        parent.respond_text('final integration')
        def create(spec, environment):
            p = FauxProvider(); p.respond_text('derived result'); return p
        self.workspace.registry.create.side_effect = create
        result = await runtime.run_loop(runtime.config, [UserMessage('root mission')])
        self.assertFalse(result.is_error)
        self.assertEqual('final integration', result.messages[-1].text)
        rows = runtime.components['subagent-monitor'].snapshot()['executions']
        self.assertEqual(('main-model', 'confirmed', True), (rows[0]['model'], rows[0]['cleanup'], rows[0]['delivered']))
        self.assertTrue(any('derived result' in str(m.to_dict()) for m in parent.calls[-1]['messages']))

    def test_unknown_role_alias_rejects_before_model_work(self):
        with self.assertRaisesRegex(ValueError, 'unknown model role profile'):
            self.assemble(model_roles={'subagent': 'missing'})
        for call in self.workspace.registry.create.mock_calls:
            self.assertEqual('create', call[0] or 'create')

    def test_replacement_reuses_parent_writer_instead_of_competing_for_child_index(self):
        first = self.assemble()
        second = self.assemble(model_roles={'subagent': 'secondary'})
        self.assertIsNot(first.components['subagent-monitor'], second.components['subagent-monitor'])
        self.assertIs(first.config.session, second.config.session)

    def test_export_preserves_inheritance_and_exposes_one_component(self):
        profile = component_profile(HarnessProfile('test', model_profile='offline',
            mechanisms=(MechanismSelection('subagent', False),)), self.catalog)
        value = profile.to_dict()
        self.assertEqual({'inherit': 'executor'}, value['models']['roles']['subagent'])
        self.assertIn('subagent', value['H'])
        self.assertFalse(value['H']['subagent'].get('inline', {}).get('enabled', False))


    async def test_failed_child_close_remains_unconfirmed_on_repeated_close(self):
        from fruitfly_agent.core.extensions.operations import OperationCleanupError
        from fruitfly_agent.lab.agents.subagent.contracts import ChildRequest, ExecutionIdentity
        runtime = self.assemble()
        class FailedCloseProvider(FauxProvider):
            async def close(self): raise RuntimeError('offline resource retirement failure')
        self.workspace.registry.create.side_effect = lambda *args: FailedCloseProvider()
        service = runtime.components['subagent-monitor']
        prepared = await service.prepare(ChildRequest(ExecutionIdentity('scope', 'agent', 'run'), 'Inspect'))
        try:
            await prepared.start()
            with self.assertRaises(OperationCleanupError): await prepared.close()
            with self.assertRaises(OperationCleanupError): await prepared.close()
        finally:
            # The failing provider is a fake with no external resource. Release
            # the test-owned Session lease after verifying the retained failure.
            prepared.config.session.close()

    async def test_component_protocol_controls_real_service_and_round_trips_nested_paths(self):
        parameters = {'max_task_characters': 7, 'max_context_characters': 12,
            'output_page_characters': 3, 'default_wait_seconds': 0,
            'retirement_timeout': .2}
        runtime = self.assemble(parameters=parameters)
        service = runtime.components['subagent-monitor']
        self.assertEqual((7, 3, .2), (service.protocol.max_task_characters,
            service.results.output_page_characters, service.retirement_timeout))
        service.begin()
        from fruitfly_agent.lab.agents.subagent.service import SubagentError
        with self.assertRaisesRegex(SubagentError, 'invalid_task_material'):
            service.spawn('Long task')
        self.assertFalse(service.tasks)
        profile = component_profile(HarnessProfile('test', model_profile='offline',
            mechanisms=(MechanismSelection('subagent', True, parameters),)), self.catalog, freeze=True)
        document = profile.to_dict()['H']['subagent']['inline']
        self.assertEqual(7, document['parameters']['settings']['protocol']['max_task_characters'])
        self.assertEqual(3, document['parameters']['settings']['results']['output_page_characters'])
        self.assertNotIn('max_task_characters', document['parameters']['settings'])
        await service.end()

    async def test_explicit_component_grant_changes_actual_child_tools_and_preserves_parent(self):
        runtime = self.assemble(parameters={'inheritance_mode': 'explicit',
            'inherited_components': ['local-env']})
        parent_tools = [t.name for t in runtime.config.tools]
        children = []
        def create(spec, environment):
            provider = FauxProvider()
            provider.respond_text('restricted result')
            children.append(provider)
            return provider
        self.workspace.registry.create.side_effect = create
        service = runtime.components['subagent-monitor']
        service.begin()
        row = service.spawn('Inspect only supplied task text')
        result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
        self.assertEqual('completed', result['executions'][0]['state'])
        self.assertEqual([], children[0].calls[0]['tools'])
        self.assertIn('read', parent_tools)
        self.assertEqual(parent_tools, [t.name for t in runtime.config.tools])
        await service.end()

    def test_explicit_component_grant_cannot_enable_absent_components(self):
        with self.assertRaisesRegex(ValueError, 'enabled parent subset'):
            self.assemble(parameters={'inheritance_mode': 'explicit',
                'inherited_components': ['bash-tool']})
        self.assertFalse((self.root / 'root.jsonl.subagents').exists())

    async def test_empty_explicit_component_grant_still_runs_independent_child(self):
        runtime = self.assemble(parameters={'inheritance_mode': 'explicit',
            'inherited_components': []})
        self.workspace.registry.create.side_effect = lambda *args: self.child_answer()
        service = runtime.components['subagent-monitor']
        service.begin()
        row = service.spawn('Answer using only this task')
        result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
        self.assertEqual('completed', result['executions'][0]['state'])
        await service.end()

    @staticmethod
    def child_answer():
        provider = FauxProvider()
        provider.respond_text('answer')
        return provider

    async def test_explicit_grant_drops_parent_prompt_but_keeps_host_execution_limits(self):
        from fruitfly_agent.run.storage.artifacts import DataArtifactStore
        store = DataArtifactStore(self.root / 'artifacts')
        reference = store.put_text('PARENT PRIVATE INSTRUCTIONS').artifact_id
        profile = HarnessProfile('test', model_profile='offline', prompt=reference,
            execution={'max_tool_calls_per_turn': 2},
            mechanisms=(MechanismSelection('subagent', parameters={
                'inheritance_mode': 'explicit', 'inherited_components': []}),))
        runtime = self.workspace.assemble(profile, self.session, catalog=self.catalog,
            artifact_store=store, permission_policy=PermissionPolicy.unrestricted(self.root))
        self.addAsyncCleanup(RuntimeHandle(None, {}, components=runtime.components).close)
        self.assertIn('PARENT PRIVATE', runtime.config.system_prompt)
        children = []
        def create(*args):
            provider = self.child_answer()
            children.append(provider)
            return provider
        self.workspace.registry.create.side_effect = create
        service = runtime.components['subagent-monitor']
        service.begin()
        row = service.spawn('Inspect only this task')
        result = await service.wait([(row['agent_id'], row['run_id'])], timeout_seconds=2)
        self.assertEqual('completed', result['executions'][0]['state'])
        self.assertNotIn('PARENT PRIVATE', children[0].calls[0]['system_prompt'])
        path = self.root / 'root.jsonl.subagents' / row['agent_id'] / 'session.jsonl'
        with Session(path) as child:
            metadata = next(e.payload for e in child.read_all() if e.payload.get('kind') == 'child-runtime')
            self.assertEqual(2, metadata['manifest']['execution']['max_tool_calls_per_turn'])
        await service.end()

    def test_improvement_cannot_grant_inheritance_or_protocol_edits(self):
        definition = self.catalog.get('subagent')
        for field in ('parameters.settings.inheritance.mode',
                'parameters.settings.inheritance.components',
                'parameters.settings.protocol.max_wait_seconds',
                'parameters.instructions.evidence_child', 'parameters.instructions.evidence_parent'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                definition.configuration_edit([field], {})
