"""Configuration candidates execute in isolation and adopt as exact H-only versions."""
from tests.support.configuration import component_parameters, with_component_parameters, with_component_text, parameter_payload
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.api import WorkflowBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.workflow.services import WorkflowServices
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.components import HarnessSnapshot, ComponentFile
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.components import ComponentRegistry, TextComponentAdapter
from tests.support.task_execution import TaskRunnerFixture
from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.execution.facts import read_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.task_execution import TaskApplicationFixture as RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.improvers import OfflineRunner, FirstSelector, SyntheticVerification
from tests.support.materials import _write_models
from tests.support.pipeline import version






class ExecutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_discovery_keeps_tool_parameters_available_for_explicit_requests_only(self):
        class Runner(OfflineRunner):
            capabilities = OfflineRunner.capabilities | {'tool:bash', 'configuration-materialization'}
        def runner(*args):
            return Runner()
        runner.capabilities = Runner.capabilities
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            providers = Mock()
            providers.create.return_value = FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(runner=runner))
            app = AgentApplication(factory)
            await app.start()
            try:
                available = app.workflow_configuration()
                self.assertTrue(next(c for c in available.components if c.component_id == 'bash-tool').available)
                default = app.workflow_preview(WorkflowRequest('Inspect the task.'))
                default_ids = dict(default.details)['Components'].split(', ')
                self.assertNotIn('bash-tool', default_ids)
                self.assertIn('tool-catalog', default_ids)
                explicit = app.workflow_preview(WorkflowRequest('Inspect the task.', component_ids=('bash-tool',)))
                self.assertEqual(dict(explicit.details)['Components'], 'bash-tool')
                self.assertEqual(providers.create.return_value.calls, [])
            finally:
                await app.close()

    async def test_detached_execution_keeps_state_for_tools_but_excludes_it_from_editor_trajectory(self):
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
        provider = FauxProvider()
        provider.respond(AssistantMessage([TextBlock('working')], stop_reason='stop',
            provider_state={'opaque': 'private-continuation'}, continue_turn=True))
        provider.respond_text('finished')
        config = AgentLoopConfig(provider=provider)
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget(config.system_prompt or 'base'), 'system-prompt'),))
        artifacts = MemoryArtifacts()
        plan = RunPlan('continuation-trial', version(), ('base_prompt',))
        services = WorkflowServices(plan)
        try:
            record = await TaskRunnerFixture(config, components, artifacts, services).execute(plan,
                TaskMaterial('task', 'Finish.'), components.snapshot())
            self.assertEqual(record.status, 'completed')
            self.assertEqual(record.output, 'finished')
            self.assertEqual(len(provider.calls), 2)
            self.assertEqual(services.used['model'], 2)
            self.assertEqual(provider.calls[1]['messages'][1].provider_state, {'opaque': 'private-continuation'})
            resource = next(r for r in record.artifacts if r.path == 'trajectory.json')
            self.assertNotIn(b'private-continuation', artifacts.read(resource.artifact_id))
        finally:
            await services.close()
    async def test_execution_policy_is_absent_from_runtime_optimization_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _write_models(root)
            providers = Mock(); providers.create.return_value = FauxProvider()
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers)
            app = AgentApplication(factory); await app.start()
            try:
                self.assertNotIn('execution-policy', {c.component_id for c in app.workflow_configuration().components})
                with self.assertRaises(ValueError):
                    app.workflow_preview(WorkflowRequest('Work.', component_ids=('execution-policy',)))
                self.assertEqual(providers.create.return_value.calls, [])
            finally: await app.close()

    async def test_trial_removes_count_caps_and_records_fixed_execution_settings(self):
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path':'a', 'content':'a'})
        provider.respond_tool_call('write', {'path':'b', 'content':'b'})
        provider.respond_text('done')
        config = AgentLoopConfig(provider, max_tool_calls_per_turn=1)
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'),'system-prompt'),))
        artifacts=MemoryArtifacts();plan=RunPlan('trial',version(),('base_prompt',));services=WorkflowServices(plan)
        try:
            record=await TaskRunnerFixture(config,components,artifacts,services).execute(plan,TaskMaterial('task','Write two files'),components.snapshot())
            self.assertEqual(dict(read_facts(record,artifacts).counters)['tool_started'],2)
            ref=next(r.artifact_id for r in record.artifacts if r.path=='runtime-execution.json')
            self.assertIsNone(json.loads(artifacts.read(ref))['max_tool_calls_per_turn'])
            self.assertEqual(config.max_tool_calls_per_turn,1)
        finally:await services.close()

    async def test_parameter_candidate_activates_with_exact_recorded_h_identity(self):
        class Generator:
            generator_id = 'parameter-rule'
            required_capabilities = frozenset()
            async def propose(self, request, services):
                document = request.baseline.component('bash-tool')
                value = component_parameters(document); value['settings']['default_timeout_seconds'] = 17
                changed = with_component_parameters(document, value)
                harness = HarnessSnapshot(tuple(changed if c.component_id == changed.component_id else c
                    for c in request.baseline.components))
                return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, harness, self.generator_id,
                    (EditReason('bash-tool', 'Synthetic timeout comparison.', (request.records[0].run_id,), expected_effect='The proposed behavior appears in the subsequent execution.'),)),))
        class ParameterRunner(OfflineRunner):
            capabilities = OfflineRunner.capabilities | {'configuration-materialization', 'tool:bash'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _write_models(root)
            providers = Mock(); providers.create.return_value = FauxProvider()
            generators = GeneratorRegistry(); generators.register('parameter-rule', Generator)
            def runner(*args): return ParameterRunner()
            runner.capabilities = ParameterRunner.capabilities
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators, runner=runner,
                    selector=lambda *args: FirstSelector(), verifier=SyntheticVerification(),
                    component_options={'bash-tool': {'editable_fields': ['parameters.settings.default_timeout_seconds'],
                        'bounds': {'parameters.settings.default_timeout_seconds': {'minimum': 1, 'maximum': 1200}}}}))
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory); await app.start()
            try:
                before = factory.system_version()
                request = WorkflowRequest('Synthetic task.', component_ids=('bash-tool',), generator_id='parameter-rule',
                     rounds=1, scope='persistent', retain_experience=False)
                preview = app.workflow_preview(request)
                candidates = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(factory.system_version(), before)
                await app.adopt_candidate(candidates[0].candidate_id)
                after = factory.system_version()
                self.assertNotEqual(after.harness, before.harness)
                self.assertEqual((after.improver, after.state), (before.improver, before.state))
                component = next(c for c in app.runtime_manifest['components'] if c['id'] == 'bash-tool')
                self.assertEqual(component['parameters']['default_timeout_seconds'], 17)
                self.assertTrue(all('Evaluate granted evidence'in c['system_prompt']for c in providers.create.return_value.calls))
            finally: await app.close()
