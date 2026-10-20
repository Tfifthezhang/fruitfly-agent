"""Official exports retain whole task bytes and leave unavailable feedback unscored."""
import json
from pathlib import Path
import tempfile
import unittest

from eval.evidence import export_harbor_evidence, material_hash
from fruitfly_agent.lab.improvement.api import TaskRunEvidence


class EvidenceExportTests(unittest.TestCase):
    def export(self, root, reward=0, exception=None, resolver=None):
        task = root/'original'
        task.mkdir()
        (task/'tests').mkdir()
        (task/'instruction.md').write_text('Full repository task\n' + 'detail ' * 1000)
        (task/'task.toml').write_text('[environment]\ncpus = 1\nmemory_mb = 2048\n')
        (task/'tests/test.sh').write_text('#!/bin/sh\nexit 0\n')
        trial = root/'job/task__1'
        (trial/'agent').mkdir(parents=True)
        (trial/'verifier').mkdir()
        (trial/'verifier/stdout.txt').write_text('official diagnostic')
        (trial/'agent/session.jsonl').write_text(json.dumps({'type':'message','message':{'role':'assistant','content':[{'type':'text','text':'answer'}]}})+'\n')
        (trial/'result.json').write_text(json.dumps({'task_name':'task', 'config':{'task':{'git_commit_id':'fixed'}},
            'verifier_result':{'rewards':{'reward':reward}},'exception_info':exception}))
        return export_harbor_evidence(root/'job',dataset='data',output_directory=root/'evidence',material_resolver=resolver or (lambda _:task)),task

    def test_export_retains_exact_full_material_and_official_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); bundle,task=self.export(root)
            self.assertEqual(bundle['errors'],[])
            evidence=TaskRunEvidence.from_dict(bundle['runs'][0])
            self.assertEqual(evidence.score,0)
            self.assertEqual(evidence.status,'scored')
            self.assertIsNone(evidence.model_calls)
            self.assertIsNone(evidence.version)
            self.assertEqual(evidence.task.instruction,(task/'instruction.md').read_text())
            copied=root/'evidence'/bundle['materials'][evidence.task.reference_id]
            self.assertEqual(material_hash(copied),material_hash(task))
            self.assertEqual({a.kind for a in evidence.artifacts},{'trajectory','official-result','verifier-log'})
            (copied/'tests/test.sh').write_text('changed')
            self.assertNotEqual(material_hash(copied),evidence.task.material_hash)

    def test_boolean_missing_and_exception_rewards_are_not_learning_scores(self):
        for reward,exception,status in [(True,None,'unscored'),(None,None,'unscored'),(0,{'exception_type':'SetupError'},'error')]:
            with self.subTest(status=status),tempfile.TemporaryDirectory() as tmp:
                bundle,_=self.export(Path(tmp),reward,exception)
                row=bundle['runs'][0]
                self.assertEqual(row['status'],status)
                self.assertIsNone(row['score'])

    def test_material_resolver_failure_is_recorded_without_inventing_receipts(self):
        def unavailable(_):
            raise ValueError('task cache unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            bundle,_=self.export(Path(tmp),resolver=unavailable)
            self.assertEqual(bundle['runs'],[])
            self.assertEqual(bundle['errors'][0]['error'],'ValueError')

    def test_task_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'target').write_text('contents')
            (root/'link').symlink_to(root/'target')
            with self.assertRaisesRegex(ValueError,'symlink'):
                material_hash(root)
