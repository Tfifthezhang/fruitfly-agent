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
