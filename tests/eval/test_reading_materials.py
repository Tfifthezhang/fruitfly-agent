"""Compact default imports preserve failure facts and explicit original identities."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_eval.improvement.evidence import collect, answer_evidence
from fruitfly_eval.improvement.history import import_history


class ReadingMaterialsTests(unittest.TestCase):
    def test_recorded_agent_time_reaches_facts_and_compact_batch_without_changing_outcome(self):
        from fruitfly_agent.improvement.execution.facts import read_facts
        from fruitfly_agent.lab.improvement.evidence.batch import batch_view
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/trial'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Finish'}}) + '\n')
            result = {'task_name': 'fixture', 'verifier_result': {'rewards': {'reward': 0}},
                'agent_execution': {'started_at': '2026-01-01T00:00:00Z', 'finished_at': '2026-01-01T00:00:42Z'}}
            path = trial / 'result.json'; path.write_text(json.dumps(result))
            before = path.read_bytes()
            artifacts = MemoryArtifacts(); batch = import_history(root, artifacts)
            record = batch.records[0]
            self.assertEqual(read_facts(record, artifacts).elapsed_seconds, 42.)
            row = batch_view(batch.tasks, batch.records, batch.observations, artifacts)['executions.json'][0]
            self.assertEqual(row['elapsed_seconds'], 42.)
            self.assertEqual(row['status'], 'completed')
            self.assertEqual(row['observations'][0]['official_status'], 'failed')
            self.assertIsNone(row['model_calls'])
            overview = next(r for r in record.artifacts if r.path == 'evidence/overview.json')
            self.assertEqual(json.loads(artifacts.read(overview.artifact_id))['elapsed_seconds'], 42.)
            self.assertEqual(path.read_bytes(), before)

    def test_default_has_one_projection_and_supplements_only_verified_permitted_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/trial'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            original = '\n'.join(json.dumps({'type': 'message', 'message': m}) for m in (
                {'role': 'user', 'content': 'Solve the task'},
                {'role': 'assistant', 'content': [{'type': 'thinking', 'thinking': 'PRIVATE REASONING'},
                    {'type': 'toolCall', 'id': 'call', 'name': 'bash', 'input': {'command': 'work'}}],
                 'providerState': {'copy': 'INTERNAL'}},
                {'role': 'toolResult', 'toolCallId': 'call', 'content': [{'type': 'text', 'text': 'x' * 10000}]},
                {'role': 'assistant', 'stopReason': 'stop', 'content': 'Done'}))
            (agent / 'session.jsonl').write_text(original)
            (agent / 'trajectory.json').write_text('{"steps":[]}')
            (agent / 'events.jsonl').write_text('{"delta":"duplicate"}')
            (trial / 'result.json').write_text('{"task_name":"fixture","verifier_result":{"rewards":{"reward":0}}}')
            outputs = trial / 'artifacts'; outputs.mkdir()
            for i in range(100):
                (outputs / f'{i}.txt').write_text('deliverable')
            private = trial / 'verifier'; private.mkdir(); (private / 'answer').write_text('PRIVATE ANSWER')
            artifacts = MemoryArtifacts()
            batch = import_history(root, artifacts)
            record = batch.records[0]
            self.assertEqual(batch.tasks[0].instruction, 'Solve the task')
            self.assertEqual(record.output, 'Done')
            self.assertEqual(len([r for r in record.artifacts if r.kind == 'trajectory']), 1)
            self.assertFalse(any(r.kind == 'deliverable' for r in record.artifacts))
            joined = b''.join(artifacts.read(r.artifact_id) for r in record.artifacts)
            for excluded in (b'PRIVATE REASONING', b'INTERNAL', b'PRIVATE ANSWER'):
                self.assertNotIn(excluded, joined)
            scope = json.loads(artifacts.read(next(r.artifact_id for r in record.artifacts if r.path == 'diagnostics/reading-scope.json')))
            self.assertEqual(len([v for v in scope['sources'] if v['kind'] == 'deliverable']), 100)
            trajectory = next(r for r in record.artifacts if r.kind == 'trajectory')
            rows = [json.loads(v) for v in artifacts.read(trajectory.artifact_id).decode().splitlines()]
            self.assertTrue(rows[2]['text_truncated'])
            body = rows[2]['message']['content'][0]
            resource = next(r for r in record.artifacts if r.path == body['body_path'])
            self.assertEqual(resource.artifact_id, body['body_artifact_id'])
            self.assertEqual(artifacts.read(resource.artifact_id), b'x' * 10000)
            self.assertEqual(json.loads(original[rows[2]['source']['start']:rows[2]['source']['end']])['message']['role'], 'toolResult')
            path = 'artifacts/harbor/job/trial/artifacts/0.txt'
            identity = 'sha256:' + hashlib.sha256(b'deliverable').hexdigest()
            retained, _ = collect(root, artifacts, interrupted=True, evidence_paths={path: identity})
            self.assertEqual(artifacts.read(next(r.artifact_id for r in retained if r.path == 'originals/' + path)), b'deliverable')
            (root / path).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                collect(root, artifacts, interrupted=True, evidence_paths={path: identity})
            for denied in ('artifacts/harbor/job/trial/verifier/answer', '../outside'):
                with self.subTest(path=denied), self.assertRaises(ValueError):
                    collect(root, artifacts, interrupted=True, evidence_paths={denied: identity})
            self.assertEqual((agent / 'session.jsonl').read_text(), original)

    def test_import_keeps_raw_reward_separate_from_official_error_and_termination_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/trial'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Inspect'}}) + '\n')
            (trial / 'result.json').write_text(json.dumps({'task_name': 'fixture',
                'exception_info': {'exception_type': 'AgentTimeoutError', 'exception_message': 'Interrupted'},
                'verifier_result': {'rewards': {'reward': 1.0}}}))
            artifacts = MemoryArtifacts()
            batch = import_history(root, artifacts)
            observation = next(o for o in batch.observations if o['name'] == 'official_reward')
            self.assertEqual(observation['value'], {'reward': 1.0})
            self.assertEqual(observation['official_status'], 'error')
            self.assertFalse(observation['eligible'])
            self.assertIsNone(observation['agent_elapsed_seconds'])
            record = batch.records[0]
            resource = next(r for r in record.artifacts if r.path == 'diagnostics/termination.json')
            self.assertEqual(json.loads(artifacts.read(resource.artifact_id))['source'], 'missing_terminal_diagnostics')

    def test_missing_and_torn_native_records_remain_explicit_without_invented_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text('{"message":{"role":"assistant","stopReason":"stop","content":"partial"}}\n{broken')
            artifacts = MemoryArtifacts()
            resources, calls = collect(root, artifacts, interrupted=True)
            self.assertIsNone(calls)
            self.assertEqual(answer_evidence(resources, artifacts)['state'], 'partial')
            (agent / 'session.jsonl').unlink()
            resources, calls = collect(root, artifacts, interrupted=True)
            self.assertEqual(answer_evidence(resources, artifacts)['state'], 'absent')
            scope = json.loads(artifacts.read(next(r.artifact_id for r in resources if r.path == 'diagnostics/reading-scope.json')))
            self.assertTrue(scope['gaps'])

    def test_native_receipts_and_timeout_reach_focused_organizer_workspace(self):
        from fruitfly_agent.core.data_model import Usage
        from fruitfly_agent.improvement.contracts.organization import OrganizationRequest
        from fruitfly_agent.lab.improvement.organizer.workspace import build_workspace
        from fruitfly_agent.lab.improvement.evidence_selection.methods.representative.algorithm import RepresentativeSelector
        from fruitfly_agent.lab.improvement.evidence_selection.configuration import SelectionSettings
        from fruitfly_agent.lab.improvement.evidence.batch import batch_view
        from fruitfly_agent.improvement.contracts.tasks import Resource
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trial = root / 'artifacts/harbor/job/trial'
            agent = trial / 'agent'; agent.mkdir(parents=True)
            (agent / 'session.jsonl').write_text(json.dumps({'message': {'role': 'user', 'content': 'Inspect'}}) + '\n')
            (agent / 'model-usage.json').write_text(json.dumps({'schema_version': 1, 'used': 1, 'requests': [
                {'id': 'a', 'usage': Usage(input_tokens=100, output_tokens=20).to_dict()}]}))
            result = trial / 'result.json'
            result.write_text(json.dumps({'task_name': 'fixture', 'exception_info': {'exception_type': 'AgentTimeoutError',
                'exception_message': 'Agent execution timed out after 900.0 seconds'}, 'verifier_result': {'rewards': {'reward': 1}}}))
            before = result.read_bytes()
            artifacts = MemoryArtifacts(); batch = import_history(root, artifacts)
            rows = batch_view(batch.tasks, batch.records, batch.observations, artifacts)['executions.json']
            usage = {v['resource']: v['used'] for v in rows[0]['usage']}
            self.assertEqual(usage['input_tokens'], 100)
            self.assertEqual(rows[0]['observations'][0]['error']['timeout_seconds'], 900.)
            selection = RepresentativeSelector(SelectionSettings()).select(rows, resources={r.run_id: r.artifacts for r in batch.records})
            context = tuple(Resource(name, artifacts.put(json.dumps(value).encode()), 'application/json', 'diagnostic')
                for name, value in [('observations.json', batch.observations), ('selection.json', selection)])
            workspace, _ = build_workspace(OrganizationRequest(batch.tasks, batch.records, context=context), artifacts)
            path = 'context/executions/' + batch.records[0].run_id + '/diagnostics/outcome.json'
            self.assertIn(path, workspace.paths())
            public = json.loads(workspace.read(path))
            self.assertEqual(public['error']['timeout_seconds'], 900.)
            self.assertFalse(public['eligible'])
            self.assertEqual(result.read_bytes(), before)
