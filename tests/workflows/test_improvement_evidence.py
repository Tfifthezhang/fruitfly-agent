"""Real collection and organization reach both roles through one evidence reader."""
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.improvement.contracts.editing import ProposalRequest, TaskSetProposalRequest
from fruitfly_agent.improvement.contracts.task_sets import TaskEntry, TaskSetSnapshot, ScoreSpec
from fruitfly_agent.improvement.contracts.evaluation import EvaluationBatch, CandidateEvaluation, TrialResult, JointAssessment
from fruitfly_agent.improvement.stages.services import StageServices
from fruitfly_agent.improvement.contracts.tasks import TaskMaterial
from fruitfly_agent.lab.improvement.evidence import EvidenceWorkspace, MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.catalog import WorkspaceEvidence
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence
from fruitfly_agent.lab.improvement.assessment import ModelEvaluator
from fruitfly_eval.improvement.evidence import collect, answer_evidence
from fruitfly_eval.improvement.facts import attach_benchmark_facts
from tests.support.stages import proposal_fixture, Runner


class ImprovementEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_role_workspaces_read_registered_events_and_files_with_source_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text(json.dumps({'message': {'role': 'assistant', 'stopReason': 'stop',
                'content': [{'type': 'text', 'text': 'actual final response'}]}}) + '\n')
            (agent / 'events.jsonl').write_text('{"type":"run_finished"}\n')
            outputs = agent.parent / 'artifacts'; outputs.mkdir()
            (outputs / 'answer.txt').write_text('actual delivered bytes')
            artifacts = MemoryArtifacts(); task = TaskMaterial('task', 'Check output')
            _, plan, baseline, _ = proposal_fixture()
            resources, calls = collect(root, artifacts, evidence_paths={
                'artifacts/harbor/job/trial/artifacts/answer.txt': 'sha256:' + hashlib.sha256(b'actual delivered bytes').hexdigest()})
            record = await Runner().execute(plan, task, baseline)
            record = replace(record, artifacts=resources, model_calls=calls,
                output=answer_evidence(resources, artifacts)['text'])
            services = StageServices(plan)
            self.addAsyncCleanup(services.close)
            services.evidence_builder = organize_evidence
            record = services.prepare_evidence(task, attach_benchmark_facts(record, root, artifacts), artifacts)
            request = ProposalRequest(plan, task, baseline, (record,), 'task', 0)
            editor_workspace = EvidenceWorkspace.build(request, artifacts)
            prefix = 'context/executions/' + record.run_id + '/'
            original = prefix + 'originals/artifacts/harbor/job/trial/artifacts/answer.txt'
            editor = WorkspaceEvidence(editor_workspace)
            editor.catalog()
            self.assertEqual(editor_workspace.provided_ids, set())
            editor_page = editor.read(original)
            self.assertEqual(editor_page['text'], 'actual delivered bytes')
            self.assertIn(editor_page['citation_id'], editor_workspace.provided_ids)
            self.assertNotIn(editor_page['artifact_id'], editor_workspace.provided_ids)
            entry = TaskEntry('sample', 'benchmark', record.material_id, 'eval', task,
                              ScoreSpec('official'), 'source/sample')
            snapshot = TaskSetSnapshot((entry,))
            evaluation = CandidateEvaluation('batch', record.harness_id, record.conditions_id,
                EvaluationBatch(snapshot.snapshot_id, ('sample',)), (TrialResult('sample', 0, record, None),),
                JointAssessment(None, (), (), 1, 0, 'fixture'))
            joint = TaskSetProposalRequest(plan, snapshot.snapshot_id, (entry,), baseline, (evaluation,), 'task', 0)
            joint_workspace = EvidenceWorkspace.build(joint, artifacts)
            joint_path = 'context/tasks/sample/executions/' + record.run_id + '/originals/artifacts/harbor/job/trial/artifacts/answer.txt'
            self.assertEqual(WorkspaceEvidence(joint_workspace).read(joint_path)['artifact_id'], editor_page['artifact_id'])
            with self.assertRaises(ValueError):
                EvidenceWorkspace.build(replace(joint, tasks=(replace(entry, partition='confirmation'),)), artifacts)
            evaluator = ModelEvaluator(AgentLoopConfig(provider=None), artifacts)
            async def inspect(mission, workspace, services, **kwargs):
                self.assertFalse(kwargs['writable'])
                self.assertEqual(workspace.writable_ids, frozenset())
                reader = WorkspaceEvidence(workspace)
                self.assertIn(prefix + 'agent/0/reading-trajectory.jsonl', workspace.paths())
                page = reader.read(original)
                self.assertEqual(page['artifact_id'], editor_page['artifact_id'])
                with self.assertRaises(ValueError):
                    workspace.write(original, 'changed')
                citation = page['citation_id']
                response = json.dumps({'evaluations': [{'run_id': record.run_id, 'dimensions': [{
                    'dimension': 'output', 'criterion': 'retained content', 'judgment': 'met',
                    'reason': 'actual bytes read', 'uncertainty': 'no correctness oracle', 'evidence_ids': [citation]}],
                    'findings': []}], 'choice': None, 'reason': 'read retained output',
                    'uncertainty': 'correctness not established', 'evidence_ids': [citation]})
                kwargs['validate_final'](response)
                return response
            evaluator.session.session = inspect
            result, _ = await evaluator.evaluate(task, (record,), services)
            self.assertEqual(result['evaluations'][0]['run_id'], record.run_id)
