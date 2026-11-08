"""A valid empty owner option document still represents an explicit grant."""
import unittest
from fruitfly_agent.lab.catalog import builtin_catalog, load_system_config, edit_grants
from pathlib import Path


class ResearchGrantTests(unittest.TestCase):
    def test_text_grant_preserves_selected_component(self):
        catalog = builtin_catalog()
        profile = load_system_config(Path('examples/configuration/default-config.example.yaml'), catalog=catalog).select()
        options = edit_grants(profile, {'base_prompt': {'fields': ['parameters.instructions.system']}}, catalog)
        self.assertEqual(options, {'base_prompt': {'editable_fields': ['parameters.instructions.system']}})

    def test_batch_directory_stays_small_with_thousands_of_originals(self):
        from dataclasses import replace
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts, EvidenceWorkspace
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial, Resource
        from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
        from fruitfly_agent.improvement.contracts.research import ResearchBatch
        from fruitfly_agent.lab.improvement.stages.propose import proposal_request
        from tests.support.stages import proposal_fixture
        _, plan, baseline, _ = proposal_fixture()
        artifacts = MemoryArtifacts()
        reference = artifacts.put(b'original retained bytes')
        task = TaskMaterial('task', 'Read selected originals')
        resources = tuple(Resource('originals/' + str(i) + '.txt', reference) for i in range(5000))
        record = ExecutionRecord('run',task.task_id,task.material_id,baseline.snapshot_id,
            plan.parent.state,plan.conditions_id,'completed','Output',resources)
        request = proposal_request(ResearchBatch((task,),(record,)), plan, baseline)
        workspace = EvidenceWorkspace.build(request, artifacts)
        self.assertLess(len(workspace.read('INDEX.json')), 2000)
        self.assertGreater(len(workspace.paths()), 5000)
