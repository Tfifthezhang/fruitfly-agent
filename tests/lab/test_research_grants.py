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

    def test_batch_view_separates_status_reward_and_unknown_diagnostics(self):
        from fruitfly_agent.lab.improvement.evidence.batch import batch_view
        from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
        from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
        from fruitfly_agent.improvement.contracts.execution import ExecutionRecord
        from tests.support.stages import proposal_fixture
        _, plan, baseline, _ = proposal_fixture()
        task = TaskMaterial('task', 'Inspect facts')
        records = tuple(ExecutionRecord('run-' + str(i), task.task_id, task.material_id,
            baseline.snapshot_id, plan.parent.state, plan.conditions_id, status, '')
            for i, status in enumerate(('error', 'completed', 'completed')))
        observations = ({'run_id': 'run-0', 'name': 'official_reward', 'value': {'reward': 1.0}},
            {'run_id': 'run-1', 'name': 'official_reward', 'value': {'reward': 0.0}})
        views = batch_view((task,), records, observations, MemoryArtifacts())
        rows = views['executions.json']
        self.assertEqual(views['overview.json']['execution_status_counts'], {'error': 1, 'completed': 2})
        self.assertEqual(rows[0]['observations'][0]['value'], {'reward': 1.0})
        self.assertEqual(rows[0]['termination_reason'], 'unknown')
        self.assertIsNone(rows[0]['elapsed_seconds'])
        self.assertEqual(rows[2]['observation_supply'], 'not_supplied')
        self.assertEqual(views['coverage.json']['original_reading'], 'not_established')
