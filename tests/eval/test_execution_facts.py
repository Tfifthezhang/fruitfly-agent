"""Benchmark fact conversion keeps collection failure and private grading separate."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest

from eval.improvement.evidence import collect
from eval.improvement.facts import attach_benchmark_facts
from fruitfly_agent.core.data_model import LoopDiagnostics
from fruitfly_agent.lab.improvement.api import ExecutionRecord, TaskMaterial, read_facts
from fruitfly_agent.lab.improvement.evidence import MemoryArtifacts
from tests.support.pipeline import fixture, version


class BenchmarkFactTests(unittest.TestCase):
    def test_new_diagnostics_are_authoritative_and_old_records_remain_unknown(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                agent = root / 'artifacts/harbor/job/trial/agent'; agent.mkdir(parents=True)
                end = {'kind': 'runRecord', 'event': 'end', 'data': {}}
                if not legacy:
                    end['data']['diagnostics'] = asdict(LoopDiagnostics('tool_budget_exhausted', 2, 0, 2, 1, 1, 0, 0, 1, 0, 1, 1, 32))
                (agent / 'session.jsonl').write_text(json.dumps(end) + '\n')
                (agent / 'model-budget.json').write_text('{"schema_version":1,"limit":200,"used":2}')
                artifact_root = agent.parent / 'artifacts'; artifact_root.mkdir()
                (artifact_root / 'manifest.json').write_text(json.dumps([
                    {'source': '/app/answer.py', 'status': 'failed'}]))
                verifier = agent.parent / 'verifier'; verifier.mkdir(); (verifier / 'answers.txt').write_text('PRIVATE')
                artifacts = MemoryArtifacts()
                resources, calls = collect(root, artifacts)
                _, harness = fixture(); task = TaskMaterial('task', 'A generic task.')
                record = ExecutionRecord('execution', task.task_id, task.material_id, harness.snapshot_id,
                    version().state, version().harness, 'completed', 'Execution finished.', resources, calls)
                result = attach_benchmark_facts(record, root, artifacts, model_limit=200)
                facts = read_facts(result, artifacts)
                self.assertEqual(facts.termination_reason, 'unknown' if legacy else 'tool_budget_exhausted')
                self.assertEqual(facts.complete, not legacy)
                self.assertEqual(facts.artifacts[0].status, 'collection_failed')
                self.assertEqual(facts.budgets[-1].used, 2)
                self.assertTrue(all(b'PRIVATE' not in artifacts.read(r.artifact_id) for r in result.artifacts))
