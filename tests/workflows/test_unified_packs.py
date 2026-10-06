"""Generic v2 views through the real terminal, with no paid model requests."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from fruitfly_agent.interactive import TerminalFrontend
from fruitfly_agent.lab.optimization.task_packs import load_pack
from tests.support import application as fixtures
from tests.support.optimizers import QueueEditor
from tests.support.task_packs import coding_pack
from tests.support.task_packs import install


class UnifiedPackApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_declared_file_invalidates_preview_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=install(root,coding_pack())
            app,_,provider=await fixtures.open_task_app(self,root,'opro')
            for filename in ('pack.json','cases.json','holdout.json'):
                preview=app.optimization_preview(pack_id='coding',direction='improve')
                file=path.parent/filename
                original=file.read_bytes()
                # Even a valid formatting edit is a different declared material version.
                file.write_bytes(original+b'\n')
                with self.subTest(file=filename), self.assertRaisesRegex(ValueError,'package changed'):
                    await app.optimize('improve',preview_token=preview.preview_token)
                self.assertEqual([],provider.calls)
                file.write_bytes(original)

    async def test_default_direction_uses_generic_view_and_cancel_makes_no_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();payload=coding_pack();payload['default_direction']='Improve boundary handling'
            install(root,payload)
            app,_,provider=await fixtures.open_task_app(self,root,'opro')
            view=next(p for p in app.task_packs() if p.pack_id=='coding')
            self.assertEqual(payload['default_direction'],view.default_direction)
            editor=QueueEditor();editor.send('/optimize','1','1','','2','/exit')
            output=io.StringIO()
            await TerminalFrontend(app,input_stream=io.StringIO(),output_stream=output,line_editor=editor).run()
            self.assertIn('blank uses Improve boundary handling',output.getvalue())
            self.assertIn('Confirm optimization',output.getvalue())
            self.assertEqual([],provider.calls)

    async def test_coding_correction_saves_checks_without_request_or_reference_code(self):
        for confirm in ('1','2'):
            with self.subTest(confirm=confirm),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();path=install(root,coding_pack())
                app,_,provider=await fixtures.open_task_app(self,root)
                provider.respond_text('wrong code')
                await app.submit('Implement triple(x), returning x * 3.')
                acceptance={'entry_point':'triple','tests':[{'args':[2],'expected':6}]}
                editor=QueueEditor()
                values=['/optimize','3','1','1','',json.dumps(acceptance),'human checked',confirm]
                if confirm=='1':values+=['1'] # return to chat after save
                editor.send(*values,'/exit')
                output=io.StringIO()
                await TerminalFrontend(app,input_stream=io.StringIO(),output_stream=output,line_editor=editor).run()
                rows=json.loads((path.parent/'cases.json').read_text())['train']
                self.assertEqual(2 if confirm=='1' else 1,len(rows))
                self.assertEqual(1,len(provider.calls))
                self.assertIn('Acceptance JSON',output.getvalue())
                self.assertNotIn('Correct answer (required)',output.getvalue())
                if confirm=='1':
                    self.assertEqual(acceptance,rows[-1]['acceptance'])
                    self.assertNotIn('expected',rows[-1])
                    self.assertEqual(1,len(load_pack(root,path).material['holdout']))
