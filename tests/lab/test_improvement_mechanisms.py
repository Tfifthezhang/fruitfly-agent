"""Improvement mechanisms behavior and failure contracts."""
from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.execution import ExecutionContext
from fruitfly_agent.improvement.contracts.editing import ProposalRequest
from fruitfly_agent.lab.improvement.editor import AgentEditor
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
from fruitfly_agent.lab.improvement.evidence.access import EvidenceAccess
from fruitfly_agent.lab.improvement.evidence.rounds import RoundIndex
from fruitfly_agent.lab.improvement.evidence.configuration import EvidenceSettings
from fruitfly_agent.core.config import AgentLoopConfig
from tests.support.stages import proposal_fixture, RuleGenerator
from tests.support.faux_provider import FauxProvider


class KernelTests(unittest.IsolatedAsyncioTestCase):




    async def test_missing_evidence_cannot_justify_changed_candidate_or_forge_supply(self):
        flow, plan, baseline, runner = proposal_fixture()
        task = TaskMaterial('task', 'Work')
        record = await runner.execute(plan, task, baseline)
        artifacts, provider = MemoryArtifacts(), FauxProvider()
        for _ in range(2):
            provider.respond_tool_call('read', {'path': 'context/executions/' + record.run_id + '/missing.log'})
            provider.respond_tool_call('write_file', {'path': 'harness/prompt/instructions.txt', 'content': 'unsupported edit'})
            provider.respond_text(json.dumps({'reasons': [{'component_id': 'prompt', 'explanation': 'Unseen evidence', 'evidence_ids': [record.run_id], 'expected_effect':'The proposed behavior appears in the subsequent execution.'}]}))
        services = StageServices(plan)
        try:
            editor = AgentEditor(AgentLoopConfig(provider=provider), artifacts, flow.components)
            with self.assertRaises(RuntimeError):
                await editor.edit('propose', ProposalRequest(plan, task, baseline, (record,), 'invariant', 0), services)
            self.assertTrue(any(e == 'editor-evidence-unavailable' for e, _ in services.events))
            access = EvidenceAccess((record.run_id,))
            access.provided('harness/prompt/fake.json', '{"run_id":"' + record.run_id + '"}')
            self.assertEqual(access.supplied, set())
        finally:
            await services.close()

    def test_fixed_evidence_settings_reject_unknown_and_invalid_limits(self):
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'research': {}})
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'read': {'default_characters': 25000}})
        with self.assertRaises(ValueError): EvidenceSettings.from_dict({'search': {'max_matches': True}})
