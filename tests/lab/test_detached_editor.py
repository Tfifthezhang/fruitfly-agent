"""Public pipeline ports support unscored work and feedback-driven algorithms."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
import asyncio
import json
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from fruitfly_agent.improvement.contracts.plans import RunPlan
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.improvement.contracts.components import ComponentDocument, ComponentFile, HarnessSnapshot
from fruitfly_agent.improvement.contracts.candidates import CandidateBundle, EditReason
from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
from fruitfly_agent.improvement.contracts.assessment import Measurement, SelectionDecision
from fruitfly_agent.improvement.contracts.editing import ProposalResult
from fruitfly_agent.lab.improvement.components import ComponentRegistry, FileComponentAdapter
from fruitfly_agent.lab.improvement.editor.generators import GeneratorRegistry
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.assessment.selection import AgentSelector
from fruitfly_agent.lab.improvement.experience.reflection import AgentReflector
from fruitfly_agent.lab.improvement.materials import WorkspaceTaskSource
from fruitfly_agent.improvement.contracts.versions import SystemVersion, content_hash
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.faux_provider import FauxProvider


from tests.support.stages import version, fixture, RuleGenerator, proposal_fixture


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def build(self, **kwargs):
        return proposal_fixture(**kwargs)








    async def test_agent_edits_a_detached_workspace_using_public_tools(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        provider = FauxProvider()
        provider.respond_tool_call('describe_target', {'component_id': 'prompt'})
        provider.respond_tool_call('read', {'path': 'context/executions.json'})
        provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'New task procedure'})
        provider.respond_text('{"reasons":[{"component_id":"prompt","explanation":"Observed omission","expected_effect":"Perform the previously omitted inspection","evidence_ids":["reference"]}]}')
        plan = RunPlan('job', version(), ('prompt',))
        task = TaskMaterial('task', 'Inspect the source')
        record = ExecutionRecord('reference', task.task_id, task.material_id, baseline.snapshot_id,
                                 plan.parent.state, plan.conditions_id, 'completed', 'Missing inspection')
        from fruitfly_agent.improvement.contracts.editing import ProposalRequest
        request = ProposalRequest(plan, task, baseline, (record,), 'invariant', 0)
        services = StageServices(plan)
        editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, registry)
        candidate = await editor.edit('propose', request, services)
        self.assertEqual(candidate.changed_ids, ('prompt',))
        self.assertEqual(services.used['model'], 4)
        self.assertEqual(baseline.component('prompt').files[0].text, 'prompt')
        self.assertTrue(any(event == 'evidence-host-read' for event, _ in services.events))
        self.assertTrue(any(event == 'component-descriptions' and fields['artifact_id'] in artifacts.values
            for event, fields in services.events))
        descriptions = json.loads(json.loads(provider.calls[1]['messages'][-1].content[0].text)['text'])
        self.assertIn('parameters.content.documents', {f['path'] for f in descriptions['fields']})

    def test_workspace_paths_binary_sources_and_read_only_evidence(self):
        registry, baseline = fixture()
        artifacts = MemoryArtifacts()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'input.bin').write_bytes(b'\x00\xff')
            task = WorkspaceTaskSource(root, artifacts).freeze('task', 'Read binary source', paths=('input.bin',))
            self.assertEqual(artifacts.read(task.inputs[0].artifact_id), b'\x00\xff')
        workspace = EvidenceWorkspace(baseline=baseline, files={'context/task.md': b'task'}, writable_ids=('prompt',))
        for path in ('../escape', '/etc/passwd', 'context/task.md', 'harness/memory/instructions.txt'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                workspace.write(path, 'unexpected')
        self.assertEqual(workspace.read('context/task.md'), b'task')
        self.assertEqual(HarnessSnapshot.from_dict(baseline.to_dict()), baseline)



    def test_discovery_does_not_construct_generators_and_instances_are_job_local(self):
        constructed = []
        def create():
            value = RuleGenerator()
            constructed.append(value)
            return value
        registry = GeneratorRegistry()
        registry.register('rule-generator', create, label='Custom search')
        self.assertEqual(registry.definitions()[0].label, 'Custom search')
        self.assertEqual(constructed, [])
        self.assertIsNot(registry.create('rule-generator'), registry.create('rule-generator'))


