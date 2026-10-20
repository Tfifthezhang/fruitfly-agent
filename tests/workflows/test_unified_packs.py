"""Generic v2 views through the real terminal, with no paid model requests."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import TerminalFrontend
from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.lab.improvement.tasks import load_pack
from tests.support import application as fixtures
from tests.support.improvers import QueueEditor
from tests.support.task_packs import coding_pack
from tests.support.task_packs import install


class UnifiedPackApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_declared_file_invalidates_preview_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=install(root,coding_pack())
            app,_,provider=await fixtures.open_task_app(self,root)
            for filename in ('pack.json','cases.json','holdout.json'):
                preview=app.workflow_preview(WorkflowRequest(component_ids=('base_prompt',), task_pack_id='coding', direction='improve'))
                file=path.parent/filename
                original=file.read_bytes()
                # Even a valid formatting edit is a different declared material version.
                file.write_bytes(original+b'\n')
                with self.subTest(file=filename), self.assertRaisesRegex(ValueError,'package changed'):
                    await app.improve('improve',preview_token=preview.preview_token)
                self.assertEqual([],provider.calls)
                file.write_bytes(original)


    async def test_coding_correction_saves_checks_without_request_or_reference_code(self):
        for confirm in ('1','2'):
            with self.subTest(confirm=confirm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();path=install(root,coding_pack())
                app,_,provider=await fixtures.open_task_app(self,root)
                provider.respond_text('wrong code')
                await app.submit('Implement triple(x), returning x * 3.')
                acceptance={'entry_point':'triple','tests':[{'args':[2],'expected':6}]}
                task = app.correction_tasks()[0]
                pack = app.task_packs()[0]
                if confirm == '1':
                    app.save_training_task(task.task_id, pack.pack_id, task.input, json.dumps(acceptance),
                        acceptance=acceptance, expected_hash=pack.source_hash, reason='Declared executable acceptance')
                rows=json.loads((path.parent/'cases.json').read_text())['train']
                self.assertEqual(2 if confirm=='1' else 1,len(rows))
                self.assertEqual(1,len(provider.calls))
                if confirm=='1':
                    self.assertEqual(acceptance,rows[-1]['acceptance'])
                    self.assertNotIn('expected',rows[-1])
                    self.assertEqual(1,len(load_pack(root,path).material['holdout']))
