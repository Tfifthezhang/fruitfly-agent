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
from fruitfly_agent.improvement.contracts.requests import WorkflowRequest
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.improvement.api import StageBindings
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.stages.services import StageServices
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
from tests.support.stages import version






class ExecutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_discovery_selects_tool_parameters_by_default_and_allows_explicit_scope(self):
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
                improvement_bindings=StageBindings(runner=runner))
            app = AgentApplication(factory)
            await app.start()
            try:
                available = app.workflow_configuration()
                self.assertTrue(next(c for c in available.components if c.component_id == 'bash-tool').available)
                default = factory._execution_host.preview(WorkflowRequest('Inspect the task.'))
                default_ids = dict(default.details)['Components'].split(', ')
                self.assertIn('bash-tool', default_ids)
                self.assertNotIn('tool-catalog', default_ids)
                explicit = factory._execution_host.preview(WorkflowRequest('Inspect the task.', component_ids=('bash-tool',)))
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
        services = StageServices(plan)
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
                    factory._execution_host.preview(WorkflowRequest('Work.', component_ids=('execution-policy',)))
                self.assertEqual(providers.create.return_value.calls, [])
            finally: await app.close()

    async def test_trial_removes_count_caps_and_records_fixed_execution_settings(self):
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path':'a', 'content':'a'})
        provider.respond_tool_call('write', {'path':'b', 'content':'b'})
        provider.respond_text('done')
        config = AgentLoopConfig(provider, max_tool_calls_per_turn=1)
        components = ComponentRegistry((TextComponentAdapter(BasePromptTarget('base'),'system-prompt'),))
        artifacts=MemoryArtifacts();plan=RunPlan('trial',version(),('base_prompt',));services=StageServices(plan)
        try:
            record=await TaskRunnerFixture(config,components,artifacts,services).execute(plan,TaskMaterial('task','Write two files'),components.snapshot())
            self.assertEqual(dict(read_facts(record,artifacts).counters)['tool_started'],2)
            ref=next(r.artifact_id for r in record.artifacts if r.path=='runtime-execution.json')
            self.assertIsNone(json.loads(artifacts.read(ref))['max_tool_calls_per_turn'])
            self.assertEqual(config.max_tool_calls_per_turn,1)
        finally:await services.close()
