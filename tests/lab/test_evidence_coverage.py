"""Evidence completeness does not reuse execution diagnostic completeness."""
from dataclasses import replace
import json
import unittest
from fruitfly_agent.improvement.contracts.facts import UsageFact
from fruitfly_agent.improvement.contracts.tasks import Resource, TaskMaterial
from fruitfly_agent.improvement.execution.facts import attach_facts, receipt_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from fruitfly_agent.lab.improvement.evidence.indexing import organize_evidence, COVERAGE_PATH
from tests.support.stages import proposal_fixture, Runner


class EvidenceCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_required_parse_gap_or_missing_captured_bytes_prevents_complete(self):
        _, plan, baseline, _ = proposal_fixture()
        task = TaskMaterial('task', 'Inspect evidence')
        for defect in ('none', 'parse', 'missing-file', 'usage'):
            with self.subTest(defect=defect):
                artifacts = MemoryArtifacts()
                def resource(path, value, kind='diagnostic'):
                    return Resource(path, artifacts.put(json.dumps(value).encode()), 'application/json', kind)
                manifest = {'status': 'complete', 'files': []}
                if defect == 'missing-file':
                    manifest['files'] = [{'status': 'collected', 'path': 'answer', 'sha256': '0' * 64}]
                resources = [resource('agent/0/session.jsonl', {'message': {'role': 'assistant'}}, 'trajectory'),
                    resource('diagnostics/final-answer.json', {'state': 'final'}),
                    resource('diagnostics/capture-manifest.json', manifest)]
                if defect == 'parse':
                    resources.append(Resource('bad.jsonl', artifacts.put(b'{broken'), kind='trajectory'))
                record = await Runner().execute(plan, task, baseline)
                record = replace(record, artifacts=tuple(resources))
                facts = receipt_facts(record, artifacts, complete=True, usage=(
                    UsageFact('input_tokens', 'execution', None if defect == 'usage' else 10),
                    UsageFact('output_tokens', 'execution', 2)))
                record = organize_evidence(task, attach_facts(record, facts, artifacts), artifacts)
                value = json.loads(artifacts.read(next(r.artifact_id for r in record.artifacts if r.path == COVERAGE_PATH)))
                self.assertTrue(value['execution_diagnostics_complete'])
                self.assertEqual(value['evidence_complete'], defect == 'none')
