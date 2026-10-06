"""V2 file boundaries, migration, offline validation and atomic training edits."""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fruitfly_agent.lab.optimization.task_packs import TaskPackCatalog, load_pack
from fruitfly_agent.lab.optimization.verification import main, migrate_pack, score_answer
from tests.support.task_packs import install, package
from tests.support.task_packs import coding_pack


class UnifiedPackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = install(self.root)
        self.catalog = TaskPackCatalog(self.root)

    def test_declared_files_and_total_bytes_are_bounded(self):
        manifest = json.loads(self.path.read_text())
        for filename in ('../other.json', '/tmp/other.json', 'pack.json', 'references.json'):
            invalid = {**manifest, 'files': {'cases': filename}}
            self.path.write_text(json.dumps(invalid))
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                load_pack(self.root, self.path)
        install(self.root)
        cases = self.path.parent / 'cases.json'
        cases.unlink()
        cases.symlink_to(self.path.parent / 'holdout.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            load_pack(self.root, self.path)
        cases.unlink()
        install(self.root)
        # Individual files are legal, but their combined bytes are not.
        self.path.write_text(json.dumps(manifest) + ' ' * 60000)
        cases.write_text(cases.read_text() + ' ' * 50000)
        with self.assertRaisesRegex(ValueError, '100 KB'):
            load_pack(self.root, self.path)

    def test_files_changed_during_read_fail_without_mixed_snapshot(self):
        from fruitfly_agent.lab.optimization import task_packs
        original = task_packs.read_bytes
        calls = 0
        def racing(root, path):
            nonlocal calls
            calls += 1
            if calls == 4:
                cases = self.path.parent / 'cases.json'
                cases.write_text(cases.read_text().replace('say A', 'say Z'))
            return original(root, path)
        with patch.object(task_packs, 'read_bytes', side_effect=racing):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                load_pack(self.root, self.path)

    def test_training_save_preserves_manifest_and_holdout_bytes(self):
        before = {name:(self.path.parent/name).read_bytes() for name in ('pack.json','holdout.json')}
        validation = json.loads((self.path.parent/'cases.json').read_text())['validation']
        self.catalog.save_training('project', 'say C', 'C', expected_hash=self.catalog.source_hash('project'))
        for name,data in before.items():
            self.assertEqual(data, (self.path.parent/name).read_bytes())
        self.assertEqual(validation, json.loads((self.path.parent/'cases.json').read_text())['validation'])
        saved = json.loads((self.path.parent/'cases.json').read_text())['train'][-1]
        self.assertEqual({'expected':'C'}, saved['acceptance'])
        self.assertNotIn('expected', saved)

    def test_final_write_rechecks_cas_and_rejects_external_edits(self):
        identity = self.catalog.source_hash('project')
        original = self.catalog._write
        def race(path, payload, **kwargs):
            holdout = path.parent/'holdout.json'
            holdout.write_text(holdout.read_text().replace('SECRET_ANSWER', 'external edit'))
            return original(path, payload, **kwargs)
        cases = (self.path.parent/'cases.json').read_bytes()
        with patch.object(self.catalog, '_write', side_effect=race), self.assertRaisesRegex(ValueError,'changed'):
            self.catalog.save_training('project','new','answer',expected_hash=identity)
        self.assertEqual(cases,(self.path.parent/'cases.json').read_bytes())

    def test_migration_is_explicit_preserves_source_and_coding_references(self):
        old = coding_pack()
        old.pop('files'); old['schema_version']=1
        old['train'][0]['expected']='def add_one(x): return x+1'
        source = self.root/'old-pack.json'
        source.write_text(json.dumps(old))
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError,'migrate'):
            load_pack(self.root, source)
        new = migrate_pack(self.root, source, self.root/'converted')
        self.assertEqual(before, source.read_bytes())
        self.assertEqual('coding',new.material['id'])
        self.assertNotIn('expected',new.material['train'][0])
        refs=json.loads((self.root/'converted/references.json').read_text())
        self.assertEqual(old['train'][0]['expected'],refs['train-add'])
        with self.assertRaisesRegex(ValueError,'exists'):
            migrate_pack(self.root,source,self.root/'converted')
        self.assertEqual(before, source.read_bytes())

    async def test_one_public_validator_scores_text_and_coding(self):
        result=await score_answer(self.root,self.path,'train-1','a')
        self.assertEqual(1,result.score)
        self.assertEqual(0,(await score_answer(self.root,self.path,'train-1','wrong')).score)
        path=install(self.root,coding_pack())
        self.assertEqual(1,(await score_answer(self.root,path,'train-add','def add_one(x): return 1+x')).score)
        with self.assertRaisesRegex(ValueError,'unknown case'):
            await score_answer(self.root,path,'missing','answer')
        with patch('pathlib.Path.cwd',return_value=self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,await main(['check',str(path)]))
            # Missing reference rows fail instead of silently reporting a subset.
            refs=path.parent/'references.json';refs.write_text('{}')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                await main(['self-check',str(path)])
            self.assertEqual(2,failure.exception.code)

    def test_coding_acceptance_can_be_added_without_reference_code(self):
        path=install(self.root,coding_pack())
        catalog=TaskPackCatalog(self.root)
        acceptance={'entry_point':'triple','tests':[{'args':[2],'expected':6}]}
        catalog.save_training('coding','Implement triple(x)', '',acceptance=acceptance, expected_hash=catalog.source_hash('coding'))
        row=json.loads((path.parent/'cases.json').read_text())['train'][-1]
        self.assertEqual(acceptance,row['acceptance'])
        self.assertNotIn('expected',row)
        self.assertEqual(2,len(catalog.freeze('coding','base_prompt').train))
        with self.assertRaisesRegex(ValueError,'conflicting'):
            catalog.save_training('coding','Implement triple(x)','',acceptance={'entry_point':'triple','tests':[{'args':[2],'expected':7}]},expected_hash=catalog.source_hash('coding'))
        catalog.save_training('coding','Implement triple(x)','',acceptance={'entry_point':'triple','tests':[{'args':[2],'expected':7}]},expected_hash=catalog.source_hash('coding'),replace=True)

    def test_unpublished_directories_are_not_discovered(self):
        hidden=self.path.parent.parent/'.new-unpublished'
        hidden.mkdir()
        (hidden/'pack.json').write_bytes(self.path.read_bytes())
        self.assertEqual(['project'],[p.pack_id for p in self.catalog.summaries()])

    def test_new_policy_projects_same_envelope_without_catalog_type_branches(self):
        from dataclasses import replace
        from fruitfly_agent.lab.optimization.scoring import ScoreResult, task_policy
        from fruitfly_agent.lab.optimization.search import TaskCase
        policy=replace(task_policy('normalized-exact-v1'),policy_id='contains-v1',task_schema='contains-task-v1',
            required_fields=frozenset({'input','contains'}),
            project=lambda row:TaskCase(row['input'],row['contains']),
            score=lambda output,case:ScoreResult(float(case.expected in output)),
            acceptance_example='{"contains":"required text"}')
        payload=package();payload.update(task_schema=policy.task_schema,objective={'policy_id':policy.policy_id,'direction':'max'})
        for part in ('train','validation','holdout'):
            for row in payload[part]:row['contains']=row.pop('expected')
        install(self.root,payload)
        catalog=TaskPackCatalog(self.root,policies=(policy,))
        suite=catalog.freeze('project','base_prompt')
        self.assertEqual('contains-v1',suite.policy_id)
        self.assertEqual(1,suite.evaluation_policy.score('prefix A',suite.train[0]).score)
        self.assertEqual(policy.acceptance_example,catalog.summaries()[0].acceptance_example)

    def test_saved_cases_keep_call_arguments_and_expected_result_on_one_line(self):
        path=install(self.root,coding_pack())
        catalog=TaskPackCatalog(self.root)
        acceptance={'entry_point':'first_two','tests':[{'args':[[1,2,3]],'expected':[1,2],'preserve_args':True}]}
        manifest_before=path.read_bytes()
        holdout_before=(path.parent/'holdout.json').read_bytes()
        catalog.save_training('coding','Implement first_two(values)','',acceptance=acceptance,expected_hash=catalog.source_hash('coding'))
        text=(path.parent/'cases.json').read_text()
        self.assertGreater(len(text.splitlines()),1)
        self.assertTrue(any('"args": [[1, 2, 3]]' in line and '"expected": [1, 2]' in line for line in text.splitlines()))
        self.assertEqual(acceptance,json.loads(text)['train'][-1]['acceptance'])
        self.assertEqual(manifest_before,path.read_bytes())
        self.assertEqual(holdout_before,(path.parent/'holdout.json').read_bytes())
        frozen=catalog.freeze('coding','base_prompt')
        self.assertEqual(acceptance,json.loads(frozen.train[-1].verification))
