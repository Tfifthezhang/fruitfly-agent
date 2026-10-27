"""Configuration candidates execute in isolation and adopt as exact H-only versions."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.execution_policy import ExecutionPolicyTarget
from fruitfly_agent.lab.improvement.api import (WorkflowBindings, GeneratorRegistry, CandidateBundle,
    HarnessSnapshot, ComponentFile, EditReason, ProposalResult, ComponentRegistry, TextComponentAdapter,
    FileTaskRunner, WorkflowServices, RunPlan, TaskMaterial, read_facts)
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.run import RunApplicationFactory
from tests.support.faux_provider import FauxProvider
from tests.support.improvers import OfflineRunner, FirstSelector, SyntheticVerification
from tests.support.materials import _write_models
from tests.support.pipeline import version


class PolicyGenerator:
    generator_id = 'policy-rule'
    required_capabilities = frozenset()

    async def propose(self, request, services):
        document = request.baseline.component('execution-policy')
        values = json.loads(document.files[0].text)
        values['max_tool_calls_per_turn'] = 128
        changed = replace(document, files=(ComponentFile('instructions.txt', json.dumps(values)),))
        candidate = HarnessSnapshot(tuple(changed if c.component_id == changed.component_id else c
            for c in request.baseline.components))
        return ProposalResult((CandidateBundle(request.plan.parent, request.baseline, candidate,
            self.generator_id, (EditReason('execution-policy', 'Synthetic parameter comparison.',
                (request.records[0].run_id,)),)),))


class PolicyRunner(OfflineRunner):
    capabilities = OfflineRunner.capabilities | {'execution-config'}


class ExecutionPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_detached_execution_keeps_state_for_tools_but_excludes_it_from_editor_trajectory(self):
        from fruitfly_agent.core.data_model import AssistantMessage, TextBlock
        provider = FauxProvider()
        provider.respond(AssistantMessage([TextBlock('working')], stop_reason='stop',
            provider_state={'opaque': 'private-continuation'}, continue_turn=True))
        provider.respond_text('finished')
        config = AgentLoopConfig(provider=provider)
        components = ComponentRegistry((TextComponentAdapter(ExecutionPolicyTarget(config), 'execution-policy'),))
        artifacts = MemoryArtifacts()
        plan = RunPlan('continuation-trial', version(), ('execution-policy',))
        services = WorkflowServices(plan)
        try:
            record = await FileTaskRunner(config, components, artifacts, services).execute(plan,
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
    async def test_verified_configuration_candidate_activates_and_changes_only_h(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_models(root)
            provider = FauxProvider()
            providers = Mock(); providers.create.return_value = provider
            generators = GeneratorRegistry(); generators.register('policy-rule', PolicyGenerator)
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=providers,
                improvement_bindings=WorkflowBindings(generators=generators, runner=lambda *args: PolicyRunner(),
                    selector=lambda *args: FirstSelector(), verifier=SyntheticVerification(),
                    component_options={'execution-policy': {'editable_fields': ['max_tool_calls_per_turn'],
                        'bounds': {'max_tool_calls_per_turn': {'minimum': 32, 'maximum': 256}}}}))
            factory.configuration.save(); factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                before = factory.system_version()
                request = WorkflowRequest('Synthetic task.', component_ids=('execution-policy',),
                    generator_id='policy-rule', strategy_id='simple', depth=1, scope='persistent', retain_experience=False)
                preview = app.workflow_preview(request)
                candidates = await app.improve('', preview_token=preview.preview_token)
                self.assertEqual(len(candidates), 1)
                self.assertEqual(factory.system_version(), before)
                self.assertEqual(app.runtime_manifest['execution']['max_tool_calls_per_turn'], 64)
                await app.adopt_candidate(candidates[0].candidate_id)
                after = factory.system_version()
                self.assertNotEqual(after.harness, before.harness)
                self.assertEqual(after.improver, before.improver)
                self.assertEqual(after.state, before.state)
                self.assertEqual(app.runtime_manifest['execution']['max_tool_calls_per_turn'], 128)
                self.assertEqual(factory.configuration.profile().execution['max_tool_calls_per_turn'], 128)
                self.assertEqual(provider.calls, [])
            finally:
                await app.close()

    async def test_detached_execution_applies_candidate_policy_and_records_effective_values(self):
        provider = FauxProvider()
        provider.respond_tool_call('write', {'path': 'a', 'content': 'a'})
        provider.respond_tool_call('write', {'path': 'b', 'content': 'b'})
        config = AgentLoopConfig(provider=provider, max_tool_calls_per_turn=256)
        components = ComponentRegistry((TextComponentAdapter(ExecutionPolicyTarget(config), 'execution-policy'),))
        baseline = components.snapshot()
        document = baseline.component('execution-policy')
        values = json.loads(document.files[0].text); values['max_tool_calls_per_turn'] = 1
        candidate = HarnessSnapshot((replace(document, files=(ComponentFile('instructions.txt', json.dumps(values)),)),))
        artifacts = MemoryArtifacts()
        plan = RunPlan('policy-trial', version(), ('execution-policy',))
        services = WorkflowServices(plan)
        try:
            result = await FileTaskRunner(config, components, artifacts, services).execute(plan,
                TaskMaterial('task', 'Write two files.'), candidate)
            self.assertEqual(dict(read_facts(result, artifacts).counters)['tool_started'], 1)
            reference = next(r.artifact_id for r in result.artifacts if r.path == 'runtime-execution.json')
            self.assertEqual(json.loads(artifacts.read(reference))['max_tool_calls_per_turn'], 1)
            self.assertEqual(config.max_tool_calls_per_turn, 256)
        finally:
            await services.close()
